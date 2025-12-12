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
        SELECT CUBE_NAME AS [cube_name], DIMENSION_CAPTION AS [dimension]
        FROM $system.MDSchema_Dimensions
    """)
    rows = cursor.fetchall()
    dimensions = rows_to_list(cursor, rows)
    
    # Find main cube (no $ prefix)
    main_cubes = [d for d in dimensions if not d.get('cube_name', '').startswith('$')]
    main_cube = main_cubes[0]['cube_name'] if main_cubes else catalog
    
    cursor.close()
    conn.close()
    
    return {
        "catalog": catalog,
        "main_cube": main_cube,
        "dimensions": [d for d in dimensions if d.get('cube_name') == main_cube]
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
    conn = get_connection(catalog)
    cursor = conn.cursor()
    main_cube = PARAMS.get('cube', catalog)
    
    try:
        # Find the Variables dimension (it might have 2025 suffix)
        cursor.execute("SELECT [DIMENSION_UNIQUE_NAME] FROM $system.MDSchema_Dimensions WHERE [DIMENSION_TYPE]=3") # 3 = Regular/Unknown? Just try name match
        # Actually safer to look for name match in Python
        cursor.execute(f"SELECT [DIMENSION_UNIQUE_NAME] FROM $system.MDSchema_Dimensions WHERE [CUBE_NAME]='{main_cube}'")
        rows = cursor.fetchall()
        dims = [r[0] for r in rows]
        
        # Look for "VARIABLES"
        var_dim = next((d for d in dims if "VARIABLES" in d.upper()), None)
        if not var_dim:
             # Fallback: take user param or default
             var_dim = PARAMS.get("dimension", "[DIM VARIABLES]")
        
        logger.info(f"Using dimension for Apartados: {var_dim}")
        
        # Get Members directly from schema - SAFER/FASTER than MDX on large cubes
        # Filter where LEVEL_NUMBER > 0 to skip (All)
        cursor.execute(f"SELECT [MEMBER_UNIQUE_NAME], [MEMBER_CAPTION] FROM $system.MDSchema_Members WHERE [CUBE_NAME]='{main_cube}' AND [DIMENSION_UNIQUE_NAME]='{var_dim}' AND [LEVEL_NUMBER]=1")
        rows = cursor.fetchall()
        
        members = rows_to_list(cursor, rows)
        
        return {
            "dimension": var_dim,
            "apartados": members
        }
    except Exception as e:
        logger.error(f"Get apartados failed: {e}")
        return {"error": str(e)}
    finally:
        cursor.close()
        conn.close()


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


def build_mdx_query(catalog: str, params: dict) -> str:
    """
    Build Standard SSAS MDX Query
    Reverting DGIS syntax since diagnostic confirmed standard syntax support.
    Expected: SELECT ... FROM [CUBE] WHERE [Dim].[Hier].&[Key]
    """
    main_cube = params.get('cube', catalog)
    
    # Columns to select
    select_fields = params.get('select', ['[Measures].AllMembers']) # Default to something valid
    if select_fields == ['*']:
        select_clause = '*' # Should avoid this on large cubes, but user might ask
    else:
        select_clause = ', '.join(select_fields)
    
    # WHERE filters - Standard SSAS: [Dim].[Hier].&[Key]
    filters = params.get('filters', [])
    where_parts = []
    for f in filters:
        member_unique_name = f.get('member_unique_name')
        if member_unique_name:
            where_parts.append(member_unique_name)
    
    where_clause = ' AND '.join(where_parts) if where_parts else ''
    
    mdx = f"SELECT {{{select_clause}}} ON COLUMNS FROM [{main_cube}]"
    if where_clause:
        mdx += f" WHERE ({where_clause})"
    
    return mdx


def diagnose_schema(catalog: str) -> dict:
    """
    Comprehensive diagnostic to discover available schema columns.
    Executes SELECT * TOP 1 on key schema rowsets to map the server capabilities.
    """
    logger.info("Starting schema diagnostic...")
    conn = get_connection(catalog)
    cursor = conn.cursor()
    
    schemas_to_probe = [
        "$system.DBSCHEMA_CATALOGS",
        "$system.MDSchema_Cubes",
        "$system.MDSchema_Dimensions",
        "$system.MDSchema_Hierarchies",
        "$system.MDSchema_Levels",
        "$system.MDSchema_Measures",
        "$system.MDSchema_Properties",
        "$system.MDSchema_Members"
    ]
    
    # Try to find main cube for context
    main_cube = "SIS_2025" 
    try:
        main_cube = PARAMS.get('cube', catalog)
    except:
        pass

    results = {}
    
    for schema in schemas_to_probe:
        try:
            # Try to select just 1 row to get column definition
            # We use a broad WHERE clause if possible to avoid empty sets, but simple enough to pass parser
            query = f"SELECT * FROM {schema}"
            
            # For some schemas, adding a restriction makes it faster or is required
            if schema == "$system.MDSchema_Levels" or schema == "$system.MDSchema_Dimensions":
                query += f" WHERE [CUBE_NAME] = '{main_cube}'"
            
            logger.info(f"Probing {schema}...")
            cursor.execute(query)
            
            # Just fetch description to get columns
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                results[schema] = {"status": "success", "columns": columns}
            else:
                results[schema] = {"status": "empty_or_unknown"}
                
        except Exception as e:
            results[schema] = {"status": "error", "error": str(e)}
            
    cursor.close()
    conn.close()
    return results


def discover_metadata(catalog: str) -> dict:
    """Discover levels and properties using schema rowsets - Standard SSAS"""
    logger.info(f"Discovering metadata for {catalog}...")
    
    conn = get_connection(catalog)
    cursor = conn.cursor()
    
    # Get main cube name
    main_cube = PARAMS.get('cube', catalog)
    
    try:
        # Optimization: Try to find the first cube that looks like a main cube
        cursor.execute("SELECT [CUBE_NAME] FROM $system.MDSchema_Cubes")
        rows = cursor.fetchall()
        if rows:
            candidates = [r[0] for r in rows if not str(r[0]).startswith('$')]
            if catalog in candidates:
                main_cube = catalog
            elif candidates:
                main_cube = candidates[0]
            logger.info(f"Identified main cube: {main_cube}")
    except Exception as e:
        logger.warning(f"Failed to auto-discover main cube: {e}")

    result = {"levels": [], "properties": []}
    
    try:
        # Get Levels - Checked against schema_diag_01 result
        cursor.execute(f"SELECT [DIMENSION_UNIQUE_NAME], [HIERARCHY_UNIQUE_NAME], [LEVEL_UNIQUE_NAME], [LEVEL_CAPTION] FROM $system.MDSchema_Levels WHERE [CUBE_NAME]='{main_cube}'")
        rows = cursor.fetchall()
        result["levels"] = rows_to_list(cursor, rows)
        
        # Get Properties (Member Properties)
        cursor.execute(f"SELECT [DIMENSION_UNIQUE_NAME], [LEVEL_UNIQUE_NAME], [PROPERTY_NAME], [PROPERTY_CAPTION] FROM $system.MDSchema_Properties WHERE [CUBE_NAME]='{main_cube}'")
        rows = cursor.fetchall()
        result["properties"] = rows_to_list(cursor, rows)
        
    except Exception as e:
        logger.error(f"Metadata discovery failed: {e}")
        result["error"] = str(e)
    
    cursor.close()
    conn.close()
    return result


def execute_query(catalog: str, params: dict) -> dict:
    """Execute query with Standard syntax builder"""
    
    # Check for raw MDX first
    raw_mdx = params.get('mdx')
    if raw_mdx:
        return execute_mdx(catalog, raw_mdx)
    
    # Build query
    mdx = build_mdx_query(catalog, params)
    return execute_mdx(catalog, mdx)


def main():
    logger.info("=== Actions Runner (DGIS Diagnostic Mode) ===")
    logger.info(f"Action: {ACTION}")
    logger.info(f"Catalog: {CATALOG}")
    logger.info(f"Request ID: {REQUEST_ID}")
    
    result = {"request_id": REQUEST_ID, "action": ACTION, "status": "success"}
    
    try:
        if ACTION == 'get_catalogs':
            result["data"] = get_catalogs()
        
        elif ACTION == 'discover_structure':
            result["data"] = discover_cube_structure(CATALOG)
            
        elif ACTION == 'discover_metadata':
            result["data"] = discover_metadata(CATALOG)
            
        elif ACTION == 'diagnose_schema':
            result["data"] = diagnose_schema(CATALOG)
        
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
