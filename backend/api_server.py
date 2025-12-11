"""
FastAPI Server for DGIS OLAP Query Builder
Endpoints para consumir desde React frontend
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging

from olap_service import get_service, OlapService
# Explicit import for type hinting if needed, though get_service abstraction handles it
try:
    from mock_service import SnapshotOlapService
except ImportError:
    pass

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear app FastAPI
app = FastAPI(
    title="DGIS OLAP Query Builder API",
    description="REST API para construcción dinámica de consultas MDX",
    version="1.0.0"
)

# CORS para desarrollo (permite cualquier origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local dev/network access
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== MODELOS PYDANTIC ==========

class CatalogResponse(BaseModel):
    name: str
    description: str
    created: str


class MeasureResponse(BaseModel):
    id: str
    name: str
    caption: str
    aggregator: str
    type: str = "measure"


class LevelInfo(BaseModel):
    name: str
    depth: int


class DimensionResponse(BaseModel):
    dimension: str
    hierarchy: str
    displayName: str
    levels: List[LevelInfo]
    type: str = "dimension"


class MemberResponse(BaseModel):
    caption: str
    uniqueName: str


class RowConfig(BaseModel):
    dimension: str
    hierarchy: str
    level: str
    depth: Optional[int] = None
    members: Optional[List[str]] = None


class FilterConfig(BaseModel):
    dimension: str
    hierarchy: str
    members: List[str]


class QueryRequest(BaseModel):
    catalog: str
    # Opción 1: Medidas genéricas (compatibilidad con UI antigua)
    measures: List[Dict[str, str]] = Field(default_factory=list, description="[{uniqueName: str}]")
    # Opción 2: Variables específicas de apartados (nueva UI wizard)
    variables: List[Dict[str, str]] = Field(default_factory=list, description="[{uniqueName: str, name: str}]")
    rows: List[RowConfig] = Field(default_factory=list)
    filters: List[FilterConfig] = Field(default_factory=list)


class QueryResponse(BaseModel):
    rows: List[Dict[str, Any]]
    columns: List[Dict[str, str]]
    rowCount: int


# ========== ENDPOINTS ==========

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "service": "DGIS OLAP Query Builder API",
        "version": "1.0.0"
    }


@app.get("/api/catalogs", response_model=List[CatalogResponse])
async def list_catalogs(service: OlapService = Depends(get_service)):
    """
    Lista todos los catálogos OLAP disponibles
    
    Ejemplo de respuesta:
    ```json
    [
        {
            "name": "sis2011",
            "description": "Sistema 2011",
            "created": "2011-01-01"
        }
    ]
    ```
    """
    try:
        catalogs = await service.get_catalogs()
        return catalogs
    except Exception as e:
        logger.error(f"Error obteniendo catálogos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/catalogs/{catalog_name}/measures", response_model=List[MeasureResponse])
async def get_measures(
    catalog_name: str,
    service: OlapService = Depends(get_service)
):
    """
    Obtiene todas las medidas de un catálogo
    
    Args:
        catalog_name: Nombre del catálogo (ej. "sis2011")
    
    Ejemplo de respuesta:
    ```json
    [
        {
            "id": "[Measures].[Total Registros]",
            "name": "Total Registros",
            "caption": "Total Registros",
            "aggregator": "SUM",
            "type": "measure"
        }
    ]
    ```
    """
    try:
        measures = await service.get_measures(catalog_name)
        return measures
    except Exception as e:
        logger.error(f"Error obteniendo medidas de {catalog_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/catalogs/{catalog_name}/apartados")
async def get_apartados(
    catalog_name: str,
    service: OlapService = Depends(get_service)
):
    """
    Obtiene apartados (grupos temáticos) de un catálogo
    
    Apartados son categorías de alto nivel que agrupan variables.
    Similar a DGIS_SCAN_2 "PASO 2: APARTADO"
    
    Returns:
        List[Dict]: Lista de apartados con id, name, uniqueName, hierarchy
    """
    try:
        apartados =  await service.get_apartados(catalog_name)
        return apartados
    except Exception as e:
        logger.error(f"Error obteniendo apartados de {catalog_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/catalogs/{catalog_name}/variables")
async def get_variables(
    catalog_name: str,
    apartados: str = None,
    service: OlapService = Depends(get_service)
):
    """
    Obtiene variables filtradas por apartados seleccionados
    
    Args:
        catalog_name: Nombre del catálogo
        apartados: IDs de apartados separados por comas, soporta rangos
                   Ejemplos: "1,3,5", "101-112", "1,3,5-10,15"
                   Si se omite, retorna TODAS las variables
    
    Returns:
        List[Dict]: Variables con id, name, uniqueName, apartado, hierarchy
        
    Example:
        GET /api/catalogs/SIS_2025/variables?apartados=101-112,119
    """
    try:
        variables = await service.get_variables(catalog_name, apartados)
        return variables
    except Exception as e:
        logger.error(f"Error obteniendo variables de {catalog_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/catalogs/{catalog_name}/dimensions", response_model=List[DimensionResponse])
async def get_dimensions(
    catalog_name: str,
    service: OlapService = Depends(get_service)
):
    """
    Obtiene todas las dimensiones y jerarquías de un catálogo con sus niveles
    
    Args:
        catalog_name: Nombre del catálogo
    
    Ejemplo de respuesta:
    ```json
    [
        {
            "dimension": "[D Clues]",
            "hierarchy": "[D Clues].[Unidad médica]",
            "displayName": "Unidad médica",
            "levels": [
                {"name": "Entidad", "depth": 1},
                {"name": "Nivel 2", "depth": 2}
            ],
            "type": "dimension"
        }
    ]
    ```
    """
    try:
        dimensions = await service.get_dimensions(catalog_name)
        return dimensions
    except Exception as e:
        logger.error(f"Error obteniendo dimensiones de {catalog_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/catalogs/{catalog_name}/members")
async def get_members(
    catalog_name: str,
    dimension: str,
    hierarchy: str,
    level: str,
    service: OlapService = Depends(get_service)
):
    """
    Obtiene miembros de un nivel específico
    
    Args:
        catalog_name: Nombre del catálogo
        dimension: Unique name de la dimensión (ej. "[D Clues]")
        hierarchy: Unique name de la jerarquía (ej. "[D Clues].[Unidad médica]")
        level: Nombre del nivel (ej. "Entidad")
    
    Query params ejemplo:
    ```
    /api/catalogs/sis2011/members?dimension=[D Clues]&hierarchy=[D Clues].[Unidad médica]&level=Entidad
    ```
    
    Ejemplo de respuesta:
    ```json
    [
        {
            "caption": "Aguascalientes",
            "uniqueName": "[D Clues].[Unidad médica].[Entidad].&[1]"
        }
    ]
    ```
    """
    try:
        members = await service.get_members(catalog_name, dimension, hierarchy, level)
        return members
    except Exception as e:
        logger.error(f"Error obteniendo miembros: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query/execute", response_model=QueryResponse)
async def execute_query(
    request: QueryRequest,
    service: OlapService = Depends(get_service)
):
    """
    Construye y ejecuta una consulta MDX basada en la configuración del drag & drop
    
    Request body ejemplo:
    ```json
    {
        "catalog": "sis2011",
        "measures": [
            {"uniqueName": "[Measures].[Total Registros]"}
        ],
        "rows": [
            {
                "dimension": "[D Clues]",
                "hierarchy": "[D Clues].[Unidad médica]",
                "level": "Entidad",
                "depth": 1
            }
        ],
        "filters": [
            {
                "dimension": "[D Clues]",
                "hierarchy": "[D Clues].[Unidad médica]",
                "members": [
                    "[D Clues].[Unidad médica].[Entidad].&[1]"
                ]
            }
        ]
    }
    ```
    
    Respuesta:
    ```json
    {
        "rows": [
            {"Entidad": "Aguascalientes", "Total Registros": 12345}
        ],
        "columns": [
            {"field": "Entidad", "headerName": "Entidad", "sortable": true},
            {"field": "Total Registros", "headerName": "Total Registros", "sortable": true}
        ],
        "rowCount": 1
    }
    ```
    """
    try:
        result = await service.execute_query(request.dict())
        return result
    except Exception as e:
        logger.error(f"Error ejecutando query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== EJECUTAR SERVIDOR ==========

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Iniciando DGIS OLAP API Server...")
    print("📍 Documentación interactiva: http://localhost:8000/docs")
    print("📍 Frontend esperado: http://localhost:5173")
    
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Hot reload en desarrollo
        log_level="info"
    )
