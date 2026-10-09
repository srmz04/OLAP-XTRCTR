"""
OlapProvider: contrato que deben cumplir todos los providers (real y mock).
No importa nada de COM ni de PySide6 -- es puro Python stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class ConnectionStatus:
    connected: bool
    server: str
    catalog: str = ""
    error: str = ""
    msolap_version: str = ""


@dataclass
class CatalogInfo:
    name: str
    description: str = ""
    created: str = ""


@dataclass
class MeasureInfo:
    id: str          # MEASURE_UNIQUE_NAME
    name: str
    caption: str
    aggregator: str = ""


@dataclass
class LevelInfo:
    name: str
    depth: int


@dataclass
class DimensionInfo:
    dimension: str
    hierarchy: str
    display_name: str
    levels: List[LevelInfo] = field(default_factory=list)


@dataclass
class MemberInfo:
    caption: str
    unique_name: str


@dataclass
class ApartadoInfo:
    id: str
    name: str
    unique_name: str
    hierarchy: str


@dataclass
class QueryResult:
    rows: List[Dict[str, Any]]
    columns: List[Dict[str, str]]
    row_count: int
    truncated: bool = False


@runtime_checkable
class OlapProvider(Protocol):
    def test_connection(self, server: str, user: str, password: str) -> ConnectionStatus: ...
    def list_catalogs(self) -> List[CatalogInfo]: ...
    def resolve_cube(self, catalog: str) -> Optional[str]: ...
    def list_measures(self, catalog: str) -> List[MeasureInfo]: ...
    def list_hierarchies(self, catalog: str) -> List[DimensionInfo]: ...
    def list_members(self, catalog: str, dimension: str,
                     hierarchy: str, level: str) -> List[MemberInfo]: ...
    def list_apartados(self, catalog: str) -> List[ApartadoInfo]: ...
    def list_variables(self, catalog: str, apartado_ids: str) -> List[Dict[str, Any]]: ...
    def execute_mdx(self, catalog: str, mdx: str) -> QueryResult: ...
    def estimate_cardinality(self, catalog: str, dimensions: List[Dict]) -> int: ...
