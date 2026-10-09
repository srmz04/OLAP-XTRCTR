"""Tests basicos del MockProvider -- corren en Ubuntu sin COM."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.provider_mock import MockProvider
from core.provider import OlapProvider


def test_mock_provider_implements_protocol():
    p = MockProvider()
    assert isinstance(p, OlapProvider)


def test_test_connection_always_ok():
    p = MockProvider()
    status = p.test_connection("any-server", "user", "pass")
    assert status.connected is True


def test_list_catalogs_returns_list():
    p = MockProvider()
    cats = p.list_catalogs()
    assert isinstance(cats, list)
    assert len(cats) >= 1


def test_list_measures_returns_list():
    p = MockProvider()
    cats = p.list_catalogs()
    measures = p.list_measures(cats[0].name)
    assert isinstance(measures, list)


def test_execute_mdx_returns_query_result():
    p = MockProvider()
    cats = p.list_catalogs()
    result = p.execute_mdx(cats[0].name, "SELECT {} ON COLUMNS FROM [MOCK]")
    assert hasattr(result, "rows")
    assert hasattr(result, "columns")
    assert hasattr(result, "row_count")


def test_list_measures_nonexistent_catalog():
    """Catalogo inexistente no crashea, retorna lista."""
    p = MockProvider()
    measures = p.list_measures("CATALOG_QUE_NO_EXISTE")
    assert isinstance(measures, list)


def test_list_hierarchies_nonexistent_catalog():
    p = MockProvider()
    hiers = p.list_hierarchies("CATALOG_QUE_NO_EXISTE")
    assert isinstance(hiers, list)
