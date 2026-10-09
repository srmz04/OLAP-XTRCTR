"""
MainWindow: ventana principal con QStackedWidget para navegar entre pantallas.
Conecta signals entre pantallas y maneja el flujo de navegacion.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QLabel,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ui.screens.prereq_screen import PrereqScreen
from ui.screens.connection_screen import ConnectionScreen
from ui.screens.explorer_screen import ExplorerScreen
from ui.screens.builder_screen import BuilderScreen
from ui.screens.results_screen import ResultsScreen
from core.cache import MetadataCache

logger = logging.getLogger(__name__)

SCREEN_PREREQ      = 0
SCREEN_CONNECTION  = 1
SCREEN_EXPLORER    = 2
SCREEN_BUILDER     = 3
SCREEN_RESULTS     = 4

class _QueryWorker(QThread):
    result_ready = pyqtSignal(object, float)  # (QueryResult, elapsed)
    error_occurred = pyqtSignal(str)

    def __init__(self, provider, catalog: str, mdx: str):
        super().__init__()
        self._provider = provider
        self._catalog = catalog
        self._mdx = mdx
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        t0 = time.monotonic()
        try:
            result = self._provider.execute_mdx(self._catalog, self._mdx)
            elapsed = time.monotonic() - t0
            if not self._cancelled:
                self.result_ready.emit(result, elapsed)
        except Exception as exc:
            if not self._cancelled:
                self.error_occurred.emit(str(exc))


# ── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, provider=None):
        super().__init__()
        self._provider = provider
        self._catalog = ""
        self._query_worker: Optional[_QueryWorker] = None
        # Cache compartida entre explorer y builder (metadata + historial)
        self._cache = MetadataCache()

        self.setWindowTitle("OLAP XTRCTR")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Crear todas las pantallas
        self._prereq = PrereqScreen()
        self._connection = ConnectionScreen(provider=provider)
        self._explorer = ExplorerScreen(provider=provider)
        self._builder = BuilderScreen()
        self._results = ResultsScreen()

        self._stack.addWidget(self._prereq)       # 0
        self._stack.addWidget(self._connection)   # 1
        self._stack.addWidget(self._explorer)     # 2
        self._stack.addWidget(self._builder)      # 3
        self._stack.addWidget(self._results)      # 4

        # Status bar
        self._status = QStatusBar()
        self._status.setObjectName("statusBar")
        self.setStatusBar(self._status)
        self._status.showMessage("Iniciando XtractorUI…")

        self._connect_signals()
        self.go_to(SCREEN_PREREQ)

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self):
        # PrereqScreen -> ConnectionScreen
        self._prereq.prereqs_ok.connect(self._on_prereqs_ok)

        # ConnectionScreen signals
        self._connection.connected.connect(self._on_connected)
        self._connection.go_back.connect(lambda: self.go_to(SCREEN_PREREQ))

        # ExplorerScreen signals
        self._explorer.build_query.connect(self._on_build_query)
        self._explorer.go_back.connect(lambda: self.go_to(SCREEN_CONNECTION))

        # BuilderScreen signals
        self._builder.execute_query.connect(self._on_execute_query)
        self._builder.go_back.connect(lambda: self.go_to(SCREEN_EXPLORER))

        # ResultsScreen signals
        self._results.new_query.connect(lambda: self.go_to(SCREEN_BUILDER))
        self._results.go_explorer.connect(lambda: self.go_to(SCREEN_EXPLORER))

    # ── Navigation slots ──────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_prereqs_ok(self):
        if self._provider is not None:
            # Modo desarrollo (MockProvider)
            self._explorer.set_provider(self._provider)
            self.go_to(SCREEN_EXPLORER)
            self.set_status("Modo desarrollo — MockProvider activo")
            return

        self.go_to(SCREEN_CONNECTION)
        self.set_status("Configure una conexión para continuar")

    @pyqtSlot(object)
    def _on_connected(self, provider):
        self._provider = provider
        self._explorer.set_provider(provider)
        self._builder._provider = provider
        self._builder.set_cache(self._cache)  # inyectar cache al builder
        self.go_to(SCREEN_EXPLORER)
        self.set_status("Conectado — explorando metadata")

    @pyqtSlot(object)
    def _on_build_query(self, context: dict):
        self._catalog = context.get("catalog", "")
        self._builder.set_cache(self._cache)  # garantizar que cache este disponible
        self._builder.set_context(context)
        self.go_to(SCREEN_BUILDER)
        self.set_status(f"Constructor — {self._catalog}")

    @pyqtSlot(str, str)
    def _on_execute_query(self, catalog: str, mdx: str):
        if not self._provider:
            self.set_status("Conecte un servidor OLAP antes de ejecutar la consulta")
            self.go_to(SCREEN_CONNECTION)
            return

        self._catalog = catalog
        self.set_status(f"Ejecutando consulta en {catalog}…")
        self._builder.set_executing(True)

        self._query_worker = _QueryWorker(self._provider, catalog, mdx)
        self._query_worker.result_ready.connect(self._on_query_done)
        self._query_worker.error_occurred.connect(self._on_query_error)
        self._query_worker.finished.connect(self._query_worker.deleteLater)
        self._query_worker.start()

        # Timeout: 60s para queries
        self._query_timer = QTimer(self)
        self._query_timer.setSingleShot(True)
        self._query_timer.timeout.connect(self._on_query_timeout)
        self._query_timer.start(60_000)

    def _stop_query_timer(self):
        if hasattr(self, '_query_timer') and self._query_timer.isActive():
            self._query_timer.stop()

    @pyqtSlot()
    def _on_query_timeout(self):
        self._builder.set_executing(False)
        self.set_status("Timeout: el servidor no respondio en 60s")
        if self._query_worker and self._query_worker.isRunning():
            self._query_worker.cancel()

    @pyqtSlot(object, float)
    def _on_query_done(self, result, elapsed: float):
        self._stop_query_timer()
        self._builder.set_executing(False)

        self._results.show_result(
            result,
            catalog=self._catalog,
            mdx=self._builder.get_mdx(),
            elapsed=elapsed,
        )
        self.go_to(SCREEN_RESULTS)
        self.set_status(
            f"{result.row_count:,} filas  ·  {elapsed:.2f}s  ·  {self._catalog}"
        )

    @pyqtSlot(str)
    def _on_query_error(self, error: str):
        self._stop_query_timer()
        self._builder.set_executing(False)
        self.set_status(f"Error: {error[:120]}")
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Error en consulta", error)

    # ── Public API ────────────────────────────────────────────────────────────

    def go_to(self, index: int):
        self._stack.setCurrentIndex(index)

    def set_status(self, msg: str):
        self._status.showMessage(msg)
