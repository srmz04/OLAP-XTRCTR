"""
MockProvider: adapta backend/mock_service.MockOlapService para uso en GUI.
Permite desarrollar y testear toda la UI en Ubuntu sin COM ni adodbapi.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

# Apuntar al backend real del monorepo
_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
sys.path.insert(0, _BACKEND)

from .provider import (
    ApartadoInfo,
    CatalogInfo,
    ConnectionStatus,
    DimensionInfo,
    LevelInfo,
    MeasureInfo,
    MemberInfo,
    OlapProvider,
    QueryResult,
)


class MockProvider:
    """
    Wrapper sincronico sobre MockOlapService.
    Cumple el protocolo OlapProvider sin necesitar COM.
    """

    def __init__(self, csv_path: Optional[str] = None):
        self._loop = asyncio.new_event_loop()
        try:
            from mock_service import MockOlapService
            self._mock = MockOlapService(csv_path or "mock_data.csv")
        except ImportError as e:
            raise RuntimeError(
                f"No se pudo importar mock_service desde {_BACKEND}: {e}"
            )

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def test_connection(self, server: str, user: str, password: str) -> ConnectionStatus:
        return ConnectionStatus(
            connected=True,
            server=server,
            catalog="MOCK_CATALOG",
            msolap_version="MOCK",
        )

    def list_catalogs(self) -> List[CatalogInfo]:
        raw = self._run(self._mock.get_catalogs())
        return [CatalogInfo(name=c["name"], description=c.get("description", ""),
                            created=c.get("created", "")) for c in raw]

    def resolve_cube(self, catalog: str) -> Optional[str]:
        return catalog  # mock: el cubo tiene el mismo nombre

    def list_measures(self, catalog: str) -> List[MeasureInfo]:
        raw = self._run(self._mock.get_measures(catalog))
        return [MeasureInfo(id=m["id"], name=m["name"],
                            caption=m.get("caption", m["name"]),
                            aggregator=m.get("aggregator", "")) for m in raw]

    def list_hierarchies(self, catalog: str) -> List[DimensionInfo]:
        raw = self._run(self._mock.get_dimensions(catalog))
        result = []
        for d in raw:
            levels = [LevelInfo(name=lv["name"], depth=lv.get("depth", 0))
                      for lv in d.get("levels", [])]
            result.append(DimensionInfo(
                dimension=d["dimension"],
                hierarchy=d.get("hierarchy", d["dimension"]),
                display_name=d.get("displayName", d["dimension"]),
                levels=levels,
            ))
        return result

    def list_members(self, catalog: str, dimension: str,
                     hierarchy: str, level: str) -> List[MemberInfo]:
        raw = self._run(self._mock.get_members(catalog, dimension, hierarchy, level))
        return [MemberInfo(caption=m["caption"], unique_name=m["uniqueName"]) for m in raw]

    def list_apartados(self, catalog: str) -> List[ApartadoInfo]:
        return []  # mock minimo -- se expande en S4

    def list_variables(self, catalog: str, apartado_ids: str) -> List[Dict[str, Any]]:
        return []

    def execute_mdx(self, catalog: str, mdx: str) -> QueryResult:
        raw = self._run(self._mock.execute_query({"catalog": catalog, "mdx": mdx}))
        return QueryResult(
            rows=raw.get("rows", []),
            columns=raw.get("columns", []),
            row_count=raw.get("rowCount", 0),
        )

    def estimate_cardinality(self, catalog: str, dimensions: List[Dict]) -> int:
        return 0  # mock no estima
