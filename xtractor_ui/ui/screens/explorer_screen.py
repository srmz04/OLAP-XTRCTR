"""
ExplorerScreen: explorador de metadata OLAP con arbol lazy-load.
Panel izquierdo: arbol (catalogo > dimensiones > jerarquias > niveles / medidas).
Panel derecho: detalle del item seleccionado.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.cache import MetadataCache
from core.provider import (
    CatalogInfo, DimensionInfo, LevelInfo, MeasureInfo, MemberInfo,
)
from ui import theme


# ── Background loaders ────────────────────────────────────────────────────────

class _HierarchiesLoader(QThread):
    done = pyqtSignal(list, list)  # hierarchies, measures
    error = pyqtSignal(str)

    def __init__(self, provider, catalog: str):
        super().__init__()
        self._provider = provider
        self._catalog = catalog
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            h = self._provider.list_hierarchies(self._catalog)
            m = self._provider.list_measures(self._catalog)
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))
            return
        if not self._cancelled:
            self.done.emit(h, m)


class _MembersLoader(QThread):
    done = pyqtSignal(str, list)  # node_id, members
    error = pyqtSignal(str)

    def __init__(self, provider, catalog, dimension, hierarchy, level, node_id):
        super().__init__()
        self._provider = provider
        self._catalog = catalog
        self._dim = dimension
        self._hier = hierarchy
        self._level = level
        self._node_id = node_id
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            members = self._provider.list_members(
                self._catalog, self._dim, self._hier, self._level
            )
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))
            return
        if not self._cancelled:
            self.done.emit(self._node_id, members)


# ── Tree item types ───────────────────────────────────────────────────────────

ROLE_TYPE   = Qt.UserRole
ROLE_DATA   = Qt.UserRole + 1
ROLE_NODEID = Qt.UserRole + 2

TYPE_CATALOG   = "catalog"
TYPE_DIMENSION = "dimension"
TYPE_HIERARCHY = "hierarchy"
TYPE_LEVEL     = "level"
TYPE_MEMBER    = "member"
TYPE_MEASURE   = "measure"
TYPE_GROUP     = "group"


# ── Screen ─────────────────────────────────────────────────────────────────────

class ExplorerScreen(QWidget):
    """
    Señales:
      build_query(context: dict)  — navegar al builder con contexto
      go_back()                   — volver a conexion
    """
    build_query = pyqtSignal(object)
    go_back = pyqtSignal()

    def __init__(self, provider=None, catalog: str = "", cache: Optional[MetadataCache] = None, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._catalog = catalog
        self._cache = cache or MetadataCache()
        self._loading_threads: Dict[str, QThread] = {}
        self._loaded_hierarchies: list = []
        self._loaded_measures: list = []
        self._build_ui()

    def set_provider(self, provider, catalog: str = ""):
        self._provider = provider
        self._catalog = catalog
        self._load_catalog()

    def load_from_cache(self, catalog: str = "DEMO_CUBE"):
        """Carga metadata enteramente del cache SQLite, sin provider."""
        self._catalog = catalog
        self._title_lbl.setText(f"Explorador — {catalog}")
        cached = self._load_meta_from_cache(catalog)
        if cached:
            hiers, measures = cached
            self._on_hierarchies_loaded(hiers, measures, from_cache=True)
        else:
            self._status_lbl.setText("Cache vacia — ejecuta seed_cache.py primero")

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
        tb.addStretch()

        self._title_lbl = QLabel("Explorador de Metadata")
        self._title_lbl.setStyleSheet(f"color: {theme.TEXT}; font-size: 15px; font-weight: 700;")
        tb.addWidget(self._title_lbl)
        tb.addStretch()

        self._build_btn = QPushButton("Construir consulta →")
        self._build_btn.setEnabled(False)
        self._build_btn.setProperty("class", "primary")
        self._build_btn.clicked.connect(self._on_build)
        tb.addWidget(self._build_btn)

        root.addWidget(topbar)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {theme.BORDER}; }}"
                               f"QSplitter::handle:hover {{ background: {theme.ACCENT}; }}")

        # Left panel
        left = QFrame()
        left.setStyleSheet(f"background: {theme.BG_BASE};")
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(12, 12, 8, 12)
        left_v.setSpacing(8)

        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Buscar dimensiones, medidas…")
        self._search_edit.setFixedHeight(32)
        self._search_edit.textChanged.connect(self._on_search)
        search_row.addWidget(self._search_edit)
        left_v.addLayout(search_row)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setExpandsOnDoubleClick(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        left_v.addWidget(self._tree)

        # Right panel
        right = QFrame()
        right.setStyleSheet(f"background: {theme.BG_BASE};")
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(12, 12, 12, 12)
        right_v.setSpacing(8)

        detail_title = QLabel("DETALLE")
        detail_title.setStyleSheet(
            f"font-size: 10px; font-weight: 700; letter-spacing: 1.5px;"
            f"color: {theme.TEXT_DIM}; margin-bottom: 4px;"
        )
        right_v.addWidget(detail_title)

        self._detail_frame = QFrame()
        self._detail_frame.setStyleSheet(
            f"background: {theme.BG_SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 10px;"
        )
        self._detail_v = QVBoxLayout(self._detail_frame)
        self._detail_v.setContentsMargins(20, 20, 20, 20)
        self._detail_v.setSpacing(8)
        self._detail_placeholder()
        right_v.addWidget(self._detail_frame, 1)
        right_v.addStretch()

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([340, 460])

        root.addWidget(splitter, 1)

        # Status
        self._status_lbl = QLabel("Cargando metadata…")
        self._status_lbl.setFixedHeight(28)
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setStyleSheet(
            f"background: {theme.BG_SURFACE}; border-top: 1px solid {theme.BORDER};"
            f"color: {theme.TEXT_DIM}; font-size: 12px; padding: 4px;"
        )
        root.addWidget(self._status_lbl)

    # ── Catalog loading ───────────────────────────────────────────────────────

    def _load_catalog(self):
        if not self._provider:
            return
        catalog = self._catalog
        if not catalog:
            try:
                cats = self._provider.list_catalogs()
                catalog = cats[0].name if cats else ""
            except Exception:
                catalog = ""
        self._catalog = catalog
        self._title_lbl.setText(f"Explorador — {catalog}" if catalog else "Explorador")

        # Si el cache tiene datos frescos, cargar directo
        if self._cache and not self._cache.is_stale(catalog):
            cached = self._load_meta_from_cache(catalog)
            if cached:
                hiers, measures = cached
                self._on_hierarchies_loaded(hiers, measures, from_cache=True)
                return

        self._status_lbl.setText("Cargando metadata…")
        self._tree.clear()

        loader = _HierarchiesLoader(self._provider, catalog)
        loader.done.connect(self._on_hierarchies_loaded)
        loader.error.connect(self._on_load_error)
        loader.finished.connect(loader.deleteLater)
        self._hier_loader = loader
        loader.start()

        # Timeout: si no responde en 30s, permitir cancelar
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_load_timeout)
        self._timeout_timer.start(30_000)

    def _stop_timeout(self):
        if hasattr(self, '_timeout_timer') and self._timeout_timer.isActive():
            self._timeout_timer.stop()

    @pyqtSlot(str)
    def _on_load_error(self, msg: str):
        self._stop_timeout()
        self._status_lbl.setText(f"Error: {msg[:100]}")
        self._status_lbl.setStyleSheet(
            f"background: {theme.BG_SURFACE}; border-top: 1px solid {theme.BORDER};"
            f"color: {theme.ERROR}; font-size: 12px; padding: 4px;"
        )

    @pyqtSlot()
    def _on_load_timeout(self):
        self._status_lbl.setText("El servidor no responde. Puedes volver y reintentar.")
        self._status_lbl.setStyleSheet(
            f"background: {theme.BG_SURFACE}; border-top: 1px solid {theme.BORDER};"
            f"color: {theme.WARN}; font-size: 12px; padding: 4px;"
        )
        # Cancelar loader para que ignore su resultado si llega tarde
        if hasattr(self, '_hier_loader') and self._hier_loader.isRunning():
            self._hier_loader.cancel()

    # ── Cache serialization ────────────────────────────────────────────────────

    @staticmethod
    def _serialize_meta(hierarchies: list, measures: list) -> dict:
        hiers = []
        for d in hierarchies:
            hiers.append({
                "dimension": d.dimension, "hierarchy": d.hierarchy,
                "display_name": d.display_name,
                "levels": [{"name": lv.name, "depth": lv.depth} for lv in d.levels],
            })
        meas = [{"id": m.id, "name": m.name, "caption": m.caption,
                 "aggregator": m.aggregator} for m in measures]
        return {"hierarchies": hiers, "measures": meas}

    @staticmethod
    def _deserialize_meta(data: dict):
        hiers = []
        for h in data.get("hierarchies", []):
            hiers.append(DimensionInfo(
                dimension=h["dimension"], hierarchy=h["hierarchy"],
                display_name=h["display_name"],
                levels=[LevelInfo(name=lv["name"], depth=lv["depth"])
                        for lv in h.get("levels", [])],
            ))
        measures = [MeasureInfo(id=m["id"], name=m["name"], caption=m["caption"],
                                aggregator=m.get("aggregator", ""))
                    for m in data.get("measures", [])]
        return hiers, measures

    def _load_meta_from_cache(self, catalog: str):
        """Intenta cargar hierarchies+measures del cache. Retorna (hiers, measures) o None."""
        data = self._cache.get_catalog_meta(catalog)
        if not data or "hierarchies" not in data:
            return None
        return self._deserialize_meta(data)

    # ── Hierarchies loaded ─────────────────────────────────────────────────────

    @pyqtSlot(list, list)
    def _on_hierarchies_loaded(self, hierarchies: list, measures: list, from_cache: bool = False):
        self._stop_timeout()
        self._tree.clear()
        catalog = self._catalog
        self._loaded_hierarchies = hierarchies
        self._loaded_measures = measures

        # Persistir al cache si vino del provider
        if not from_cache and self._cache:
            meta = self._serialize_meta(hierarchies, measures)
            self._cache.touch_catalog(catalog, meta)

        # ── Medidas group ──────────────────────────────────────────
        if measures:
            measures_root = QTreeWidgetItem(self._tree, ["📊 Medidas"])
            measures_root.setData(0, ROLE_TYPE, TYPE_GROUP)
            measures_root.setData(0, ROLE_DATA, {"catalog": catalog})
            measures_root.setForeground(0, self._color_fg(theme.GROUP_MEAS))
            font = measures_root.font(0)
            font.setBold(True)
            measures_root.setFont(0, font)
            for m in measures:
                child = QTreeWidgetItem(measures_root, [f"∑  {m.caption}"])
                child.setData(0, ROLE_TYPE, TYPE_MEASURE)
                child.setData(0, ROLE_DATA, m)
                child.setToolTip(0, m.id)
                child.setForeground(0, self._color_fg(theme.MEASURE))

        # ── Dimensions ─────────────────────────────────────────────
        dims_root = QTreeWidgetItem(self._tree, ["⬡ Dimensiones"])
        dims_root.setData(0, ROLE_TYPE, TYPE_GROUP)
        dims_root.setForeground(0, self._color_fg(theme.GROUP_DIM))
        font2 = dims_root.font(0)
        font2.setBold(True)
        dims_root.setFont(0, font2)

        dim_map: Dict[str, QTreeWidgetItem] = {}
        for dim_info in hierarchies:
            dim_name = dim_info.dimension
            if dim_name not in dim_map:
                dim_item = QTreeWidgetItem(dims_root, [f"  {dim_name}"])
                dim_item.setData(0, ROLE_TYPE, TYPE_DIMENSION)
                dim_item.setData(0, ROLE_DATA, {"catalog": catalog, "dimension": dim_name})
                dim_item.setForeground(0, self._color_fg(theme.DIM))
                dim_map[dim_name] = dim_item

            hier_item = QTreeWidgetItem(dim_map[dim_name], [f"  {dim_info.hierarchy}"])
            hier_item.setData(0, ROLE_TYPE, TYPE_HIERARCHY)
            hier_item.setData(0, ROLE_DATA, dim_info)
            hier_item.setForeground(0, self._color_fg(theme.HIER))

            for level in dim_info.levels:
                lv_item = QTreeWidgetItem(hier_item, [f"    {level.name}"])
                lv_item.setData(0, ROLE_TYPE, TYPE_LEVEL)
                lv_item.setData(0, ROLE_DATA, {
                    "catalog": catalog,
                    "dim_info": dim_info,
                    "level": level,
                })
                lv_item.setForeground(0, self._color_fg(theme.LEVEL))
                lv_item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

        self._tree.expandItem(dims_root)
        if measures:
            self._tree.expandItem(measures_root)

        count_d = len(dim_map)
        count_m = len(measures)
        source = "cache" if from_cache else "servidor"
        self._status_lbl.setText(
            f"{catalog}  ·  {count_d} dimensiones  ·  {count_m} medidas  ({source})"
        )
        self._build_btn.setEnabled(True)

    # ── Lazy member load ──────────────────────────────────────────────────────

    @pyqtSlot(QTreeWidgetItem)
    def _on_item_expanded(self, item: QTreeWidgetItem):
        if item.data(0, ROLE_TYPE) != TYPE_LEVEL:
            return
        if item.childCount() > 0:
            return  # already loaded
        data = item.data(0, ROLE_DATA)
        dim_info: DimensionInfo = data["dim_info"]
        level = data["level"]

        # Intentar cargar del cache primero
        if self._cache and self._cache.has_members(
            self._catalog, dim_info.dimension, dim_info.hierarchy, level.name
        ):
            cached = self._cache.get_members(
                self._catalog, dim_info.dimension, dim_info.hierarchy, level.name
            )
            members = [MemberInfo(caption=m["caption"], unique_name=m["unique_name"])
                       for m in cached]
            self._on_members_loaded(item, members)
            return

        if not self._provider:
            placeholder = QTreeWidgetItem(item, ["Sin datos offline — ejecuta consulta para cargar"])
            placeholder.setForeground(0, self._color_fg(theme.TEXT_DIM))
            return

        node_id = id(item)
        loader = _MembersLoader(
            self._provider,
            self._catalog,
            dim_info.dimension,
            dim_info.hierarchy,
            level.name,
            str(node_id),
        )
        loader.done.connect(lambda nid, members, i=item, di=dim_info, lv=level:
                            self._on_members_loaded(i, members, di, lv))
        loader.finished.connect(loader.deleteLater)
        loader.finished.connect(lambda nid=str(node_id): self._loading_threads.pop(nid, None))
        self._loading_threads[str(node_id)] = loader

        placeholder = QTreeWidgetItem(item, ["Cargando…"])
        placeholder.setForeground(0, self._color_fg(theme.TEXT_DIM))
        loader.start()

    def _on_members_loaded(self, item: QTreeWidgetItem, members: list,
                           dim_info: Optional[DimensionInfo] = None,
                           level: Optional[LevelInfo] = None):
        # Remove placeholder
        while item.childCount():
            item.removeChild(item.child(0))

        # Persistir al cache si tenemos contexto (= vino del provider, no del cache)
        if dim_info and level and self._cache and members:
            self._cache.save_members(
                self._catalog, dim_info.dimension, dim_info.hierarchy, level.name,
                [{"caption": m.caption, "unique_name": m.unique_name} for m in members],
            )

        for m in members[:500]:
            child = QTreeWidgetItem(item, [f"      {m.caption}"])
            child.setData(0, ROLE_TYPE, TYPE_MEMBER)
            child.setData(0, ROLE_DATA, m)
            child.setToolTip(0, m.unique_name)
            child.setForeground(0, self._color_fg(theme.MEMBER))
        if len(members) > 500:
            more = QTreeWidgetItem(item, [f"      … y {len(members)-500} más"])
            more.setForeground(0, self._color_fg(theme.TEXT_DIM))

    # ── Search ────────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def _on_search(self, text: str):
        text = text.lower().strip()
        self._filter_tree(self._tree.invisibleRootItem(), text)

    def _filter_tree(self, parent: QTreeWidgetItem, text: str) -> bool:
        any_visible = False
        for i in range(parent.childCount()):
            child = parent.child(i)
            label = child.text(0).lower()
            child_visible = self._filter_tree(child, text)
            visible = (not text) or text in label or child_visible
            child.setHidden(not visible)
            if visible:
                any_visible = True
        return any_visible

    # ── Selection & detail ────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_selection_changed(self):
        items = self._tree.selectedItems()
        if not items:
            self._detail_placeholder()
            return
        item = items[0]
        itype = item.data(0, ROLE_TYPE)
        data = item.data(0, ROLE_DATA)
        self._show_detail(itype, data)

    @pyqtSlot(QTreeWidgetItem, int)
    def _on_item_double_clicked(self, item: QTreeWidgetItem, _col: int):
        itype = item.data(0, ROLE_TYPE)
        if itype in (TYPE_MEASURE, TYPE_HIERARCHY, TYPE_LEVEL):
            self._on_build()

    def _detail_placeholder(self):
        self._clear_detail()
        lbl = QLabel("Selecciona un elemento del arbol para ver su detalle.")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 13px;")
        self._detail_v.addWidget(lbl)
        self._detail_v.addStretch()

    def _clear_detail(self):
        while self._detail_v.count():
            item = self._detail_v.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_detail(self, itype: str, data: Any):
        self._clear_detail()

        def row(label: str, value: str):
            h = QHBoxLayout()
            lbl = QLabel(label + ":")
            lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px; font-weight: 600;")
            lbl.setFixedWidth(120)
            h.addWidget(lbl)
            val = QLabel(value)
            val.setWordWrap(True)
            val.setStyleSheet(f"color: {theme.TEXT}; font-size: 12px;")
            h.addWidget(val, 1)
            return h

        type_labels = {
            TYPE_MEASURE: ("Medida", theme.MEASURE),
            TYPE_DIMENSION: ("Dimension", theme.DIM),
            TYPE_HIERARCHY: ("Jerarquia", theme.HIER),
            TYPE_LEVEL: ("Nivel", theme.LEVEL),
            TYPE_MEMBER: ("Miembro", theme.TEXT),
            TYPE_GROUP: ("Grupo", theme.TEXT_DIM),
        }
        type_label, type_color = type_labels.get(itype, ("?", theme.TEXT_DIM))

        type_pill = QLabel(type_label)
        type_pill.setFixedHeight(24)
        type_pill.setAlignment(Qt.AlignCenter)
        type_pill.setStyleSheet(
            f"background: {theme.BG_DEEP}; border: 1px solid {type_color};"
            f"color: {type_color}; border-radius: 12px; font-size: 11px;"
            "font-weight: 700; padding: 0 12px;"
        )
        type_pill.setFixedWidth(100)
        pill_row = QHBoxLayout()
        pill_row.addWidget(type_pill)
        pill_row.addStretch()
        self._detail_v.addLayout(pill_row)
        self._detail_v.addSpacing(12)

        if itype == TYPE_MEASURE and hasattr(data, "caption"):
            self._detail_v.addLayout(row("Nombre", data.name))
            self._detail_v.addLayout(row("Caption", data.caption))
            self._detail_v.addLayout(row("ID", data.id))
            self._detail_v.addLayout(row("Agregacion", data.aggregator or "—"))
        elif itype == TYPE_HIERARCHY and hasattr(data, "hierarchy"):
            self._detail_v.addLayout(row("Dimension", data.dimension))
            self._detail_v.addLayout(row("Jerarquia", data.hierarchy))
            self._detail_v.addLayout(row("Display", data.display_name))
            self._detail_v.addLayout(row("Niveles", str(len(data.levels))))
        elif itype == TYPE_LEVEL:
            level = data.get("level")
            dim_info = data.get("dim_info")
            if level:
                self._detail_v.addLayout(row("Nivel", level.name))
                self._detail_v.addLayout(row("Profundidad", str(level.depth)))
            if dim_info:
                self._detail_v.addLayout(row("Dimension", dim_info.dimension))
                self._detail_v.addLayout(row("Jerarquia", dim_info.hierarchy))
        elif itype == TYPE_MEMBER and hasattr(data, "caption"):
            self._detail_v.addLayout(row("Caption", data.caption))
            self._detail_v.addLayout(row("Unique Name", data.unique_name))
        else:
            info = QLabel(str(data)[:200])
            info.setWordWrap(True)
            info.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 12px;")
            self._detail_v.addWidget(info)

        self._detail_v.addStretch()

    # ── Build query ───────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_build(self):
        items = self._tree.selectedItems()
        selected_data = None
        selected_type = None
        if items:
            selected_data = items[0].data(0, ROLE_DATA)
            selected_type = items[0].data(0, ROLE_TYPE)

        context = {
            "catalog": self._catalog,
            "provider": self._provider,
            "hierarchies": self._loaded_hierarchies,
            "measures": self._loaded_measures,
            "selected_type": selected_type,
            "selected_data": selected_data,
        }
        self.build_query.emit(context)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _color_fg(hex_color: str):
        return QColor(hex_color)
