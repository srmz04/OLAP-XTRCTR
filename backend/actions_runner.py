#!/usr/bin/env python3
"""
Actions Runner - Executes OLAP queries in GitHub Actions environment
Uses same connection pattern as working DGIS_SCAN_2_stable.py
"""

import os
import sys
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment variables from GitHub Actions
ACTION = os.environ.get('ACTION', 'get_catalogs')
CATALOG = os.environ.get('CATALOG', '')
PARAMS = json.loads(os.environ.get('PARAMS', '{}'))
REQUEST_ID = os.environ.get('REQUEST_ID', 'unknown')

DGIS_SERVER = os.environ.get('DGIS_SERVER')
DGIS_USER = os.environ.get('DGIS_USER')
DGIS_PASSWORD = os.environ.get('DGIS_PASSWORD')

# Import adodbapi
try:
    import adodbapi
except ImportError as e:
    logger.critical(f"Failed to import adodbapi: {e}")
    sys.exit(1)


def get_connection(catalog: str = None):
    """Create MSOLAP connection using same pattern as working scanner"""
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
    """Get list of available catalogs using $system.DBSCHEMA_CATALOGS"""
    logger.info("Fetching catalogs from $system.DBSCHEMA_CATALOGS...")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM $system.DBSCHEMA_CATALOGS")
    rows = cursor.fetchall()
    catalogs = rows_to_list(cursor, rows)
    
    cursor.close()
    conn.close()
    
    # Transform to simpler format
    result = []
    for cat in catalogs:
        result.append({
            "name": cat.get("CATALOG_NAME", ""),
            "description": cat.get("DESCRIPTION", ""),
            "created": ""
        })
    
    return {"catalogs": result}


def get_apartados(catalog: str) -> dict:
    """Get apartados from a catalog via MDX query"""
    logger.info(f"Fetching apartados from {catalog}...")
    
    conn = get_connection(catalog)
    cursor = conn.cursor()
    
    # First try to find the Apartado dimension
    mdx = f"""
    SELECT 
        {{}} ON COLUMNS,
        [Apartado].[Apartado].MEMBERS ON ROWS
    FROM [{catalog}]
    """
    
    try:
        cursor.execute(mdx)
        rows = cursor.fetchall()
        apartados = rows_to_list(cursor, rows)
        
        result = []
        for i, apt in enumerate(apartados):
            first_col = list(apt.keys())[0] if apt else ""
            val = apt.get(first_col, "")
            if val and "All" not in str(val):
                result.append({
                    "id": str(i),
                    "name": str(val).split('.')[-1].strip('[]&'),
                    "uniqueName": str(val),
                    "hierarchy": "Apartado"
                })
        
        cursor.close()
        conn.close()
        return {"apartados": result}
    except Exception as e:
        logger.warning(f"Apartado query failed: {e}, trying measures...")
        cursor.close()
        conn.close()
        
        # Fallback: return measures as apartados
        return {"apartados": [], "error": str(e)}


def get_variables(catalog: str, apartados: list = None) -> dict:
    """Get measures from a catalog"""
    logger.info(f"Fetching variables/measures from {catalog}...")
    
    conn = get_connection(catalog)
    cursor = conn.cursor()
    
    # Query measures from system schema
    cursor.execute(f"SELECT MEASURE_NAME, MEASURE_UNIQUE_NAME, MEASURE_CAPTION FROM $system.MDSCHEMA_MEASURES WHERE CATALOG_NAME = '{catalog}'")
    rows = cursor.fetchall()
    measures = rows_to_list(cursor, rows)
    
    cursor.close()
    conn.close()
    
    result = []
    for i, m in enumerate(measures):
        result.append({
            "id": str(i),
            "name": m.get("MEASURE_NAME") or m.get("MEASURE_CAPTION", ""),
            "uniqueName": m.get("MEASURE_UNIQUE_NAME", ""),
            "apartado": "General",
            "hierarchy": "Measures"
        })
    
    return {"variables": result}


def get_dimensions(catalog: str) -> dict:
    """Get dimensions from a catalog using MDSCHEMA_DIMENSIONS"""
    logger.info(f"Fetching dimensions from {catalog}...")
    
    conn = get_connection(catalog)
    cursor = conn.cursor()
    
    cursor.execute(f"SELECT DIMENSION_NAME, DIMENSION_UNIQUE_NAME, DIMENSION_CAPTION FROM $system.MDSCHEMA_DIMENSIONS WHERE CATALOG_NAME = '{catalog}'")
    rows = cursor.fetchall()
    dims = rows_to_list(cursor, rows)
    
    cursor.close()
    conn.close()
    
    result = []
    for d in dims:
        name = d.get("DIMENSION_NAME", "")
        if name and not name.startswith('$'):
            result.append({
                "dimension": name,
                "hierarchy": name,
                "displayName": d.get("DIMENSION_CAPTION") or name,
                "levels": [{"name": "All", "depth": 0}, {"name": name, "depth": 1}]
            })
    
    return {"dimensions": result}


def get_members(catalog: str, dimension: str, hierarchy: str, level: str) -> dict:
    """Get members of a dimension hierarchy"""
    logger.info(f"Fetching members for {dimension}.{hierarchy}...")
    
    conn = get_connection(catalog)
    cursor = conn.cursor()
    
    mdx = f"""
    SELECT 
        {{}} ON COLUMNS,
        [{dimension}].[{hierarchy}].MEMBERS ON ROWS
    FROM [{catalog}]
    """
    
    try:
        cursor.execute(mdx)
        rows = cursor.fetchall()
        members_raw = rows_to_list(cursor, rows)
        
        result = []
        for m in members_raw:
            first_col = list(m.keys())[0] if m else ""
            val = m.get(first_col, "")
            if val:
                result.append({
                    "caption": str(val).split('.')[-1].strip('[]&'),
                    "uniqueName": str(val)
                })
        
        cursor.close()
        conn.close()
        return {"members": result}
    except Exception as e:
        cursor.close()
        conn.close()
        return {"members": [], "error": str(e)}


def execute_query(catalog: str, params: dict) -> dict:
    """Execute MDX query with given parameters"""
    logger.info(f"Executing query on {catalog}...")
    
    variables = params.get('variables', [])
    rows_dims = params.get('rows', [])
    filters = params.get('filters', [])
    
    # Build measures set
    if variables:
        measures = ', '.join([v.get('uniqueName', f"[Measures].[{v['name']}]") for v in variables])
    else:
        measures = '[Measures].MEMBERS'
    
    # Build rows axis
    if rows_dims:
        row_parts = []
        for r in rows_dims:
            dim = r.get('dimension', '')
            hier = r.get('hierarchy', dim)
            row_parts.append(f"[{dim}].[{hier}].MEMBERS")
        row_axis = 'NON EMPTY ' + ' * '.join(row_parts)
    else:
        row_axis = 'NON EMPTY [Apartado].[Apartado].MEMBERS'
    
    mdx = f"""
    SELECT 
        NON EMPTY {{{measures}}} ON COLUMNS,
        {row_axis} ON ROWS
    FROM [{catalog}]
    """
    
    # Add WHERE clause for filters
    if filters:
        filter_members = []
        for f in filters:
            if f.get('members'):
                filter_members.extend(f['members'])
        if filter_members:
            mdx += f" WHERE ({', '.join(filter_members)})"
    
    logger.info(f"MDX: {mdx[:200]}...")
    
    try:
        conn = get_connection(catalog)
        cursor = conn.cursor()
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
        logger.error(f"Query failed: {e}")
        return {"rows": [], "columns": [], "rowCount": 0, "error": str(e), "mdx": mdx}


def main():
    logger.info(f"=== Actions Runner ===")
    logger.info(f"Action: {ACTION}")
    logger.info(f"Catalog: {CATALOG}")
    logger.info(f"Request ID: {REQUEST_ID}")
    
    result = {"request_id": REQUEST_ID, "action": ACTION, "status": "success"}
    
    try:
        if ACTION == 'get_catalogs':
            result["data"] = get_catalogs()
        elif ACTION == 'get_apartados':
            result["data"] = get_apartados(CATALOG)
        elif ACTION == 'get_variables':
            apartados = PARAMS.get('apartados', [])
            result["data"] = get_variables(CATALOG, apartados)
        elif ACTION == 'get_dimensions':
            result["data"] = get_dimensions(CATALOG)
        elif ACTION == 'get_members':
            result["data"] = get_members(
                CATALOG,
                PARAMS.get('dimension', ''),
                PARAMS.get('hierarchy', ''),
                PARAMS.get('level', '')
            )
        elif ACTION == 'execute_query':
            result["data"] = execute_query(CATALOG, PARAMS)
        else:
            result["status"] = "error"
            result["error"] = f"Unknown action: {ACTION}"
            
    except Exception as e:
        logger.error(f"Action failed: {e}")
        result["status"] = "error"
        result["error"] = str(e)
    
    # Write result to file
    with open('result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Result written to result.json")
    logger.info(f"Status: {result['status']}")
    
    if result["status"] == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
