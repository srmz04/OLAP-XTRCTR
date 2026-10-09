"""
MsOlapProvider: adapta OlapService del backend real (Windows/COM).
No reescribe logica OLAP; solo adapta la interfaz al protocolo OlapProvider.
En Linux/no-COM este modulo se importara pero no se instanciara.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

# Apuntar al backend del monorepo (o al folder desempaquetado en MEIPASS)
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Ejecutando como binario PyInstaller
    _BACKEND = os.path.join(sys._MEIPASS, "backend") # type: ignore
else:
    # Ejecutando desde codigo fuente
    _BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "backend")

if _BACKEND not in sys.path:
    # Usar .insert(0, ...) en lugar de append para que estos modulos dominen
    sys.path.insert(0, os.path.abspath(_BACKEND))

from .provider import (
    ApartadoInfo,
    CatalogInfo,
    ConnectionStatus,
    DimensionInfo,
    LevelInfo,
    MeasureInfo,
    MemberInfo,
    QueryResult,
)


def _import_backend():
    """Importa modulos COM/Windows; lanza ImportError en Linux."""
    from olap_service import OlapService  # type: ignore  # noqa: F401
    from olap_scanner import Config, ConnectionManager  # type: ignore  # noqa: F401
    return OlapService, Config, ConnectionManager


class MsOlapProvider:
    """
    Provider real para Windows con MSOLAP/ADODBAPI instalado.
    Requiere: adodbapi, pywin32, msolap driver.
    """

    def __init__(self, server: str, user: str, password: str, catalog: str = ""):
        OlapService, Config, _ConnectionManager = _import_backend()
        self._Config = Config
        self._ConnectionManager = _ConnectionManager
        config = Config(server=server, user=user, password=password,
                        default_catalog=catalog)
        self._svc = OlapService(config)
        self._config = config

    def test_connection(self, server: str, user: str, password: str) -> ConnectionStatus:
        try:
            _OlapService, Config, ConnectionManager = _import_backend()
            config = Config(server=server, user=user, password=password)
            with ConnectionManager(config) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM $system.DBSCHEMA_CATALOGS WHERE 1=0")
            return ConnectionStatus(connected=True, server=server)
        except Exception as exc:
            err = str(exc)
            if "Dispatch" in err or "ADODB" in err:
                msg = "Driver ADODB/COM no disponible"
            elif "Provider" in err and "found" in err.lower():
                msg = "MSOLAP provider no registrado"
            elif "password" in err.lower() or "credentials" in err.lower():
                msg = "Credenciales invalidas"
            else:
                msg = err[:120]
            return ConnectionStatus(connected=False, server=server, error=msg)

    def list_catalogs(self) -> List[CatalogInfo]:
        raw = self._svc._get_catalogs_sync()
        return [
            CatalogInfo(
                name=c["name"],
                description=c.get("description", ""),
                created=c.get("created", ""),
            )
            for c in raw
        ]

    def resolve_cube(self, catalog: str) -> Optional[str]:
        return self._svc._tool._resolve_cube_name(catalog)

    def list_measures(self, catalog: str) -> List[MeasureInfo]:
        raw = self._svc._get_measures_sync(catalog)
        return [
            MeasureInfo(
                id=m["id"],
                name=m["name"],
                caption=m.get("caption", m["name"]),
                aggregator=m.get("aggregator", ""),
            )
            for m in raw
        ]

    def list_hierarchies(self, catalog: str) -> List[DimensionInfo]:
        raw = self._svc._get_dimensions_sync(catalog)
        result = []
        for d in raw:
            levels = [
                LevelInfo(name=lv["name"], depth=lv.get("depth", 0))
                for lv in d.get("levels", [])
            ]
            result.append(
                DimensionInfo(
                    dimension=d["dimension"],
                    hierarchy=d["hierarchy"],
                    display_name=d.get("displayName", d["dimension"]),
                    levels=levels,
                )
            )
        return result

    def list_members(self, catalog: str, dimension: str,
                     hierarchy: str, level: str) -> List[MemberInfo]:
        raw = self._svc._get_members_sync(catalog, dimension, hierarchy, level)
        return [
            MemberInfo(caption=m["caption"], unique_name=m["uniqueName"])
            for m in raw
        ]

    def list_apartados(self, catalog: str) -> List[ApartadoInfo]:
        raw = self._svc._get_apartados_sync(catalog)
        return [
            ApartadoInfo(
                id=a["id"],
                name=a["name"],
                unique_name=a["uniqueName"],
                hierarchy=a["hierarchy"],
            )
            for a in raw
        ]

    def list_variables(self, catalog: str, apartado_ids: str) -> List[Dict[str, Any]]:
        return self._svc._get_variables_sync(catalog, apartado_ids)

    def execute_mdx(self, catalog: str, mdx: str) -> QueryResult:
        raw = self._svc._execute_mdx_sync(catalog, mdx)
        if hasattr(raw, "to_dict"):
            rows = raw.to_dict("records")
            cols = [{"field": c, "headerName": c} for c in raw.columns]
            return QueryResult(rows=rows, columns=cols, row_count=len(rows))
        return QueryResult(rows=[], columns=[], row_count=0)

    def estimate_cardinality(self, catalog: str, dimensions: List[Dict]) -> int:
        tool = getattr(self._svc, "_tool", None)
        if tool and hasattr(tool, "_estimate_and_warn_cardinality"):
            return tool._estimate_and_warn_cardinality(dimensions, catalog)
        return 0
