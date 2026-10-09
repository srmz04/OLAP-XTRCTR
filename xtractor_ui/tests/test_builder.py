"""Tests del builder MDX — logica pura y Sprint 7 (historial)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ui.screens.builder_screen import build_mdx, BuilderScreen, _SESSION_SLOT


def test_single_measure_no_rows():
    mdx = build_mdx(
        catalog="DEMO_CUBE", cube="DEMO_CUBE",
        columns=["[Measures].[Total]"], col_kinds=["measure"],
        rows=[], row_kinds=[],
        filters=[], filter_kinds=[],
    )
    assert "[Measures].[Total]" in mdx
    assert "ON COLUMNS" in mdx
    assert "DEMO_CUBE" in mdx
    assert "ON ROWS" not in mdx


def test_measure_with_one_row_dim():
    mdx = build_mdx(
        catalog="DEMO_CUBE", cube="DEMO_CUBE",
        columns=["[Measures].[Total]"], col_kinds=["measure"],
        rows=["[DIM TIEMPO].[Mes]"], row_kinds=["hierarchy"],
        filters=[], filter_kinds=[],
    )
    assert "ON COLUMNS" in mdx
    assert "ON ROWS" in mdx
    assert "[DIM TIEMPO].[Mes]" in mdx
    assert "NON EMPTY" in mdx


def test_crossjoin_two_dims():
    mdx = build_mdx(
        catalog="DEMO_CUBE", cube="DEMO_CUBE",
        columns=["[Measures].[Total]"], col_kinds=["measure"],
        rows=["[DIM TIEMPO].[Mes]", "[DIM ESTADO].[Estado]"],
        row_kinds=["hierarchy", "hierarchy"],
        filters=[], filter_kinds=[],
    )
    assert "CROSSJOIN" in mdx
    assert "[DIM TIEMPO].[Mes]" in mdx
    assert "[DIM ESTADO].[Estado]" in mdx


def test_where_filter():
    mdx = build_mdx(
        catalog="DEMO_CUBE", cube="DEMO_CUBE",
        columns=["[Measures].[Total]"], col_kinds=["measure"],
        rows=["[DIM TIEMPO].[Mes]"], row_kinds=["hierarchy"],
        filters=["[DIM ESTADO].[Estado].&[09]"], filter_kinds=["hierarchy"],
    )
    assert "WHERE" in mdx
    assert "[DIM ESTADO].[Estado].&[09]" in mdx


def test_empty_columns_produces_empty_set():
    mdx = build_mdx(
        catalog="DEMO_CUBE", cube="DEMO_CUBE",
        columns=[], col_kinds=[],
        rows=[], row_kinds=[],
        filters=[], filter_kinds=[],
    )
    assert "{}" in mdx
    assert "DEMO_CUBE" in mdx


def test_cube_defaults_to_catalog_when_empty():
    mdx = build_mdx(
        catalog="DEMO_CUBE", cube="",
        columns=["[Measures].[X]"], col_kinds=["measure"],
        rows=[], row_kinds=[],
        filters=[], filter_kinds=[],
    )
    assert "DEMO_CUBE" in mdx


def test_members_suffix_added_to_hierarchy():
    mdx = build_mdx(
        catalog="DEMO_CUBE", cube="DEMO_CUBE",
        columns=["[Measures].[Total]"], col_kinds=["measure"],
        rows=["[DIM TIEMPO].[Mes]"], row_kinds=["hierarchy"],
        filters=[], filter_kinds=[],
    )
    assert "[DIM TIEMPO].[Mes].Members" in mdx


def test_measures_not_get_members_suffix():
    mdx = build_mdx(
        catalog="DEMO_CUBE", cube="DEMO_CUBE",
        columns=["[Measures].[Total]"], col_kinds=["measure"],
        rows=[], row_kinds=[],
        filters=[], filter_kinds=[],
    )
    assert "[Measures].[Total].Members" not in mdx
    assert "[Measures].[Total]" in mdx


def test_special_chars_in_dimension_name():
    """Nombres con corchetes y caracteres especiales no rompen el MDX."""
    mdx = build_mdx(
        catalog="DEMO_CUBE", cube="DEMO_CUBE",
        columns=["[Measures].[Total]"], col_kinds=["measure"],
        rows=["[DIM VARIABLES2025].[Apartado y Variable]"], row_kinds=["hierarchy"],
        filters=[], filter_kinds=[],
    )
    assert "[DIM VARIABLES2025].[Apartado y Variable].Members" in mdx
    assert "ON ROWS" in mdx


def test_filter_measure_excluded_from_where():
    """Medidas en filtros no deben ir al WHERE (solo dimensiones)."""
    mdx = build_mdx(
        catalog="C", cube="C",
        columns=["[Measures].[X]"], col_kinds=["measure"],
        rows=[], row_kinds=[],
        filters=["[Measures].[Y]", "[DIM].[H].&[1]"],
        filter_kinds=["measure", "hierarchy"],
    )
    assert "WHERE" in mdx
    assert "[DIM].[H].&[1]" in mdx
    assert "[Measures].[Y]" not in mdx.split("WHERE")[1]


# ── Sprint 7: historial y guardado ────────────────────────────────────────────


def test_builder_save_query_calls_cache(qtbot, tmp_cache):
    """
    Si el editor tiene MDX y la cache esta inyectada,
    _on_save_query guarda en la cache.
    El test usa mock de QInputDialog para no necesitar interaccion del usuario.
    """
    widget = BuilderScreen()
    qtbot.addWidget(widget)
    widget.set_cache(tmp_cache)
    widget._catalog = "DEMO_CUBE"

    # Precarga MDX en el editor
    test_mdx = "SELECT {[Measures].[X]} ON COLUMNS FROM [DEMO_CUBE]"
    widget._mdx_edit.setPlainText(test_mdx)

    # Simular que el usuario escribe "Consulta prueba" en el dialogo
    with patch("ui.screens.builder_screen.QInputDialog.getText",
               return_value=("Consulta prueba", True)):
        widget._on_save_query()

    queries = tmp_cache.list_queries("DEMO_CUBE")
    assert any(q["name"] == "Consulta prueba" for q in queries)
    assert any(q["mdx"] == test_mdx for q in queries)


def test_builder_load_query_from_dict(qtbot, tmp_cache):
    """
    Doble-click en un item de historial restaura el MDX en el editor.
    """
    widget = BuilderScreen()
    qtbot.addWidget(widget)
    widget.set_cache(tmp_cache)
    widget._catalog = "DEMO_CUBE"

    # Guardar una consulta directamente en la cache
    mdx_a = "SELECT {[Measures].[Y]} ON COLUMNS FROM [DEMO_CUBE]"
    tmp_cache.save_query("DEMO_CUBE", "Mi consulta A", mdx_a)

    # Abrir historial y cargar la consulta
    widget._refresh_history()
    assert widget._history_list.count() == 1

    # Seleccionar el item y llamar _on_load_query (equivale a doble-click)
    widget._history_list.setCurrentRow(0)
    widget._on_load_query()

    assert widget._mdx_edit.toPlainText() == mdx_a


def test_session_slot_not_shown_in_history(qtbot, tmp_cache):
    """
    Las entradas reservadas (~session~) no deben aparecer en la lista de historial.
    """
    widget = BuilderScreen()
    qtbot.addWidget(widget)
    widget.set_cache(tmp_cache)
    widget._catalog = "DEMO_CUBE"

    # Guardar una sesion automatica y una consulta normal
    tmp_cache.save_query("DEMO_CUBE", _SESSION_SLOT, "SELECT {} ON COLUMNS FROM [X]")
    tmp_cache.save_query("DEMO_CUBE", "Normal", "SELECT {} ON COLUMNS FROM [Y]")

    widget._refresh_history()

    texts = [widget._history_list.item(i).text()
             for i in range(widget._history_list.count())]
    assert _SESSION_SLOT not in texts
    assert "Normal" in texts
