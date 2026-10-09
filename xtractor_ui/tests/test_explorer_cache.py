"""Tests de integracion: ExplorerScreen + MetadataCache."""
from __future__ import annotations

import sys
from pathlib import Path


import pytest
from core.cache import MetadataCache
from core.provider import DimensionInfo, LevelInfo, MeasureInfo, MemberInfo
from ui.screens.explorer_screen import ExplorerScreen


@pytest.fixture
def tmp_cache(tmp_path):
    return MetadataCache(tmp_path / "test.db")


# ── Serialization round-trip ─────────────────────────────────────────────────

def test_serialize_deserialize_roundtrip():
    hiers = [
        DimensionInfo(
            dimension="DIM1", hierarchy="H1", display_name="Dim One",
            levels=[LevelInfo(name="L1", depth=0), LevelInfo(name="L2", depth=1)],
        ),
    ]
    measures = [
        MeasureInfo(id="[M1]", name="M1", caption="Measure One", aggregator="SUM"),
    ]
    data = ExplorerScreen._serialize_meta(hiers, measures)
    h2, m2 = ExplorerScreen._deserialize_meta(data)

    assert len(h2) == 1
    assert h2[0].dimension == "DIM1"
    assert h2[0].hierarchy == "H1"
    assert len(h2[0].levels) == 2
    assert h2[0].levels[1].name == "L2"
    assert h2[0].levels[1].depth == 1

    assert len(m2) == 1
    assert m2[0].id == "[M1]"
    assert m2[0].caption == "Measure One"
    assert m2[0].aggregator == "SUM"


def test_cache_stores_and_retrieves_meta(tmp_cache):
    hiers = [
        DimensionInfo(
            dimension="DIM_A", hierarchy="HA", display_name="A",
            levels=[LevelInfo(name="All", depth=0)],
        ),
    ]
    measures = [MeasureInfo(id="[MA]", name="MA", caption="Medida A")]
    meta = ExplorerScreen._serialize_meta(hiers, measures)
    tmp_cache.touch_catalog("TEST_CAT", meta)

    assert not tmp_cache.is_stale("TEST_CAT")

    # Leer de vuelta
    row = tmp_cache._db.execute(
        "SELECT data_json FROM catalog_meta WHERE catalog = ?", ("TEST_CAT",)
    ).fetchone()
    import json
    data = json.loads(row[0])
    h2, m2 = ExplorerScreen._deserialize_meta(data)
    assert h2[0].dimension == "DIM_A"
    assert m2[0].caption == "Medida A"


def test_cache_members_roundtrip(tmp_cache):
    members = [
        {"caption": "Aguascalientes", "unique_name": "[GEO].[AGS]"},
        {"caption": "Baja California", "unique_name": "[GEO].[BC]"},
    ]
    tmp_cache.save_members("CAT", "GEO", "HIER", "Estado", members)
    assert tmp_cache.has_members("CAT", "GEO", "HIER", "Estado")

    loaded = tmp_cache.get_members("CAT", "GEO", "HIER", "Estado")
    assert len(loaded) == 2
    assert loaded[0]["caption"] == "Aguascalientes"
    assert loaded[1]["unique_name"] == "[GEO].[BC]"
