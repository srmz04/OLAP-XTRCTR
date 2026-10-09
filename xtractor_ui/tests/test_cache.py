"""Tests del MetadataCache."""
from __future__ import annotations
import sys
from pathlib import Path

from core.cache import MetadataCache


def test_new_cache_is_stale(tmp_cache):
    assert tmp_cache.is_stale("DEMO_CUBE") is True


def test_touch_marks_fresh(tmp_cache):
    tmp_cache.touch_catalog("DEMO_CUBE", {"cubes": 1})
    assert tmp_cache.is_stale("DEMO_CUBE", max_age_hours=1) is False


def test_save_and_get_members(tmp_cache):
    members = [
        {"caption": "Enero", "unique_name": "[DIM TIEMPO].[Mes].&[1]"},
        {"caption": "Febrero", "unique_name": "[DIM TIEMPO].[Mes].&[2]"},
    ]
    count = tmp_cache.save_members("DEMO_CUBE", "[DIM TIEMPO]", "[DIM TIEMPO].[Mes]", "Mes", members)
    assert count == 2

    result = tmp_cache.get_members("DEMO_CUBE", "[DIM TIEMPO]", "[DIM TIEMPO].[Mes]", "Mes")
    assert len(result) == 2
    assert result[0]["caption"] == "Enero"
    assert result[1]["unique_name"] == "[DIM TIEMPO].[Mes].&[2]"


def test_has_members(tmp_cache):
    assert tmp_cache.has_members("DEMO_CUBE", "[DIM TIEMPO]", "[DIM TIEMPO].[Mes]", "Mes") is False
    tmp_cache.save_members("DEMO_CUBE", "[DIM TIEMPO]", "[DIM TIEMPO].[Mes]", "Mes",
                           [{"caption": "Ene", "unique_name": "[X].[Y].&[1]"}])
    assert tmp_cache.has_members("DEMO_CUBE", "[DIM TIEMPO]", "[DIM TIEMPO].[Mes]", "Mes") is True


def test_save_and_list_queries(tmp_cache):
    qid = tmp_cache.save_query("DEMO_CUBE", "Mi consulta", "SELECT {} ON COLUMNS FROM [DEMO_CUBE]")
    assert qid > 0

    queries = tmp_cache.list_queries("DEMO_CUBE")
    assert len(queries) == 1
    assert queries[0]["name"] == "Mi consulta"
    assert queries[0]["catalog"] == "DEMO_CUBE"


def test_delete_query(tmp_cache):
    qid = tmp_cache.save_query("DEMO_CUBE", "Para borrar", "SELECT {} ON COLUMNS FROM [X]")
    tmp_cache.delete_query(qid)
    queries = tmp_cache.list_queries()
    assert all(q["id"] != qid for q in queries)


def test_clear_catalog(tmp_cache):
    tmp_cache.touch_catalog("DEMO_CUBE")
    tmp_cache.save_members("DEMO_CUBE", "[D]", "[D].[H]", "L",
                           [{"caption": "X", "unique_name": "[D].[H].&[1]"}])
    tmp_cache.clear_catalog("DEMO_CUBE")
    assert tmp_cache.is_stale("DEMO_CUBE") is True
    assert tmp_cache.get_members("DEMO_CUBE", "[D]", "[D].[H]", "L") == []


def test_corrupt_db_auto_recreates(tmp_path):
    """Si la DB esta corrupta, MetadataCache la recrea automaticamente."""
    db_file = tmp_path / "corrupt.db"
    db_file.write_bytes(b"this is not a sqlite database at all")
    cache = MetadataCache(db_file)
    # Debe funcionar normalmente despues de recrear
    cache.touch_catalog("TEST")
    assert not cache.is_stale("TEST")


def test_get_catalog_meta_missing_returns_none(tmp_cache):
    assert tmp_cache.get_catalog_meta("NONEXISTENT") is None


def test_get_catalog_meta_invalid_json(tmp_cache):
    """data_json con basura no crashea."""
    tmp_cache._db.execute(
        "INSERT INTO catalog_meta(catalog, data_json, fetched_at) VALUES(?, ?, ?)",
        ("BAD", "not-json{{{", "2026-01-01T00:00:00"),
    )
    tmp_cache._db.commit()
    assert tmp_cache.get_catalog_meta("BAD") is None
