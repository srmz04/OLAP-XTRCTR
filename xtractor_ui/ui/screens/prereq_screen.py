"""
PrereqScreen: verifica prerequisitos del sistema al arrancar.
En Linux muestra "Modo desarrollo" y permite continuar de inmediato.
En Windows verifica adodbapi, pywin32 y el provider MSOLAP registrado.
"""
from __future__ import annotations

import platform
import sys
from typing import List, Tuple

from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ui import theme


# ── Check runner ──────────────────────────────────────────────────────────────

class _CheckWorker(QThread):
    """Ejecuta todos los checks en background; emite lista de resultados."""
    checks_done = pyqtSignal(list)  # List[Tuple[str, str, str]]  name,status,detail

    def run(self):
        results: List[Tuple[str, str, str]] = []
        is_win = sys.platform == "win32"

        # Python version
        ver = platform.python_version()
        ok = sys.version_info >= (3, 9)
        results.append((
            "Python >= 3.9",
            "ok" if ok else "error",
            f"v{ver}",
        ))

        if is_win:
            results += self._win_checks()
        else:
            results.append(("Modo desarrollo (Linux/Mac)", "info",
                            "MockProvider activo — COM no requerido"))

        self.checks_done.emit(results)

    def _win_checks(self) -> List[Tuple[str, str, str]]:
        out = []

        # adodbapi
        try:
            import adodbapi  # type: ignore  # noqa: F401
            out.append(("adodbapi", "ok", "Instalado"))
        except ImportError:
            out.append(("adodbapi", "error",
                        "pip install adodbapi  — Requerido para OLAP"))

        # pywin32 / pythoncom
        try:
            import pythoncom  # type: ignore  # noqa: F401
            import win32com.client  # type: ignore  # noqa: F401
            out.append(("pywin32 / pythoncom", "ok", "Instalado"))
        except ImportError:
            out.append(("pywin32 / pythoncom", "error",
                        "pip install pywin32  — Requerido para COM"))

        # MSOLAP provider registrado
        try:
            import win32com.client as wc  # type: ignore
            wc.Dispatch("ADODB.Connection")
            out.append(("ADODB.Connection", "ok", "COM object creado"))
        except Exception as exc:
            msg = str(exc)
            if "MSOLAP" in msg or "Provider" in msg:
                detail = "Instalar SQL Server Analysis Services OLEDB Provider"
            else:
                detail = msg[:80]
            out.append(("MSOLAP Provider", "error", detail))

        return out


# ── Check row widget ──────────────────────────────────────────────────────────

class _CheckRow(QFrame):
    ICON = {"ok": "✓", "error": "✗", "warn": "⚠", "info": "ℹ"}
    COLOR = {
        "ok":    theme.SUCCESS,
        "error": theme.ERROR,
        "warn":  theme.WARN,
        "info":  theme.ACCENT,
    }

    def __init__(self, name: str, status: str, detail: str, parent=None):
        super().__init__(parent)
        self.setObjectName("CheckRow")
        self.setFixedHeight(44)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(12)

        icon = QLabel(self.ICON.get(status, "?"))
        icon.setFixedWidth(22)
        icon.setAlignment(Qt.AlignCenter)
        icon.setFont(QFont("", 15, QFont.Bold))
        icon.setStyleSheet(f"color: {self.COLOR.get(status, theme.TEXT_DIM)}; background: transparent;")
        row.addWidget(icon)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {theme.TEXT}; background: transparent; font-weight: 600;")
        row.addWidget(name_lbl)

        row.addStretch()

        detail_lbl = QLabel(detail)
        detail_lbl.setStyleSheet(
            f"color: {self.COLOR.get(status, theme.TEXT_DIM)}; "
            f"background: transparent; font-size: 12px;"
        )
        detail_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(detail_lbl)


# ── Main screen ───────────────────────────────────────────────────────────────

class PrereqScreen(QWidget):
    prereqs_ok = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_ok = False
        self._build_ui()
        self._run_checks()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Centered content card
        outer.addStretch(2)

        card_wrap = QHBoxLayout()
        card_wrap.addStretch()

        card = QFrame()
        card.setObjectName("prereqCard")
        card.setFixedWidth(560)
        card.setStyleSheet(
            f"QFrame#prereqCard {{"
            f"  background-color: {theme.BG_SURFACE};"
            f"  border: 1px solid {theme.BORDER};"
            f"  border-radius: 14px;"
            f"}}"
        )

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 36, 40, 36)
        card_layout.setSpacing(0)

        # Logo / title
        logo = QLabel("⬡ XtractorUI")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            f"font-size: 28px; font-weight: 800; color: {theme.ACCENT_FG};"
            f"letter-spacing: 1px; background: transparent;"
        )
        card_layout.addWidget(logo)

        sub = QLabel("Explorador y constructor de consultas OLAP")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 13px; margin-bottom: 28px; background: transparent;")
        card_layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER}; margin-bottom: 20px;")
        card_layout.addWidget(sep)

        section_lbl = QLabel("VERIFICACION DEL SISTEMA")
        section_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; letter-spacing: 1.5px;"
            f"color: {theme.TEXT_DIM}; margin-bottom: 12px; background: transparent;"
        )
        card_layout.addWidget(section_lbl)

        # Scroll area for checks
        self._checks_widget = QWidget()
        self._checks_widget.setStyleSheet("background: transparent;")
        self._checks_layout = QVBoxLayout(self._checks_widget)
        self._checks_layout.setContentsMargins(0, 0, 0, 0)
        self._checks_layout.setSpacing(4)

        # Loading placeholder
        self._loading_lbl = QLabel("Verificando…")
        self._loading_lbl.setAlignment(Qt.AlignCenter)
        self._loading_lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; padding: 20px; background: transparent;")
        self._checks_layout.addWidget(self._loading_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._checks_widget)
        scroll.setFixedHeight(200)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {theme.BG_BASE}; border: 1px solid {theme.BORDER};"
            f"border-radius: 8px; }}"
        )
        card_layout.addWidget(scroll)
        card_layout.addSpacing(20)

        # Status message
        self._status_lbl = QLabel("")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 12px; margin-bottom: 16px; background: transparent;"
        )
        card_layout.addWidget(self._status_lbl)

        # Action button
        self._btn = QPushButton("Verificando…")
        self._btn.setEnabled(False)
        self._btn.setFixedHeight(42)
        self._btn.setProperty("class", "primary")
        self._btn.setStyleSheet(
            f"QPushButton {{ background: {theme.ACCENT}; color: white; border: none;"
            f"border-radius: 8px; font-size: 14px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {theme.ACCENT_H}; }}"
            f"QPushButton:disabled {{ background: {theme.ACCENT_BG}; color: {theme.ACCENT_DIS}; }}"
        )
        self._btn.clicked.connect(self._on_continue)
        card_layout.addWidget(self._btn)

        card_wrap.addWidget(card)
        card_wrap.addStretch()
        outer.addLayout(card_wrap)
        outer.addStretch(3)

        # Version footer
        ver_lbl = QLabel(f"Python {platform.python_version()}  ·  {platform.system()} {platform.release()}")
        ver_lbl.setAlignment(Qt.AlignCenter)
        ver_lbl.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; margin-bottom: 12px; background: transparent;"
        )
        outer.addWidget(ver_lbl)

    # ── Check execution ──────────────────────────────────────────────────────

    def _run_checks(self):
        self._worker = _CheckWorker()
        self._worker.checks_done.connect(self._on_checks_done)
        self._worker.start()

    @pyqtSlot(list)
    def _on_checks_done(self, results: list):
        # Clear loading label
        self._loading_lbl.setVisible(False)

        errors = 0
        for name, status, detail in results:
            row = _CheckRow(name, status, detail)
            self._checks_layout.addWidget(row)
            if status == "error":
                errors += 1

        self._checks_layout.addStretch()

        is_linux = sys.platform != "win32"

        if is_linux:
            self._all_ok = True
            self._status_lbl.setText("Modo desarrollo activo — MockProvider en uso")
            self._status_lbl.setStyleSheet(
                f"color: {theme.ACCENT}; font-size: 12px; margin-bottom: 16px; background: transparent;"
            )
            self._btn.setText("Continuar")
            self._btn.setEnabled(True)
        elif errors == 0:
            self._all_ok = True
            self._status_lbl.setText("Todos los prerequisitos cumplidos.")
            self._status_lbl.setStyleSheet(
                f"color: {theme.SUCCESS}; font-size: 12px; margin-bottom: 16px; background: transparent;"
            )
            self._btn.setText("Continuar")
            self._btn.setEnabled(True)
        else:
            self._all_ok = False
            self._status_lbl.setText(
                f"{errors} prerequisito(s) faltante(s). "
                "Instala los componentes indicados y reinicia la aplicacion."
            )
            self._status_lbl.setStyleSheet(
                f"color: {theme.ERROR}; font-size: 12px; margin-bottom: 16px; background: transparent;"
            )
            self._btn.setText("Reintentar")
            self._btn.setEnabled(True)

    @pyqtSlot()
    def _on_continue(self):
        if self._all_ok:
            self.prereqs_ok.emit()
        else:
            # Retry
            self._all_ok = False
            self._btn.setEnabled(False)
            self._btn.setText("Verificando…")
            self._status_lbl.setText("")
            # Clear previous rows
            while self._checks_layout.count():
                item = self._checks_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._loading_lbl.setVisible(True)
            self._checks_layout.addWidget(self._loading_lbl)
            self._run_checks()
