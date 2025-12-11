"""
Mock data para testing cuando el servidor OLAP no está disponible
"""

MOCK_CATALOGS = [
    {
        "name": "sis2011",
        "description": "Sistema de Información en Salud 2011",
        "created": "2011-01-01"
    },
    {
        "name": "SIS_2023",
        "description": "Sistema de Información en Salud 2023",
        "created": "2023-01-01"
    }
]

MOCK_MEASURES = [
    {
        "id": "[Measures].[Total Registros]",
        "name": "Total Registros",
        "caption": "Total Registros",
        "aggregator": "SUM",
        "type": "measure"
    },
    {
        "id": "[Measures].[Suma Atenciones]",
        "name": "Suma Atenciones",
        "caption": "Suma de Atenciones",
        "aggregator": "SUM",
        "type": "measure"
    }
]

MOCK_DIMENSIONS = [
    {
        "dimension": "[D Clues]",
        "hierarchy": "[D Clues].[Unidad médica]",
        "displayName": "Unidad médica",
        "levels": [
            {"name": "Entidad", "depth": 1},
            {"name": "Nivel 2", "depth": 2}
        ],
        "type": "dimension"
    },
    {
        "dimension": "[D Tiempo]",
        "hierarchy": "[D Tiempo].[Año]",
        "displayName": "Año",
        "levels": [
            {"name": "Año", "depth": 1}
        ],
        "type": "dimension"
    }
]

MOCK_MEMBERS = [
    {
        "caption": "Aguascalientes",
        "uniqueName": "[D Clues].[Unidad médica].[Entidad].&[1]"
    },
    {
        "caption": "Baja California",
        "uniqueName": "[D Clues].[Unidad médica].[Entidad].&[2]"
    }
]

MOCK_QUERY_RESULTS = {
    "rows": [
        {"Entidad": "Aguascalientes", "Total Registros": 12345},
        {"Entidad": "Baja California", "Total Registros": 23456}
    ],
    "columns": [
        {"field": "Entidad", "headerName": "Entidad", "sortable": True, "filter": True},
        {"field": "Total Registros", "headerName": "Total Registros", "sortable": True, "filter": True}
    ],
    "rowCount": 2
}
