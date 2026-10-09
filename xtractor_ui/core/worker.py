"""
OlapWorkerThread: ejecuta operaciones OLAP en un QThread dedicado.
En Windows inicializa COM (STA). La UI solo usa signals/slots.
Patron basado en backend/olap_pool.py:OlapWorker.
"""
from __future__ import annotations

import logging
import queue
import sys
import traceback
import uuid
from typing import Any, Callable, Optional

from PyQt5.QtCore import QThread, pyqtSignal as Signal, QObject

logger = logging.getLogger(__name__)

# COM solo en Windows
_COM_AVAILABLE = False
if sys.platform == "win32":
    try:
        import pythoncom
        _COM_AVAILABLE = True
    except ImportError:
        pass


class _Signals(QObject):
    result_ready = Signal(str, object)   # (task_id, result)
    error_occurred = Signal(str, str)    # (task_id, error_message)
    progress = Signal(str, int, int)     # (task_id, current, total)


class OlapWorkerThread(QThread):
    """
    Thread dedicado para operaciones OLAP.
    - COM se inicializa UNA vez al inicio del thread (STA correcto).
    - La UI nunca llama al provider directamente; todo es via submit().
    - Signals llevan los resultados de vuelta al main thread.
    """

    def __init__(self, provider, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.signals = _Signals()
        self._queue: queue.Queue = queue.Queue()
        self.setObjectName("OlapWorkerThread")

    # ------------------------------------------------------------------
    # API publica (llamada desde main thread)
    # ------------------------------------------------------------------

    def submit(self, func: Callable, *args, task_id: Optional[str] = None, **kwargs) -> str:
        """
        Encola una operacion OLAP. Retorna task_id para rastrear el resultado.
        El resultado llega via signals.result_ready o signals.error_occurred.
        """
        tid = task_id or str(uuid.uuid4())[:8]
        self._queue.put((tid, func, args, kwargs))
        return tid

    def stop(self):
        """Para el thread limpiamente."""
        self._queue.put(None)  # poison pill
        self.wait(3000)

    # ------------------------------------------------------------------
    # Implementacion interna
    # ------------------------------------------------------------------

    def run(self):
        if _COM_AVAILABLE:
            pythoncom.CoInitialize()
            logger.info("OlapWorkerThread: COM inicializado (STA)")
        try:
            while True:
                task = self._queue.get()
                if task is None:
                    break
                tid, func, args, kwargs = task
                try:
                    result = func(*args, **kwargs)
                    self.signals.result_ready.emit(tid, result)
                except Exception as exc:
                    msg = f"{type(exc).__name__}: {exc}"
                    logger.error(f"[{tid}] Error en worker: {msg}\n{traceback.format_exc()}")
                    self.signals.error_occurred.emit(tid, msg)
        finally:
            if _COM_AVAILABLE:
                pythoncom.CoUninitialize()
                logger.info("OlapWorkerThread: COM liberado")
