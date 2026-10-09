"""
BuilderScreen: constructor visual de consultas MDX con drag-and-drop.
Permite arrastrar (o doble-click) medidas/dimensiones a zonas COLUMNAS, FILAS, FILTROS.
Genera MDX en tiempo real, guarda historial de consultas en SQLite (MetadataCache).
Emite señal execute_query(catalog, mdx).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QMimeData, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QDrag, QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui import theme

logger = logging.getLogger(__name__)

# Nombre reservado para la sesion automatica — nunca mostrado al usuario
_SESSION_SLOT = "~session~"

ROLE_UNAME = Qt.UserRole
ROLE_KIND  = Qt.UserRole + 1   # "measure" | "hierarchy" | "level"
ROLE_DATA  = Qt.UserRole + 2


# ── Drag-enabled source list ──────────────────────────────────────────────────

class _SourceList(QListWidget):
    """Lista de medidas/dimensiones con soporte drag."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setStyleSheet(
            f"QListWidget {{ background: {theme.BG_DEEP}; border: none; }}"
            f"QListWidget::item {{ padding: 5px 8px; border-radius: 4px; }}"
            f"QListWidget::item:hover {{ background: {theme.BG_SURFACE}; }}"
            f"QListWidget::item:selected {{ background: {theme.ACCENT_D}; color: white; }}"
        )

    def startDrag(self, actions):
        item = self.currentItem()
        if not item:
            return
        mime = QMimeData()
        mime.setText(item.text())
        mime.setData("application/x-olap-item-kind",
                     (item.data(ROLE_KIND) or "").encode())
        mime.setData("application/x-olap-item-uname",
                     (item.data(ROLE_UNAME) or "").encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.CopyAction)


# ── Drop zone list ────────────────────────────────────────────────────────────

class _DropZone(QListWidget):
    """Lista que acepta drops de _SourceList; permite borrar items."""
    changed = pyqtSignal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self._label = label
        self.setStyleSheet(
            f"QListWidget {{ background: {theme.BG_DEEP}; border: 2px dashed {theme.BORDER};"
            f"border-radius: 8px; }}"
            f"QListWidget::item {{ padding: 5px 8px; border-radius: 4px; }}"
            f"QListWidget::item:hover {{ background: {theme.ACCENT_HOVER}; }}"
            f"QListWidget::item:selected {{ background: {theme.ACCENT_D}; color: white; }}"
        )
        # Delete with Del key
        self.setFocus()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-olap-item-uname"):
            event.acceptProposedAction()
            self.setStyleSheet(
                f"QListWidget {{ background: {theme.ACCENT_DEEP}; border: 2px dashed "
                f"{theme.ACCENT}; border-radius: 8px; }}"
                f"QListWidget::item {{ padding: 5px 8px; border-radius: 4px; }}"
                f"QListWidget::item:hover {{ background: {theme.ACCENT_HOVER}; }}"
                f"QListWidget::item:selected {{ background: {theme.ACCENT_D}; color: white; }}"
            )
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._reset_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._reset_style()
        mime = event.mimeData()
        uname = mime.data("application/x-olap-item-uname").data().decode()
        kind  = mime.data("application/x-olap-item-kind").data().decode()
        text  = mime.text()
        if uname and not self._has_item(uname):
            self._add_item(text, uname, kind)
        event.acceptProposedAction()

    def _reset_style(self):
        self.setStyleSheet(
            f"QListWidget {{ background: {theme.BG_DEEP}; border: 2px dashed {theme.BORDER};"
            f"border-radius: 8px; }}"
            f"QListWidget::item {{ padding: 5px 8px; border-radius: 4px; }}"
            f"QListWidget::item:hover {{ background: {theme.ACCENT_HOVER}; }}"
            f"QListWidget::item:selected {{ background: {theme.ACCENT_D}; color: white; }}"
        )

    def _has_item(self, uname: str) -> bool:
        for i in range(self.count()):
            if self.item(i).data(ROLE_UNAME) == uname:
                return True
        return False

    def _add_item(self, text: str, uname: str, kind: str):
        item = QListWidgetItem(f"  {text}")
        item.setData(ROLE_UNAME, uname)
        item.setData(ROLE_KIND, kind)
        self.addItem(item)
        self.changed.emit()

    def add_item_programmatic(self, text: str, uname: str, kind: str):
        if not self._has_item(uname):
            self._add_item(text, uname, kind)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in self.selectedItems():
                self.takeItem(self.row(item))
            self.changed.emit()
        else:
            super().keyPressEvent(event)

    def get_unique_names(self) -> List[str]:
        return [self.item(i).data(ROLE_UNAME) for i in range(self.count())]

    def get_kinds(self) -> List[str]:
        return [self.item(i).data(ROLE_KIND) for i in range(self.count())]

    def clear_zone(self):
        self.clear()
        self.changed.emit()


# ── MDX builder logic ─────────────────────────────────────────────────────────

def build_mdx(catalog: str, cube: str,
              columns: List[str], col_kinds: List[str],
              rows: List[str], row_kinds: List[str],
              filters: List[str], filter_kinds: List[str]) -> str:
    """Genera MDX SELECT desde las zonas del builder."""
    if not cube:
        cube = catalog

    def bracket(s: str) -> str:
        """Asegura que el nombre este entre corchetes si no lo esta."""
        s = s.strip()
        if s.startswith("[") and s.endswith("]"):
            return s
        if s.startswith("[") and "].[" in s:
            return s
        return f"[{s}]"

    def to_set(unames: List[str], kinds: List[str]) -> str:
        parts = []
        for u, k in zip(unames, kinds):
            if k == "measure":
                parts.append(u)
            else:
                # Hierarchy or level -> use .Members
                parts.append(f"{u}.Members")
        if not parts:
            return "{}"
        if len(parts) == 1:
            return f"{{{parts[0]}}}"
        # NON EMPTY CROSSJOIN
        inner = parts[-1]
        for p in reversed(parts[:-1]):
            inner = f"CROSSJOIN({{{p}}}, {{{inner}}})"
        return inner

    col_set = to_set(columns, col_kinds) if columns else "{}"
    row_set = to_set(rows, row_kinds) if rows else ""

    if row_set:
        axes = (
            f"SELECT\n"
            f"  NON EMPTY {col_set} ON COLUMNS,\n"
            f"  NON EMPTY {row_set} ON ROWS\n"
        )
    else:
        axes = f"SELECT\n  NON EMPTY {col_set} ON COLUMNS\n"

    from_clause = f"FROM [{cube}]"

    if filters:
        where_parts = [f for f, k in zip(filters, filter_kinds) if k != "measure"]
        if where_parts:
            where_set = ", ".join(where_parts)
            where_clause = f"\nWHERE ({where_set})"
        else:
            where_clause = ""
    else:
        where_clause = ""

    return f"{axes}{from_clause}{where_clause}"


# ── Screen ─────────────────────────────────────────────────────────────────────

class BuilderScreen(QWidget):
    """
    Señales:
      execute_query(catalog, mdx)
      go_back()
    """
    execute_query = pyqtSignal(str, str)
    go_back = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider = None
        self._catalog = ""
        self._cube = ""
        self._cache = None          # MetadataCache inyectada por MainWindow
        self._history_visible = False
        self._ctx_hierarchies: list = []
        self._ctx_measures: list = []
        self._build_ui()

    def set_cache(self, cache) -> None:
        """
        Inyecta la instancia de MetadataCache compartida desde MainWindow.
        Debe llamarse antes de set_context() para que el historial funcione.
        """
        self._cache = cache

    def set_context(self, context: dict):
        """Recibe contexto desde ExplorerScreen; restaura sesion si existe."""
        self._provider = context.get("provider")
        self._catalog = context.get("catalog", "")
        self._cube = self._catalog  # se resuelve luego si provider lo soporta
        self._catalog_lbl.setText(f"Catalogo: {self._catalog}")
        self._ctx_hierarchies = context.get("hierarchies", [])
        self._ctx_measures = context.get("measures", [])
        self._load_metadata()
        self._refresh_history()
        self._restore_session_state()  # carga ultimo estado si lo hay
        # Pre-select item if coming from explorer
        sel_type = context.get("selected_type")
        sel_data = context.get("selected_data")
        if sel_type and sel_data:
            self._preselect(sel_type, sel_data)

    def _load_metadata(self):
        if self._provider:
            try:
                measures = self._provider.list_measures(self._catalog)
            except Exception:
                measures = []
            try:
                hierarchies = self._provider.list_hierarchies(self._catalog)
            except Exception:
                hierarchies = []
        elif self._ctx_hierarchies or self._ctx_measures:
            hierarchies = self._ctx_hierarchies
            measures = self._ctx_measures
        else:
            return

        self._measures_list.clear()
        for m in measures:
            item = QListWidgetItem(f"∑  {m.caption}")
            item.setData(ROLE_UNAME, m.id)
            item.setData(ROLE_KIND, "measure")
            item.setToolTip(m.id)
            item.setForeground(QColor(theme.MEASURE))
            self._measures_list.addItem(item)

        self._dims_tree.clear()
        for d in hierarchies:
            dim_name = d.dimension
            # Find or create dimension node
            dim_items = self._dims_tree.findItems(dim_name, Qt.MatchExactly, 0)
            if dim_items:
                dim_node = dim_items[0]
            else:
                dim_node = QTreeWidgetItem(self._dims_tree, [dim_name])
                dim_node.setForeground(0, QColor(theme.DIM))
                font = dim_node.font(0)
                font.setBold(True)
                dim_node.setFont(0, font)

            hier_item = QTreeWidgetItem(dim_node, [f"  {d.hierarchy}"])
            hier_item.setData(0, ROLE_UNAME, f"[{d.dimension}].[{d.hierarchy}]")
            hier_item.setData(0, ROLE_KIND, "hierarchy")
            hier_item.setForeground(0, QColor(theme.HIER))

            for lv in d.levels:
                lv_item = QTreeWidgetItem(hier_item, [f"    {lv.name}"])
                lv_item.setData(0, ROLE_UNAME, f"[{d.dimension}].[{d.hierarchy}].[{lv.name}]")
                lv_item.setData(0, ROLE_KIND, "level")
                lv_item.setForeground(0, QColor(theme.LEVEL))
                lv_item.setToolTip(0, lv_item.data(0, ROLE_UNAME))

    def _preselect(self, sel_type: str, sel_data: Any):
        """Agrega el item seleccionado en explorer a la zona COLUMNAS."""
        from ui.screens.explorer_screen import TYPE_MEASURE, TYPE_HIERARCHY, TYPE_LEVEL
        if sel_type == TYPE_MEASURE and hasattr(sel_data, "id"):
            self._cols_zone.add_item_programmatic(sel_data.caption, sel_data.id, "measure")
        elif sel_type == TYPE_HIERARCHY and hasattr(sel_data, "hierarchy"):
            uname = f"[{sel_data.dimension}].[{sel_data.hierarchy}]"
            self._cols_zone.add_item_programmatic(sel_data.hierarchy, uname, "hierarchy")
        elif sel_type == TYPE_LEVEL:
            dim_info = sel_data.get("dim_info")
            level = sel_data.get("level")
            if dim_info and level:
                uname = f"[{dim_info.dimension}].[{dim_info.hierarchy}].[{level.name}]"
                self._cols_zone.add_item_programmatic(level.name, uname, "level")
        self._rebuild_mdx()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        topbar = QFrame()
        topbar.setFixedHeight(52)
        topbar.setProperty("class", "topbar")
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(16, 0, 16, 0)

        back_btn = QPushButton("← Volver")
        back_btn.clicked.connect(self.go_back)
        back_btn.setProperty("class", "ghost")
        tb.addWidget(back_btn)

        self._catalog_lbl = QLabel("Constructor de Consulta")
        self._catalog_lbl.setStyleSheet(f"color: {theme.TEXT}; font-size: 15px; font-weight: 700; margin-left: 16px;")
        tb.addWidget(self._catalog_lbl)
        tb.addStretch()
        root.addWidget(topbar)

        # Main area
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setHandleWidth(2)
        main_splitter.setStyleSheet(f"QSplitter::handle {{ background: {theme.BORDER}; }}")

        # ── LEFT: palette ──────────────────────────────────────────────────
        left = QFrame()
        left.setMinimumWidth(220)
        left.setMaximumWidth(300)
        left.setStyleSheet(f"background: {theme.BG_BASE}; border-right: 1px solid {theme.BORDER};")
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(8, 8, 8, 8)
        left_v.setSpacing(6)

        self._add_pal_section(left_v, "MEDIDAS  (arrastrar o doble-click)")
        self._measures_list = _SourceList()
        self._measures_list.setFixedHeight(160)
        self._measures_list.itemDoubleClicked.connect(
            lambda item: self._quick_add(item, self._cols_zone))
        left_v.addWidget(self._measures_list)

        self._add_pal_section(left_v, "DIMENSIONES")
        self._dims_tree = QTreeWidget()
        self._dims_tree.setHeaderHidden(True)
        self._dims_tree.setDragEnabled(True)
        self._dims_tree.setStyleSheet(
            f"QTreeWidget {{ background: {theme.BG_DEEP}; border: none; }}"
            f"QTreeWidget::item {{ padding: 4px 6px; }}"
            f"QTreeWidget::item:hover {{ background: {theme.BG_SURFACE}; }}"
            f"QTreeWidget::item:selected {{ background: {theme.ACCENT_D}; }}"
        )
        self._dims_tree.itemDoubleClicked.connect(self._on_dim_double_click)
        left_v.addWidget(self._dims_tree, 1)

        # ── RIGHT: drop zones + MDX ────────────────────────────────────────
        right = QFrame()
        right.setStyleSheet(f"background: {theme.BG_BASE};")
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(10, 8, 10, 8)
        right_v.setSpacing(8)

        # Zones grid
        zones_splitter = QSplitter(Qt.Vertical)
        zones_splitter.setHandleWidth(2)
        zones_splitter.setStyleSheet(f"QSplitter::handle {{ background: {theme.BORDER}; }}")

        # Columns zone
        col_frame = self._make_zone_frame("COLUMNAS  (ON COLUMNS)", theme.ACCENT)
        col_inner = col_frame.layout()
        self._cols_zone = _DropZone("COLUMNAS")
        self._cols_zone.changed.connect(self._rebuild_mdx)
        col_inner.addWidget(self._cols_zone)
        zones_splitter.addWidget(col_frame)

        # Rows zone
        row_frame = self._make_zone_frame("FILAS  (ON ROWS)", theme.BLUE)
        row_inner = row_frame.layout()
        self._rows_zone = _DropZone("FILAS")
        self._rows_zone.changed.connect(self._rebuild_mdx)
        row_inner.addWidget(self._rows_zone)
        zones_splitter.addWidget(row_frame)

        # Filters zone
        fil_frame = self._make_zone_frame("FILTROS  (WHERE)", theme.WARN)
        fil_inner = fil_frame.layout()
        self._filters_zone = _DropZone("FILTROS")
        self._filters_zone.changed.connect(self._rebuild_mdx)
        fil_inner.addWidget(self._filters_zone)
        zones_splitter.addWidget(fil_frame)
        zones_splitter.setSizes([130, 130, 100])

        # Conectar botones "Vaciar"
        self._connect_zone_clear(col_frame, self._cols_zone)
        self._connect_zone_clear(row_frame, self._rows_zone)
        self._connect_zone_clear(fil_frame, self._filters_zone)

        right_v.addWidget(zones_splitter, 1)

        # MDX Preview
        mdx_hdr = QLabel("MDX GENERADO")
        mdx_hdr.setStyleSheet(
            f"font-size: 10px; font-weight: 700; letter-spacing: 1.5px;"
            f"color: {theme.TEXT_DIM}; margin-top: 4px;"
        )
        right_v.addWidget(mdx_hdr)

        self._mdx_edit = QTextEdit()
        self._mdx_edit.setReadOnly(False)
        self._mdx_edit.setFixedHeight(100)
        self._mdx_edit.setPlaceholderText("Agrega medidas y dimensiones para generar MDX…")
        self._mdx_edit.setStyleSheet(
            f"QTextEdit {{ background: {theme.BG_CODE}; color: {theme.ACCENT_FG};"
            f"border: 1px solid {theme.BORDER}; border-radius: 6px;"
            f"font-family: 'Consolas', 'Fira Code', monospace; font-size: 12px; padding: 8px; }}"
        )
        right_v.addWidget(self._mdx_edit)

        # Bottom action bar
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 4, 0, 4)

        clear_btn = QPushButton("Limpiar")
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_BASE}; border: 1px solid {theme.BORDER};"
            f"color: {theme.TEXT_DIM}; border-radius: 6px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ border-color: {theme.ERROR}; color: {theme.ERROR}; }}"
        )
        clear_btn.clicked.connect(self._on_clear)
        action_bar.addWidget(clear_btn)

        # Boton para guardar la consulta actual con nombre
        save_btn = QPushButton("Guardar")
        save_btn.setToolTip("Guardar consulta MDX con nombre")
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_BASE}; border: 1px solid {theme.BORDER};"
            f"color: {theme.BLUE}; border-radius: 6px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ border-color: {theme.BLUE}; }}"
        )
        save_btn.clicked.connect(self._on_save_query)
        action_bar.addWidget(save_btn)

        # Boton para alternar panel de historial
        self._hist_btn = QPushButton("Historial")
        self._hist_btn.setCheckable(True)
        self._hist_btn.setChecked(False)
        self._hist_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_BASE}; border: 1px solid {theme.BORDER};"
            f"color: {theme.TEXT_DIM}; border-radius: 6px; padding: 6px 16px; }}"
            f"QPushButton:checked {{ border-color: {theme.ACCENT}; color: {theme.ACCENT}; }}"
            f"QPushButton:hover {{ border-color: {theme.ACCENT}; }}"
        )
        self._hist_btn.toggled.connect(self._on_toggle_history)
        action_bar.addWidget(self._hist_btn)

        self._cardinality_lbl = QLabel("Cardinalidad: —")
        self._cardinality_lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 12px; padding: 0 12px;")
        action_bar.addWidget(self._cardinality_lbl)
        action_bar.addStretch()

        self._exec_btn = QPushButton("▶  Ejecutar consulta")
        self._exec_btn.setFixedHeight(38)
        self._exec_btn.setProperty("class", "primary")
        self._exec_btn.clicked.connect(self._on_execute)
        action_bar.addWidget(self._exec_btn)

        right_v.addLayout(action_bar)

        # Panel de historial (colapsado por defecto)
        self._history_panel = self._build_history_panel()
        self._history_panel.setVisible(False)
        right_v.addWidget(self._history_panel)

        main_splitter.addWidget(left)
        main_splitter.addWidget(right)
        main_splitter.setSizes([240, 700])
        root.addWidget(main_splitter, 1)

    def _add_pal_section(self, layout: QVBoxLayout, text: str):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; letter-spacing: 1px;"
            f"color: {theme.TEXT_DIM}; margin-top: 6px; background: transparent;"
        )
        layout.addWidget(lbl)

    def _make_zone_frame(self, title: str, accent_color: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"background: {theme.BG_BASE};")
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(4)
        hdr = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; letter-spacing: 1px;"
            f"color: {accent_color}; background: transparent;"
        )
        hdr.addWidget(lbl)
        hdr.addStretch()
        remove_btn = QPushButton("Vaciar")
        remove_btn.setFixedHeight(20)
        remove_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f"color: {theme.BORDER}; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {theme.ERROR}; }}"
        )
        hdr.addWidget(remove_btn)
        v.addLayout(hdr)
        # Store reference to zone so vaciar can clear it
        frame._remove_btn = remove_btn
        return frame

    def _connect_zone_clear(self, frame: QFrame, zone: _DropZone):
        frame._remove_btn.clicked.connect(zone.clear_zone)

    # ── History panel ─────────────────────────────────────────────────────────

    def _build_history_panel(self) -> QFrame:
        """Construye el panel colapsable de historial de consultas."""
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame {{ background: {theme.BG_SURFACE};"
            f"border-top: 1px solid {theme.BORDER}; }}"
        )
        v = QVBoxLayout(panel)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)

        # Encabezado
        hdr = QHBoxLayout()
        lbl = QLabel("HISTORIAL DE CONSULTAS")
        lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; letter-spacing: 1.2px;"
            f"color: {theme.TEXT_DIM}; background: transparent;"
        )
        hdr.addWidget(lbl)
        hdr.addStretch()
        v.addLayout(hdr)

        # Lista de consultas guardadas
        self._history_list = QListWidget()
        self._history_list.setFixedHeight(130)
        self._history_list.setStyleSheet(
            f"QListWidget {{ background: {theme.BG_DEEP}; border: 1px solid {theme.BORDER};"
            f"border-radius: 6px; }}"
            f"QListWidget::item {{ padding: 5px 8px; }}"
            f"QListWidget::item:hover {{ background: {theme.BG_SURFACE}; }}"
            f"QListWidget::item:selected {{ background: {theme.ACCENT_D}; color: white; }}"
        )
        # Nota: QListWidget en PyQt5 no tiene setPlaceholderText();
        # el texto "vacio" se maneja en _refresh_history() con un item no seleccionable.
        # Doble-click restaura el MDX al editor
        self._history_list.itemDoubleClicked.connect(self._on_load_query)
        v.addWidget(self._history_list)

        # Botones de accion del historial
        btn_row = QHBoxLayout()
        load_btn = QPushButton("Cargar")
        load_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_BASE}; border: 1px solid {theme.BORDER};"
            f"color: {theme.TEXT_DIM}; border-radius: 4px; padding: 4px 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ border-color: {theme.ACCENT}; color: {theme.ACCENT}; }}"
        )
        load_btn.clicked.connect(self._on_load_query)
        btn_row.addWidget(load_btn)

        del_btn = QPushButton("Eliminar")
        del_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_BASE}; border: 1px solid {theme.BORDER};"
            f"color: {theme.TEXT_DIM}; border-radius: 4px; padding: 4px 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ border-color: {theme.ERROR}; color: {theme.ERROR}; }}"
        )
        del_btn.clicked.connect(self._on_delete_history_item)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)

        return panel

    @pyqtSlot(bool)
    def _on_toggle_history(self, checked: bool):
        """Alterna visibilidad del panel de historial."""
        self._history_panel.setVisible(checked)
        if checked:
            self._refresh_history()

    def _refresh_history(self) -> None:
        """Repobla la lista con las consultas guardadas del catalogo activo."""
        if not hasattr(self, '_history_list'):
            return
        if not self._cache:
            return
        self._history_list.clear()
        try:
            queries = self._cache.list_queries(self._catalog)
        except Exception as exc:
            logger.error("Error al leer historial: %s", exc)
            return
        for q in queries:
            # No exponer la sesion automatica al usuario
            if q["name"] == _SESSION_SLOT:
                continue
            item = QListWidgetItem(f"{q['name']}")
            item.setToolTip(q["mdx"])
            item.setData(Qt.UserRole, q)   # dict con id, name, mdx, catalog
            item.setForeground(QColor(theme.TEXT))
            self._history_list.addItem(item)

        if self._history_list.count() == 0:
            placeholder = QListWidgetItem("No hay consultas guardadas")
            placeholder.setForeground(QColor(theme.TEXT_DIM))
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsSelectable)
            self._history_list.addItem(placeholder)

    @pyqtSlot()
    def _on_save_query(self) -> None:
        """Abre dialogo para nombrar y guardar la consulta MDX actual."""
        mdx = self._mdx_edit.toPlainText().strip()
        if not mdx:
            QMessageBox.warning(self, "Sin consulta", "No hay MDX para guardar.")
            return
        if not self._cache:
            QMessageBox.warning(self, "Cache no disponible",
                                "Conéctate primero para habilitar el guardado.")
            return

        name, ok = QInputDialog.getText(
            self, "Guardar consulta", "Nombre de la consulta:",
            QLineEdit.Normal, ""
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        if name == _SESSION_SLOT:
            QMessageBox.warning(self, "Nombre reservado",
                                f'El nombre "{_SESSION_SLOT}" está reservado.')
            return

        try:
            qid = self._cache.save_query(self._catalog, name, mdx)
            logger.info("Consulta guardada id=%s catalog=%s name=%r", qid, self._catalog, name)
            self._refresh_history()
            # Asegurar que el panel sea visible como confirmacion visual
            if not self._hist_btn.isChecked():
                self._hist_btn.setChecked(True)
        except Exception as exc:
            logger.error("Error guardando consulta: %s", exc)
            QMessageBox.critical(self, "Error", f"No se pudo guardar: {exc}")

    @pyqtSlot()
    def _on_load_query(self) -> None:
        """Carga la consulta seleccionada al editor MDX."""
        item = self._history_list.currentItem()
        if not item:
            return
        q = item.data(Qt.UserRole)
        if not q:
            return
        mdx = q.get("mdx", "")
        if mdx:
            self._mdx_edit.setPlainText(mdx)
            logger.info("Consulta cargada id=%s name=%r", q.get('id'), q.get('name'))

    @pyqtSlot()
    def _on_delete_history_item(self) -> None:
        """Elimina la entrada seleccionada del historial."""
        item = self._history_list.currentItem()
        if not item:
            return
        q = item.data(Qt.UserRole)
        if not q or not self._cache:
            return
        try:
            self._cache.delete_query(q["id"])
            logger.info("Consulta eliminada id=%s", q.get('id'))
            self._refresh_history()
        except Exception as exc:
            logger.error("Error eliminando consulta: %s", exc)

    # ── Session persistence (Fase 7.3) ────────────────────────────────────────

    def _save_session_state(self) -> None:
        """
        Persiste el MDX actual como sesion automatica.
        Sobreescribe el slot reservado si ya existia.
        """
        if not self._cache:
            return
        mdx = self._mdx_edit.toPlainText().strip()
        if not mdx:
            return
        try:
            # Eliminar sesion anterior del mismo catalogo
            existing = [
                q for q in self._cache.list_queries(self._catalog)
                if q["name"] == _SESSION_SLOT
            ]
            for q in existing:
                self._cache.delete_query(q["id"])
            self._cache.save_query(self._catalog, _SESSION_SLOT, mdx)
            logger.debug("Estado de sesion guardado para catalog=%s", self._catalog)
        except Exception as exc:
            logger.warning("No se pudo guardar sesion: %s", exc)

    def _restore_session_state(self) -> None:
        """
        Si existe una sesion previa para el catalogo activo, la carga al editor.
        Solo restaura si el editor esta vacio (no sobreescribe trabajo activo).
        """
        if not self._cache:
            return
        current_mdx = self._mdx_edit.toPlainText().strip()
        if current_mdx:
            return  # hay trabajo activo, no sobreescribir
        try:
            sessions = [
                q for q in self._cache.list_queries(self._catalog)
                if q["name"] == _SESSION_SLOT
            ]
            if sessions:
                mdx = sessions[0]["mdx"]
                self._mdx_edit.setPlainText(mdx)
                logger.info("Sesion previa restaurada para catalog=%s", self._catalog)
        except Exception as exc:
            logger.warning("No se pudo restaurar sesion: %s", exc)

    # ── Quick add (double click) ──────────────────────────────────────────────

    def _quick_add(self, item: QListWidgetItem, zone: _DropZone):
        uname = item.data(ROLE_UNAME) or ""
        kind  = item.data(ROLE_KIND) or ""
        text  = item.text().strip()
        zone.add_item_programmatic(text, uname, kind)

    @pyqtSlot(QTreeWidgetItem, int)
    def _on_dim_double_click(self, item: QTreeWidgetItem, _col: int):
        uname = item.data(0, ROLE_UNAME)
        kind  = item.data(0, ROLE_KIND)
        text  = item.text(0).strip()
        if uname and kind:
            self._rows_zone.add_item_programmatic(text, uname, kind)

    # ── MDX generation ────────────────────────────────────────────────────────

    @pyqtSlot()
    def _rebuild_mdx(self):
        cols = self._cols_zone.get_unique_names()
        col_kinds = self._cols_zone.get_kinds()
        rows = self._rows_zone.get_unique_names()
        row_kinds = self._rows_zone.get_kinds()
        fils = self._filters_zone.get_unique_names()
        fil_kinds = self._filters_zone.get_kinds()

        cube = self._cube or self._catalog
        mdx = build_mdx(self._catalog, cube, cols, col_kinds, rows, row_kinds, fils, fil_kinds)
        self._mdx_edit.setPlainText(mdx)

        # Estimate cardinality
        if self._provider and (cols or rows):
            dims = [{"unique_name": u, "kind": k}
                    for u, k in zip(rows + cols, row_kinds + col_kinds)
                    if k != "measure"]
            try:
                card = self._provider.estimate_cardinality(self._catalog, dims)
                if card and card > 0:
                    self._cardinality_lbl.setText(f"Cardinalidad est.: ~{card:,}")
                else:
                    self._cardinality_lbl.setText("Cardinalidad: —")
            except Exception:
                self._cardinality_lbl.setText("Cardinalidad: —")

    # ── Actions ───────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_clear(self):
        self._cols_zone.clear_zone()
        self._rows_zone.clear_zone()
        self._filters_zone.clear_zone()
        self._mdx_edit.clear()
        self._cardinality_lbl.setText("Cardinalidad: —")

    @pyqtSlot()
    def _on_execute(self):
        mdx = self._mdx_edit.toPlainText().strip()
        if not mdx:
            return
        # Persistir estado de sesion antes de ejecutar (Fase 7.3)
        self._save_session_state()
        self.execute_query.emit(self._catalog, mdx)

    # ── Public reset ─────────────────────────────────────────────────────────

    def set_executing(self, running: bool):
        self._exec_btn.setEnabled(not running)
        self._exec_btn.setText("Ejecutando…" if running else "▶  Ejecutar consulta")

    def get_mdx(self) -> str:
        return self._mdx_edit.toPlainText()

    def reset(self):
        """Limpia zonas pero conserva el catalogo/provider."""
        self._on_clear()
