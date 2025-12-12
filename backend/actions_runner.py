#!/usr/bin/env python3
"""
Actions Runner - DGIS-specific MDX syntax
Based on validated patterns from Juan Santos blog (2022)
DGIS uses NON-STANDARD syntax: [$DIMENSION.field]="Value"
"""

import os
import sys
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment variables
ACTION = os.environ.get('ACTION', 'get_catalogs')
CATALOG = os.environ.get('CATALOG', '')
PARAMS = json.loads(os.environ.get('PARAMS', '{}'))
REQUEST_ID = os.environ.get('REQUEST_ID', 'unknown')

DGIS_SERVER = os.environ.get('DGIS_SERVER')
DGIS_USER = os.environ.get('DGIS_USER')
DGIS_PASSWORD = os.environ.get('DGIS_PASSWORD')

try:
    import adodbapi
except ImportError as e:
    logger.critical(f"Failed to import adodbapi: {e}")
    sys.exit(1)


def get_connection(catalog: str = None):
    """Create MSOLAP connection - same as Juan Santos validated pattern"""
    conn_str = (
        "Provider=MSOLAP;"
        f"Data Source={DGIS_SERVER};"
        "Persist Security Info=True;"
        f"User ID={DGIS_USER};"
        f"Password={DGIS_PASSWORD};"
    )
    if catalog:
        conn_str += f"Initial Catalog={catalog};"
    
    return adodbapi.connect(conn_str, timeout=60)


def rows_to_list(cursor, rows) -> list:
    """Convert cursor rows to list of dicts"""
    if rows is None or len(rows) == 0:
        return []
    
    cols = [c[0] for c in cursor.description] if cursor.description else []
    result = []
    for row in rows:
        result.append({cols[i]: (str(v) if v is not None else None) for i, v in enumerate(row)})
    return result


def get_catalogs() -> dict:
    """Get list of available catalogs"""
    logger.info("Fetching catalogs...")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Validated DGIS query
    cursor.execute("SELECT [catalog_name] FROM $system.DBSCHEMA_CATALOGS")
    rows = cursor.fetchall()
    catalogs = rows_to_list(cursor, rows)
    
    cursor.close()
    conn.close()
    
    result = []
    for cat in catalogs:
        name = cat.get("catalog_name", "")
        if name and not name.startswith("$"):
            result.append({"name": name, "description": "", "created": ""})
    
    return {"catalogs": result}


def discover_cube_structure(catalog: str) -> dict:
    """Discover dimensions and fields in a cube - DGIS style"""
    logger.info(f"Discovering structure for {catalog}...")
    
    conn = get_connection(catalog)
    cursor = conn.cursor()
    
    # Get cubes - main cube doesn't start with $
    cursor.execute("""
        SELECT CUBE_NAME AS cube, DIMENSION_CAPTION AS dimension
        FROM $system.MDSchema_Dimensions
    """)
    rows = cursor.fetchall()
    dimensions = rows_to_list(cursor, rows)
    
    # Find main cube (no $ prefix)
    main_cubes = [d for d in dimensions if not d.get('cube', '').startswith('$')]
    main_cube = main_cubes[0]['cube'] if main_cubes else catalog
    
    cursor.close()
    conn.close()
    
    return {
        "catalog": catalog,
        "main_cube": main_cube,
        "dimensions": [d for d in dimensions if d.get('cube') == main_cube]
    }


def get_apartados(catalog: str) -> dict:
    """Get apartados using DGIS field discovery"""
    logger.info(f"Fetching apartados from {catalog}...")
    
    # First discover structure
    structure = discover_cube_structure(catalog)
    main_cube = structure.get("main_cube", catalog)
    
    conn = get_connection(catalog)
    cursor = conn.cursor()
    
    try:
        # Try to get sample data to discover field names
        # DGIS style: SELECT field FROM [CUBE].[Measures]
        cursor.execute(f"SELECT * FROM [{main_cube}].[Measures]")
        rows = cursor.fetchmany(10)  # Just get 10 rows to discover columns
        
        if rows and cursor.description:
            cols = [c[0] for c in cursor.description]
            # Look for apartado column
            apartado_cols = [c for c in cols if 'apartado' in c.lower()]
            logger.info(f"Found columns: {cols[:5]}... (showing first 5)")
            logger.info(f"Apartado columns: {apartado_cols}")
        
        cursor.close()
        conn.close()
        
        return {
            "structure": structure,
            "columns_sample": cols[:10] if rows else [],
            "apartados": []  # Need more analysis
        }
    except Exception as e:
        cursor.close()
        conn.close()
        return {"error": str(e), "structure": structure}


def execute_mdx(catalog: str, mdx: str) -> dict:
    """Execute raw MDX query - DGIS syntax"""
    logger.info(f"Executing MDX on {catalog}...")
    logger.info(f"MDX: {mdx[:200]}...")
    
    conn = get_connection(catalog)
    cursor = conn.cursor()
    
    try:
        cursor.execute(mdx)
        rows = cursor.fetchall()
        data = rows_to_list(cursor, rows)
        
        columns = list(data[0].keys()) if data else []
        
        cursor.close()
        conn.close()
        
        return {
            "rows": data,
            "columns": [{"field": c, "headerName": c} for c in columns],
            "rowCount": len(data),
            "mdx": mdx
        }
    except Exception as e:
        cursor.close()
        conn.close()
        return {"rows": [], "columns": [], "rowCount": 0, "error": str(e), "mdx": mdx}


def build_dgis_query(catalog: str, params: dict) -> str:
    """
    Build DGIS-style MDX query
    
    DGIS Syntax: SELECT [$DIM.field] FROM [CUBE].[Measures] WHERE [$DIM.field]="Value"
    NOT SSAS: [Dimension].[Hierarchy].[Level].&[Key]
    """
    main_cube = params.get('cube', catalog)
    
    # Columns to select
    select_fields = params.get('select', ['*'])
    if select_fields == ['*']:
        select_clause = '*'
    else:
        select_clause = ', '.join(select_fields)
    
    # WHERE filters - DGIS style: [$DIM.field]="Value"
    filters = params.get('filters', [])
    where_parts = []
    for f in filters:
        dim = f.get('dimension', '')
        field = f.get('field', '')
        value = f.get('value', '')
        if dim and field and value:
            # DGIS format: [$dimension.field]="value"
            where_parts.append(f'[${dim}.{field}]="{value}"')
    
    where_clause = ' AND '.join(where_parts) if where_parts else ''
    
    mdx = f"SELECT {select_clause} FROM [{main_cube}].[Measures]"
    if where_clause:
        mdx += f" WHERE {where_clause}"
    
    return mdx


def execute_query(catalog: str, params: dict) -> dict:
    """Execute query with DGIS syntax builder"""
    
    # Check for raw MDX first
    raw_mdx = params.get('mdx')
    if raw_mdx:
        return execute_mdx(catalog, raw_mdx)
    
    # Build DGIS-style query
    mdx = build_dgis_query(catalog, params)
    return execute_mdx(catalog, mdx)


def main():
    logger.info("=== Actions Runner (DGIS Syntax) ===")
    logger.info(f"Action: {ACTION}")
    logger.info(f"Catalog: {CATALOG}")
    logger.info(f"Request ID: {REQUEST_ID}")
    
    result = {"request_id": REQUEST_ID, "action": ACTION, "status": "success"}
    
    try:
        if ACTION == 'get_catalogs':
            result["data"] = get_catalogs()
        
        elif ACTION == 'discover_structure':
            result["data"] = discover_cube_structure(CATALOG)
        
        elif ACTION == 'get_apartados':
            result["data"] = get_apartados(CATALOG)
        
        elif ACTION == 'execute_query':
            result["data"] = execute_query(CATALOG, PARAMS)
        
        elif ACTION == 'execute_mdx':
            mdx = PARAMS.get('mdx', '')
            result["data"] = execute_mdx(CATALOG, mdx)
        
        else:
            result["status"] = "error"
            result["error"] = f"Unknown action: {ACTION}"
            
    except Exception as e:
        logger.error(f"Action failed: {e}")
        result["status"] = "error"
        result["error"] = str(e)
    
    # Write result
    with open('result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Result written to result.json")
    logger.info(f"Status: {result['status']}")
    
    if result["status"] == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
