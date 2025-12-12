#!/usr/bin/env python3
"""
Actions Runner - Executes OLAP queries in GitHub Actions environment
Outputs result to result.json for Gist upload
"""

import os
import sys
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get environment variables
ACTION = os.environ.get('ACTION', 'get_catalogs')
CATALOG = os.environ.get('CATALOG', '')
PARAMS = json.loads(os.environ.get('PARAMS', '{}'))
REQUEST_ID = os.environ.get('REQUEST_ID', 'unknown')

DGIS_SERVER = os.environ.get('DGIS_SERVER')
DGIS_USER = os.environ.get('DGIS_USER')
DGIS_PASSWORD = os.environ.get('DGIS_PASSWORD')

def get_connection_string(catalog: str = None) -> str:
    """Build OLEDB connection string for SSAS"""
    conn_str = (
        f"Provider=MSOLAP;"
        f"Data Source={DGIS_SERVER};"
        f"User ID={DGIS_USER};"
        f"Password={DGIS_PASSWORD};"
    )
    if catalog:
        conn_str += f"Initial Catalog={catalog};"
    return conn_str

def execute_mdx(catalog: str, mdx: str) -> list:
    """Execute MDX query and return results as list of dicts"""
    import adodbapi
    
    conn_str = get_connection_string(catalog)
    logger.info(f"Connecting to SSAS...")
    
    conn = adodbapi.connect(conn_str)
    cursor = conn.cursor()
    
    logger.info(f"Executing MDX: {mdx[:100]}...")
    cursor.execute(mdx)
    
    columns = [desc[0] for desc in cursor.description]
    rows = []
    for row in cursor.fetchall():
        rows.append(dict(zip(columns, [str(v) if v is not None else None for v in row])))
    
    cursor.close()
    conn.close()
    
    return rows

def get_catalogs() -> dict:
    """Get list of available catalogs"""
    import adodbapi
    
    conn_str = get_connection_string()
    conn = adodbapi.connect(conn_str)
    
    # Use DISCOVER_CATALOGS schema rowset
    schema = conn.GetSchemaRowset("{C8B52211-5CF3-11CE-ADE5-00AA0044773D}")
    
    catalogs = []
    for row in schema:
        catalogs.append({
            "name": row.CATALOG_NAME,
            "description": getattr(row, 'DESCRIPTION', ''),
            "created": str(getattr(row, 'DATE_MODIFIED', ''))
        })
    
    conn.close()
    return {"catalogs": catalogs}

def get_apartados(catalog: str) -> dict:
    """Get apartados (data categories) from catalog"""
    # Query the Apartado dimension
    mdx = f"""
    SELECT 
        {{}} ON COLUMNS,
        [Apartado].[Apartado].MEMBERS ON ROWS
    FROM [{catalog}]
    """
    
    try:
        rows = execute_mdx(catalog, mdx)
        apartados = []
        for row in rows:
            member_key = list(row.keys())[0]
            member_val = row[member_key]
            if member_val and 'All' not in member_val:
                # Extract ID from member name (e.g., "[Apartado].[Apartado].&[119]" -> "119")
                import re
                match = re.search(r'\[(\d+)\]$', member_val)
                if match:
                    apartados.append({
                        "id": match.group(1),
                        "name": member_val.split('.')[-1].strip('[]&'),
                        "uniqueName": member_val,
                        "hierarchy": "Apartado"
                    })
        return {"apartados": apartados}
    except Exception as e:
        logger.error(f"Error getting apartados: {e}")
        return {"apartados": [], "error": str(e)}

def get_variables(catalog: str, apartados: list = None) -> dict:
    """Get variables/measures from catalog"""
    mdx = f"""
    SELECT 
        {{}} ON COLUMNS,
        [Variable].[Variable].MEMBERS ON ROWS
    FROM [{catalog}]
    """
    
    try:
        rows = execute_mdx(catalog, mdx)
        variables = []
        for i, row in enumerate(rows):
            member_key = list(row.keys())[0]
            member_val = row[member_key]
            if member_val and 'All' not in member_val:
                variables.append({
                    "id": str(i),
                    "name": member_val.split('.')[-1].strip('[]&'),
                    "uniqueName": member_val,
                    "apartado": "General",
                    "hierarchy": "Variable"
                })
        return {"variables": variables}
    except Exception as e:
        logger.error(f"Error getting variables: {e}")
        return {"variables": [], "error": str(e)}

def get_dimensions(catalog: str) -> dict:
    """Get dimensions from catalog"""
    import adodbapi
    
    conn_str = get_connection_string(catalog)
    conn = adodbapi.connect(conn_str)
    
    # Query MDSCHEMA_DIMENSIONS
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM $system.MDSCHEMA_DIMENSIONS WHERE CATALOG_NAME = '{catalog}'")
    
    dimensions = []
    for row in cursor.fetchall():
        dim_name = row[2]  # DIMENSION_NAME
        if dim_name and not dim_name.startswith('$'):
            dimensions.append({
                "dimension": dim_name,
                "hierarchy": dim_name,
                "displayName": dim_name,
                "levels": [{"name": "All", "depth": 0}, {"name": dim_name, "depth": 1}]
            })
    
    cursor.close()
    conn.close()
    return {"dimensions": dimensions}

def get_members(catalog: str, dimension: str, hierarchy: str, level: str) -> dict:
    """Get members of a dimension level"""
    mdx = f"""
    SELECT 
        {{}} ON COLUMNS,
        [{dimension}].[{hierarchy}].MEMBERS ON ROWS
    FROM [{catalog}]
    """
    
    try:
        rows = execute_mdx(catalog, mdx)
        members = []
        for row in rows:
            member_key = list(row.keys())[0]
            member_val = row[member_key]
            if member_val:
                members.append({
                    "caption": member_val.split('.')[-1].strip('[]&'),
                    "uniqueName": member_val
                })
        return {"members": members}
    except Exception as e:
        logger.error(f"Error getting members: {e}")
        return {"members": [], "error": str(e)}

def execute_query(catalog: str, params: dict) -> dict:
    """Execute a full query based on wizard parameters"""
    # Build MDX from params
    variables = params.get('variables', [])
    rows_dims = params.get('rows', [])
    filters = params.get('filters', [])
    
    # Simple MDX construction
    measures = ', '.join([f"[Measures].[{v['name']}]" for v in variables]) if variables else '[Measures].MEMBERS'
    
    row_axis = 'NON EMPTY '
    if rows_dims:
        row_sets = [f"[{r['dimension']}].[{r['hierarchy']}].MEMBERS" for r in rows_dims]
        row_axis += ' * '.join(row_sets)
    else:
        row_axis += '[Apartado].[Apartado].MEMBERS'
    
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
    
    try:
        rows = execute_mdx(catalog, mdx)
        columns = list(rows[0].keys()) if rows else []
        return {
            "rows": rows,
            "columns": [{"field": c, "headerName": c} for c in columns],
            "rowCount": len(rows),
            "mdx": mdx
        }
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return {"rows": [], "columns": [], "rowCount": 0, "error": str(e), "mdx": mdx}

def main():
    logger.info(f"Starting action: {ACTION} for catalog: {CATALOG}")
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
    
    if result["status"] == "error":
        sys.exit(1)

if __name__ == "__main__":
    main()
