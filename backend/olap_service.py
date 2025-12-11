"""
DGIS OLAP Service - Thread-Safe Wrapper
Encapsula DGIS_SCAN_2.py para uso en entornos asyncio (FastAPI/NiceGUI)
"""

import sys
import os
import asyncio
import threading
from typing import List, Dict, Optional
from functools import wraps
import pandas as pd
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env
load_dotenv()

# Importar COM solo si estamos en Windows o con adodbapi disponible
try:
    import pythoncom
    COM_AVAILABLE = True
except ImportError:
    COM_AVAILABLE = False

# Importar el módulo original
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from DGIS_SCAN_2 import (
    Config,
    MDXQueryTool,
    ServerDiscovery,
    CatalogExplorer,
    ConnectionManager
)


def com_thread_safe(func):
    """
    Decorator que garantiza que funciones ADODBAPI se ejecuten 
    en threads con COM inicializado
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        def _sync_runner():
            if COM_AVAILABLE:
                pythoncom.CoInitialize()
            try:
                return func(*args, **kwargs)
            finally:
                if COM_AVAILABLE:
                    pythoncom.CoUninitialize()
        
        return await asyncio.to_thread(_sync_runner)
    
    return wrapper


class OlapService:
    """
    Servicio principal para interactuar con cubos OLAP
    Thread-safe y compatible con asyncio
    """
    
    def __init__(self, config: Optional[Config] = None):
        if config is None:
            # Crear Config con variables de entorno
            config = Config(
                server=os.getenv('OLAP_SERVER', 'reportesdgis.salud.gob.mx'),
                user=os.getenv('OLAP_USER', 'PWIDGISREPORTES\\DGIS15'),
                password=os.getenv('OLAP_PASSWORD', 'Temp123!'),
                connection_timeout=int(os.getenv('OLAP_TIMEOUT', '30')),
            )
        
        self.config = config
        self._tool = MDXQueryTool(self.config)
        self._discovery = ServerDiscovery(self.config)
        self._explorer = CatalogExplorer(self.config)
        self._lock = threading.Lock()
    
    # ========== MÉTODOS SÍNCRONOS (para uso en threads) ==========
    
    def _get_catalogs_sync(self) -> List[Dict]:
        """Obtiene lista de catálogos del servidor"""
        self._discovery.discover_generic(
            'Catalogos',
            "SELECT * FROM $system.DBSCHEMA_CATALOGS",
            'catalogs'
        )
        catalogs = self._discovery.discovery_results.get('catalogs', [])
        
        # Transformar a formato ligero
        return [
            {
                'name': c.get('CATALOG_NAME', 'Unknown'),
                'description': c.get('DESCRIPTION', ''),
                'created': str(c.get('DATE_CREATED', ''))
            }
            for c in catalogs
        ]
    
    def _get_measures_sync(self, catalog: str) -> List[Dict]:
        """Obtiene medidas de un catálogo"""
        measures = self._tool.get_measures(catalog)
        
        # Formato para frontend
        return [
            {
                'id': m.get('MEASURE_UNIQUE_NAME', ''),
                'name': m.get('MEASURE_NAME', ''),
                'caption': m.get('MEASURE_CAPTION', m.get('MEASURE_NAME', '')),
                'aggregator': m.get('MEASURE_AGGREGATOR', 'UNKNOWN'),
                'type': 'measure'
            }
            for m in measures
        ]
    
    def _get_dimensions_sync(self, catalog: str) -> List[Dict]:
        """Obtiene dimensiones y jerarquías con sus niveles"""
        # Cargar metadata del catálogo
        df_members = self._tool.load_catalog_members_csv(catalog)
        if df_members is None:
            return []
        
        hierarchies = self._tool.get_hierarchies(catalog)
        result = []
        
        for hier in hierarchies:
            dimension = hier.get('DIMENSION_UNIQUE_NAME', '')
            hierarchy = hier.get('HIERARCHY_UNIQUE_NAME', '')
            
            # Extraer niveles
            levels = self._tool.extract_levels_from_unique_names(
                df_members, dimension, hierarchy
            )
            
            result.append({
                'dimension': dimension,
                'hierarchy': hierarchy,
                'displayName': hier.get('HIERARCHY_CAPTION', hierarchy),
                'levels': [
                    {
                        'name': lv['level_name'],
                        'depth': lv['level_depth'],
                        'uniqueName': f"{hierarchy}.[{lv['level_name']}]",
                        'memberCount': None  # Will be populated if CSV cached
                    }
                    for lv in levels
                ],
                'type': 'dimension'
            })
        
        return result
    
    def _get_apartados_sync(self, catalog: str) -> List[Dict]:
        """Extrae apartados (grupos temáticos) del catálogo
        
        Similar a DGIS_SCAN_2 líneas 947-983:
        - Busca jerarquías con 'APARTADO' en el nombre
        - Filtra por NIVEL_NOMBRE == 'Apartado' o cuenta de '&' en MIEMBRO_UNIQUE_NAME
        """
        df_members = self._tool.load_catalog_members_csv(catalog)
        if df_members is None:
            return []
        
        # Buscar jerarquía de apartados
        mask_hier = df_members['JERARQUIA'].str.upper().str.contains('APARTADO', na=False)
        df_vars = df_members[mask_hier].copy()
        
        if df_vars.empty:
            return []
        
        # Filtrar solo apartados (no variables hijas)
        if 'NIVEL_NOMBRE' in df_vars.columns:
            apartados = df_vars[df_vars['NIVEL_NOMBRE'] == 'Apartado'].copy()
        else:
            # Fallback: contar '&' en unique name
            # Apartado tiene 1 '&', Variable tiene 2+
            df_vars['ampersand_count'] = df_vars['MIEMBRO_UNIQUE_NAME'].str.count(r'\.\&\[')
            apartados = df_vars[df_vars['ampersand_count'] == 1].copy()
            
            if apartados.empty:
                # Último recurso: tomar todos únicos
                apartados = df_vars.drop_duplicates(subset=['MIEMBRO_UNIQUE_NAME']).copy()
        
        apartados = apartados.sort_values('MIEMBRO_CAPTION')
        
        return [
            {
                'id': str(idx),
                'name': ap.get('MIEMBRO_CAPTION', ''),
                'uniqueName': ap.get('MIEMBRO_UNIQUE_NAME', ''),
                'hierarchy': ap.get('JERARQUIA', '')
            }
            for idx, ap in enumerate(apartados.to_dict('records'), 1)
        ]
    
    def _get_variables_sync(self, catalog: str, apartado_ids: str = None) -> List[Dict]:
        """Extrae variables filtradas por apartados seleccionados
        
        Args:
            catalog: Nombre del catálogo
            apartado_ids: String con IDs de apartados (ej: "1,3,5-10,15")
                         Si es None o vacío, retorna todas las variables
        
        Returns:
            Lista de variables con id, name, uniqueName, apartado
        
        Similar a DGIS_SCAN_2 líneas 1031-1050
        """
        from utils import parse_ranges
        
        df_members = self._tool.load_catalog_members_csv(catalog)
        if df_members is None:
            return []
        
        # Buscar jerarquía de apartados
        mask_hier = df_members['JERARQUIA'].str.upper().str.contains('APARTADO', na=False)
        df_vars = df_members[mask_hier].copy()
        
        if df_vars.empty:
            return []
        
        # Si no se especificaron apartados, retornar todas las variables
        if not apartado_ids or not apartado_ids.strip():
            # Filtrar solo variables (no apartados)
            if 'NIVEL_NOMBRE' in df_vars.columns:
                variables = df_vars[df_vars['NIVEL_NOMBRE'] == 'Variable'].copy()
            else:
                # Contar '&' - variables tienen 2+ '&'
                df_vars['ampersand_count'] = df_vars['MIEMBRO_UNIQUE_NAME'].str.count(r'\.\&\[')
                variables = df_vars[df_vars['ampersand_count'] >= 2].copy()
            
            return self._format_variables(variables)
        
        # Parsear IDs y filtrar apartados
        selected_ids = parse_ranges(apartado_ids)
        apartados_list = self._get_apartados_sync(catalog)
        
        # Filtrar apartados por IDs seleccionados
        selected_apartados = [
            ap for ap in apartados_list
            if int(ap['id']) in selected_ids
        ]
        
        if not selected_apartados:
            return []
        
        # Obtener variables hijas de cada apartado seleccionado
        all_variables = []
        
        for apartado in selected_apartados:
            parent_unique = apartado['uniqueName']
            
            # Buscar variables que tengan este apartado como padre
            if 'PARENT_UNIQUE_NAME' in df_vars.columns:
                vars_from_apartado = df_vars[
                    df_vars['PARENT_UNIQUE_NAME'] == parent_unique
                ].copy()
            else:
                # Fallback: buscar por patrón en unique name
                # Las variables contienen el unique name del apartado
                vars_from_apartado = df_vars[
                    df_vars['MIEMBRO_UNIQUE_NAME'].str.contains(
                        parent_unique.replace('[', r'\[').replace(']', r'\]'),
                        regex=True,
                        na=False
                    ) &
                    (df_vars['MIEMBRO_UNIQUE_NAME'] != parent_unique)
                ].copy()
            
            for _, var_row in vars_from_apartado.iterrows():
                all_variables.append({
                    'id': str(len(all_variables) + 1),
                    'name': var_row.get('MIEMBRO_CAPTION', ''),
                    'uniqueName': var_row.get('MIEMBRO_UNIQUE_NAME', ''),
                    'apartado': apartado['name'],
                    'hierarchy': var_row.get('JERARQUIA', '')
                })
        
        return all_variables
    
    def _format_variables(self, df_variables) -> List[Dict]:
        """Helper para formatear DataFrame de variables a lista de dicts"""
        return [
            {
                'id': str(idx),
                'name': var.get('MIEMBRO_CAPTION', ''),
                'uniqueName': var.get('MIEMBRO_UNIQUE_NAME', ''),
                'hierarchy': var.get('JERARQUIA', ''),
                'apartado': 'N/A'
            }
            for idx, var in enumerate(df_variables.to_dict('records'), 1)
        ]
    
    
    def _get_members_sync(
        self, 
        catalog: str,
        dimension: str, 
        hierarchy: str, 
        level: str
    ) -> List[Dict]:
        """Obtiene miembros de un nivel específico"""
        df_members = self._tool.load_catalog_members_csv(catalog)
        if df_members is None:
            return []
        
        members = self._tool.get_dimension_members(
            df_members, dimension, hierarchy, level
        )
        
        return [
            {
                'caption': m.get('MIEMBRO_CAPTION', ''),
                'uniqueName': m.get('MIEMBRO_UNIQUE_NAME', '')
            }
            for m in members
        ]
    
    def _execute_mdx_sync(self, catalog: str, mdx: str) -> Dict:
        """Ejecuta consulta MDX y devuelve resultados serializables"""
        df = self._tool.execute_mdx(catalog, mdx)
        
        if df.empty:
            return {'rows': [], 'columns': [], 'rowCount': 0}
        
        # Sanitizar DataFrame para JSON - reemplazar valores no válidos
        import numpy as np
        df_clean = df.replace({
            pd.NaT: None, 
            pd.NA: None,
            np.nan: None,
            np.inf: None,
            -np.inf: None
        })
        
        # Convertir a formato AG Grid
        return {
            'rows': df_clean.to_dict('records'),
            'columns': [
                {'field': col, 'headerName': col, 'sortable': 'true', 'filter': 'true'}
                for col in df.columns
            ],
            'rowCount': len(df)
        }
    
    def _build_and_execute_query_sync(self, request: Dict) -> Dict:
        """
        Construye y ejecuta query desde estructura de request
        
        Args:
            request: {
                'catalog': str,
                'measures': [{'uniqueName': str}],
                'rows': [{'dimension': str, 'hierarchy': str, 'level': str, 'members': [str]}],
                'filters': [{'dimension': str, 'hierarchy': str, 'members': [str]}]
            }
        """
        catalog = request['catalog']
        measures = request.get('measures', [])
        variables = request.get('variables', [])
        rows_config = request.get('rows', [])
        filters = request.get('filters', [])
        
        # Construir MDX
        # COLUMNS: Variables (wizard) o Medidas (UI antigua)
        # Priorizar variables si están presentes
        items_for_columns = variables if variables else measures
        
        if not items_for_columns:
            raise ValueError("Debe especificar al menos una medida o variable")
        
        if len(items_for_columns) == 1:
            columns_clause = f"{{ {items_for_columns[0]['uniqueName']} }}"
        else:
            items_list = ", ".join([item['uniqueName'] for item in items_for_columns])
            columns_clause = f"{{ {items_list} }}"
        
        # ROWS: Dimensiones con CROSSJOIN
        rows_parts = []
        for row in rows_config:
            mdx_path = self._build_level_mdx(row)
            rows_parts.append(mdx_path)
        
        # Combinar con CROSSJOIN
        if len(rows_parts) == 0:
            return {'error': 'No rows specified'}
        elif len(rows_parts) == 1:
            rows_clause = rows_parts[0]
        else:
            rows_clause = rows_parts[0]
            for part in rows_parts[1:]:
                rows_clause = f"CROSSJOIN({part}, {rows_clause})"
        
        # Incorporar filtros en ROWS (solo si tienen miembros Y no están ya en rows)
        for filt in filters:
            if filt.get('members') and len(filt['members']) > 0:
                # Verificar si la jerarquía del filtro ya está en rows
                filt_hierarchy = filt.get('hierarchy', '')
                hierarchy_in_rows = any(
                    row.get('hierarchy', '') == filt_hierarchy 
                    for row in rows_config
                )
                
                # Solo agregar el filtro si su jerarquía NO está en rows
                if not hierarchy_in_rows:
                    members_list = ", ".join(filt['members'])
                    filter_set = f"{{ {members_list} }}"
                    rows_clause = f"CROSSJOIN({filter_set}, {rows_clause})"

        
        # Obtener nombre del cubo
        cube_name = f"[{catalog}]"
        try:
            with ConnectionManager(self.config, catalog) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT CUBE_NAME FROM $system.MDSCHEMA_CUBES")
                cubes = cursor.fetchall()
                if cubes:
                    cube_name = f"[{cubes[0][0]}]"
        except:
            pass
        
        # Ensamblar MDX
        mdx = f"""SELECT 
    {columns_clause} ON COLUMNS,
    NON EMPTY {rows_clause} ON ROWS
FROM {cube_name}"""
        
        # Ejecutar
        return self._execute_mdx_sync(catalog, mdx)
    
    def _build_level_mdx(self, row_config: Dict) -> str:
        """Construye la parte MDX para un nivel"""
        level_name = row_config['level']
        hierarchy = row_config['hierarchy']
        
        # Si es nivel genérico (Nivel 2, Nivel 3)
        if level_name.startswith("Nivel "):
            depth = row_config.get('depth', 1)
            return f"{hierarchy}.Levels({depth}).MEMBERS"
        
        # Si el level es "All.UNKNOWNMEMBER" o similar, extraer el nombre real de la jerarquía
        if "All" in level_name or "UNKNOWNMEMBER" in level_name:
            # Extraer el último elemento de la jerarquía como level name
            # Ej: [DIM UNIDAD].[CLUES] -> CLUES
            if '.' in hierarchy:
                actual_level = hierarchy.split('.')[-1].strip('[]')
                return f"{hierarchy}.[{actual_level}].MEMBERS"
            else:
                # Fallback: usar hierarchy.MEMBERS
                return f"{hierarchy}.MEMBERS"
        
        return f"{hierarchy}.[{level_name}].MEMBERS"
    
    # ========== MÉTODOS ASÍNCRONOS (API FastAPI/NiceGUI) ==========
    
    @com_thread_safe
    def get_catalogs(self) -> List[Dict]:
        return self._get_catalogs_sync()
    
    @com_thread_safe
    def get_measures(self, catalog: str) -> List[Dict]:
        return self._get_measures_sync(catalog)
    
    @com_thread_safe
    def get_dimensions(self, catalog: str) -> List[Dict]:
        return self._get_dimensions_sync(catalog)
    
    @com_thread_safe
    def get_apartados(self, catalog: str) -> List[Dict]:
        return self._get_apartados_sync(catalog)
    
    @com_thread_safe
    def get_variables(self, catalog: str, apartado_ids: str = None) -> List[Dict]:
        return self._get_variables_sync(catalog, apartado_ids)
    
    @com_thread_safe
    def get_members(
        self, 
        catalog: str, 
        dimension: str, 
        hierarchy: str, 
        level: str
    ) -> List[Dict]:
        return self._get_members_sync(catalog, dimension, hierarchy, level)
    
    @com_thread_safe
    def execute_query(self, request: Dict) -> Dict:
        return self._build_and_execute_query_sync(request)


# Instancia global (singleton)
_service_instance: Optional[OlapService] = None

def get_service() -> OlapService:
    """Dependency injection para FastAPI"""
    global _service_instance
    if _service_instance is None:
        if not COM_AVAILABLE:
            try:
                from mock_service import SnapshotOlapService
                _service_instance = SnapshotOlapService()
            except ImportError as e:
                import logging
                logging.getLogger(__name__).error(f"Could not load SnapshotOlapService: {e}")
                _service_instance = OlapService()
        else:
            _service_instance = OlapService()
    return _service_instance
