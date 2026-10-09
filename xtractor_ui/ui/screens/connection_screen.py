"""
ConnectionScreen: login con perfiles guardados, test y conexion real.
Señal connected(provider) -> navegar al explorer.
"""
from __future__ import annotations

import sys
from typing import Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.config import ConnectionProfile, ProfileStore
from core.credential_store import delete_password, load_password, save_password
from ui import theme


# ── Background worker for connection test ─────────────────────────────────────

class _TestWorker(QThread):
    result_ready = pyqtSignal(object)  # ConnectionStatus

    def __init__(self, provider, server, user, password):
        super().__init__()
        self._provider = provider
        self._server = server
        self._user = user
        self._password = password

    def run(self):
        status = self._provider.test_connection(self._server, self._user, self._password)
        self.result_ready.emit(status)


# ── Screen ─────────────────────────────────────────────────────────────────────

class ConnectionScreen(QWidget):
    """
    Pantalla de conexion OLAP.
    Señales:
      connected(provider)  — provider listo; navegar a explorer
      go_back()            — volver a prereq
    """
    connected = pyqtSignal(object)
    go_back = pyqtSignal()

    def __init__(self, provider=None, parent=None):
        super().__init__(parent)
        self._provider = provider          # puede ser MockProvider o None
        self._store = ProfileStore()
        self._test_ok = False
        self._test_worker: Optional[_TestWorker] = None
        self._build_ui()
        self._load_profiles()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setProperty("class", "topbar")
        topbar.setFixedHeight(52)
        tb_layout = QHBoxLayout(topbar)
        tb_layout.setContentsMargins(16, 0, 16, 0)

        back_btn = QPushButton("← Volver")
        back_btn.setProperty("class", "ghost")
        back_btn.clicked.connect(self.go_back)
        tb_layout.addWidget(back_btn)
        tb_layout.addStretch()

        title = QLabel("Conexion OLAP")
        title.setStyleSheet(
            f"color: {theme.TEXT}; font-size: 15px; font-weight: 700;"
        )
        tb_layout.addWidget(title)
        tb_layout.addStretch()
        # Placeholder for symmetry
        tb_layout.addSpacing(80)

        root.addWidget(topbar)

        # Content
        content_wrap = QHBoxLayout()
        content_wrap.setContentsMargins(0, 0, 0, 0)
        content_wrap.addStretch()

        card = QFrame()
        card.setObjectName("connCard")
        card.setFixedWidth(500)
        card.setStyleSheet(
            f"QFrame#connCard {{"
            f"  background: {theme.BG_SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 14px;"
            f"}}"
        )

        card_v = QVBoxLayout(card)
        card_v.setContentsMargins(36, 32, 36, 32)
        card_v.setSpacing(14)

        # Profile selector
        self._add_section_label(card_v, "PERFIL GUARDADO")
        prof_row = QHBoxLayout()
        self._profile_combo = QComboBox()
        self._profile_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        prof_row.addWidget(self._profile_combo)

        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(36)
        del_btn.setToolTip("Eliminar perfil seleccionado")
        del_btn.setProperty("class", "danger")
        prof_row.addWidget(del_btn)
        del_btn.clicked.connect(self._on_delete_profile)
        card_v.addLayout(prof_row)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet(f"color: {theme.BORDER}; margin: 4px 0;")
        card_v.addWidget(sep1)

        # Connection fields
        self._add_section_label(card_v, "SERVIDOR")
        self._server_edit = self._make_edit("ej. myserver\\SSAS  o  myserver:2383")
        card_v.addWidget(self._server_edit)

        self._add_section_label(card_v, "USUARIO")
        self._user_edit = self._make_edit("dominio\\usuario  o  usuario@dominio.com")
        card_v.addWidget(self._user_edit)

        self._add_section_label(card_v, "PASSWORD")
        self._pass_edit = self._make_edit("••••••••")
        self._pass_edit.setEchoMode(QLineEdit.Password)
        card_v.addWidget(self._pass_edit)

        self._add_section_label(card_v, "CATALOGO (opcional)")
        self._catalog_edit = self._make_edit("dejar vacío para listar todos")
        card_v.addWidget(self._catalog_edit)

        # Save profile row
        save_row = QHBoxLayout()
        self._save_name_edit = self._make_edit("Nombre del perfil")
        save_row.addWidget(self._save_name_edit)
        save_btn = QPushButton("Guardar perfil")
        save_btn.setFixedWidth(130)
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BLUE_BG}; border: 1px solid {theme.BLUE};"
            f"color: {theme.DIM}; border-radius: 6px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {theme.BLUE}; color: white; }}"
        )
        save_btn.clicked.connect(self._on_save_profile)
        save_row.addWidget(save_btn)
        card_v.addLayout(save_row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"color: {theme.BORDER}; margin: 4px 0;")
        card_v.addWidget(sep2)

        # Status label
        self._status_lbl = QLabel("")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setFixedHeight(32)
        self._status_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {theme.TEXT_DIM};"
        )
        card_v.addWidget(self._status_lbl)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._test_btn = QPushButton("Probar conexion")
        self._test_btn.setFixedHeight(40)
        self._test_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_BASE}; border: 1px solid {theme.ACCENT};"
            f"color: {theme.ACCENT_FG}; border-radius: 8px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {theme.ACCENT_HOVER}; }}"
            f"QPushButton:disabled {{ color: {theme.BORDER}; border-color: {theme.BG_SURFACE}; }}"
        )
        self._test_btn.clicked.connect(self._on_test)
        btn_row.addWidget(self._test_btn)

        self._connect_btn = QPushButton("Conectar")
        self._connect_btn.setFixedHeight(40)
        self._connect_btn.setEnabled(False)
        self._connect_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.ACCENT}; border: none;"
            f"color: white; border-radius: 8px; font-weight: 700; font-size: 14px; }}"
            f"QPushButton:hover {{ background: {theme.ACCENT_H}; }}"
            f"QPushButton:disabled {{ background: {theme.ACCENT_BG}; color: {theme.ACCENT_DIS}; }}"
        )
        self._connect_btn.clicked.connect(self._on_connect)
        btn_row.addWidget(self._connect_btn)

        card_v.addLayout(btn_row)

        # Dev mode note
        if sys.platform != "win32" and self._provider is not None:
            note = QLabel("Modo desarrollo: MockProvider activo")
            note.setAlignment(Qt.AlignCenter)
            note.setStyleSheet(
                f"background: {theme.ACCENT_DEEP}; border: 1px solid {theme.ACCENT}; border-radius: 6px;"
                f"color: {theme.ACCENT_FG}; font-size: 11px; padding: 6px;"
            )
            card_v.addWidget(note)

        content_wrap.addWidget(card)
        content_wrap.addStretch()

        root.addStretch()
        root.addLayout(content_wrap)
        root.addStretch()

    def _add_section_label(self, layout: QVBoxLayout, text: str):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; letter-spacing: 1px;"
            f"color: {theme.TEXT_DIM}; background: transparent; margin-top: 4px;"
        )
        layout.addWidget(lbl)

    def _make_edit(self, placeholder: str) -> QLineEdit:
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        e.setFixedHeight(36)
        e.textChanged.connect(self._on_field_changed)
        return e

    # ── Profile management ────────────────────────────────────────────────────

    def _load_profiles(self):
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        self._profile_combo.addItem("— Seleccionar perfil guardado —", None)
        for p in self._store.load_all():
            self._profile_combo.addItem(p.name, p)
        self._profile_combo.blockSignals(False)

    @pyqtSlot(int)
    def _on_profile_selected(self, idx: int):
        profile: Optional[ConnectionProfile] = self._profile_combo.itemData(idx)
        if profile is None:
            return
        self._server_edit.setText(profile.server)
        self._user_edit.setText(profile.user)
        self._catalog_edit.setText(profile.default_catalog)
        self._save_name_edit.setText(profile.name)
        pw = load_password(profile.name)
        self._pass_edit.setText(pw)
        self._test_ok = False
        self._connect_btn.setEnabled(False)
        self._set_status("", "")

    @pyqtSlot()
    def _on_save_profile(self):
        name = self._save_name_edit.text().strip()
        if not name:
            self._set_status("Introduce un nombre para el perfil.", "error")
            return
        profile = ConnectionProfile(
            name=name,
            server=self._server_edit.text().strip(),
            user=self._user_edit.text().strip(),
            default_catalog=self._catalog_edit.text().strip(),
        )
        self._store.save(profile)
        save_password(name, self._pass_edit.text())
        self._load_profiles()
        # Select the saved profile
        for i in range(self._profile_combo.count()):
            if self._profile_combo.itemText(i) == name:
                self._profile_combo.setCurrentIndex(i)
                break
        self._set_status(f"Perfil '{name}' guardado.", "success")

    @pyqtSlot()
    def _on_delete_profile(self):
        idx = self._profile_combo.currentIndex()
        profile = self._profile_combo.itemData(idx)
        if profile is None:
            return
        reply = QMessageBox.question(
            self, "Eliminar perfil",
            f"¿Eliminar el perfil '{profile.name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._store.delete(profile.name)
            delete_password(profile.name)
            self._load_profiles()
            self._set_status(f"Perfil '{profile.name}' eliminado.", "")

    # ── Connection test ───────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_field_changed(self):
        self._test_ok = False
        self._connect_btn.setEnabled(False)

    @pyqtSlot()
    def _on_test(self):
        server = self._server_edit.text().strip()
        user = self._user_edit.text().strip()
        password = self._pass_edit.text()

        if not server:
            self._set_status("Introduce el servidor.", "error")
            return

        self._test_btn.setEnabled(False)
        self._test_btn.setText("Probando…")
        self._set_status("Conectando…", "")
        self._test_ok = False
        self._connect_btn.setEnabled(False)

        # Use mock provider in dev mode
        provider = self._get_or_build_provider(server, user, password)

        self._test_worker = _TestWorker(provider, server, user, password)
        self._test_worker.result_ready.connect(self._on_test_result)
        self._test_worker.start()

    @pyqtSlot(object)
    def _on_test_result(self, status):
        self._test_btn.setEnabled(True)
        self._test_btn.setText("Probar conexion")

        if status.connected:
            self._test_ok = True
            self._set_status("Conexion exitosa.", "success")
            self._connect_btn.setEnabled(True)
        else:
            self._test_ok = False
            self._set_status(f"Error: {status.error}", "error")
            self._connect_btn.setEnabled(False)

    @pyqtSlot()
    def _on_connect(self):
        if not self._test_ok:
            return
        server = self._server_edit.text().strip()
        user = self._user_edit.text().strip()
        password = self._pass_edit.text()
        provider = self._get_or_build_provider(server, user, password)
        self.connected.emit(provider)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_or_build_provider(self, server: str, user: str, password: str):
        """En Linux usa el MockProvider existente; en Windows construye MsOlapProvider."""
        if self._provider is not None and sys.platform != "win32":
            return self._provider
        if sys.platform == "win32":
            try:
                from core.provider_msolap import MsOlapProvider
                catalog = self._catalog_edit.text().strip()
                return MsOlapProvider(server=server, user=user,
                                      password=password, catalog=catalog)
            except ImportError:
                pass
        return self._provider

    def _set_status(self, msg: str, level: str):
        color = {
            "error": theme.ERROR,
            "success": theme.SUCCESS,
            "warn": theme.WARN,
            "": theme.TEXT_DIM,
        }.get(level, theme.TEXT_DIM)
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {color};"
        )
