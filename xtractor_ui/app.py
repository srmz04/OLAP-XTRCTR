"""
app.py: inicializa QApplication, carga stylesheet y levanta MainWindow.
Importado tanto por __main__.py como por PyInstaller.

Al arrancar verifica si el cache de metadata esta poblado; si no,
lo siembra desde los JSONs del ETL.
"""
from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def _load_runtime_config() -> None:
    """Carga configuración privada sin exigir que viva dentro del repositorio."""
    configured = os.environ.get("OLAP_XTRCTR_ENV_FILE", "").strip()
    env_path = Path(configured).expanduser() if configured else Path(__file__).parents[1] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)

def _load_stylesheet(app: QApplication):
    """Carga el QSS centralizado desde ui/resources/style.qss."""
    qss_path = Path(__file__).parent / "ui" / "resources" / "style.qss"
    if qss_path.exists():
        try:
            qss = qss_path.read_text(encoding="utf-8")
            app.setStyleSheet(qss)
            logger.info("Stylesheet cargado desde %s", qss_path)
        except Exception as exc:
            logger.warning("No se pudo cargar stylesheet: %s", exc)
    else:
        logger.warning("style.qss no encontrado en %s", qss_path)


def _detect_provider():
    """Devuelve MockProvider en Linux/Mac; None en Windows hasta que usuario conecte."""
    if sys.platform != "win32":
        try:
            from core.provider_mock import MockProvider
            logger.info("Usando MockProvider (Linux/dev mode)")
            return MockProvider()
        except Exception as exc:
            logger.warning("MockProvider no disponible: %s", exc)
    server = os.environ.get("OLAP_SERVER", "").strip()
    user = os.environ.get("OLAP_USER", "").strip()
    password = os.environ.get("OLAP_PASSWORD", "")
    catalog = os.environ.get("OLAP_CATALOG", "").strip()
    if server and user and password:
        try:
            from core.provider_msolap import MsOlapProvider
            return MsOlapProvider(server=server, user=user, password=password, catalog=catalog)
        except Exception as exc:
            logger.warning("No se pudo inicializar la conexión configurada: %s", exc)
    return None


def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """Atrapa excepciones no manejadas y las escribe a un archivo de log visible."""
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    try:
        log_dir = Path(os.environ.get("APPDATA", Path.home() / ".config")) / "xtractor_ui"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "error_log.txt"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write("="*60 + "\n")
            f.write(f"CRASH REPORT - {logger.name}\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
            f.write("\n")
    except Exception:
        pass


def run():
    _load_runtime_config()
    # Instalar manejador global de excepciones
    sys.excepthook = _global_exception_handler

    # High-DPI debe setearse ANTES de crear QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("XtractorUI")
    app.setOrganizationName("OLAP XTRCTR")
    app.setApplicationVersion("1.0.0")

    _load_stylesheet(app)

    # Importar aqui para que el path este listo
    from ui.main_window import MainWindow

    provider = _detect_provider()
    window = MainWindow(provider=provider)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    run()
