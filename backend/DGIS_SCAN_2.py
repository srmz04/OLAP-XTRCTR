#!/usr/bin/env python3
"""
DGIS OLAP Full Discovery Scanner v4.0
Descubre TODA la estructura accesible del servidor MSOLAP de forma segura y eficiente.
Incluye: Metadatos, Schemas, Rowsets, Propiedades del servidor, Roles, Permisos
"""

import sys
import os
import time
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps, lru_cache
from dataclasses import dataclass, asdict

# ============================================================================
# CONFIGURACIÓN DE ENTORNO Y CONSOLA
# ============================================================================

try:
    import colorama
    from colorama import Fore, Style, Back
    colorama.init(autoreset=True)
except ImportError:
    class ColorStub:
        def __getattr__(self, name): return ""
    Fore = Style = Back = ColorStub()

try:
    import pandas as pd
    import openpyxl
    try:
        import adodbapi
        ADODB_AVAILABLE = True
    except ImportError:
        ADODB_AVAILABLE = False
except ImportError as e:
    print(f"\n{Fore.RED}[ERROR CRITICO] Faltan dependencias{Style.RESET_ALL}")
    print(f"Falta la libreria: {e.name}")
    # sys.exit(1) # DISABLED FOR LINUX MOCK MODE

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# Rich for enhanced CLI visuals
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.layout import Layout
    from rich.text import Text
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None

# Validators (local module)
try:
    from validators import validate_selection, sanitize_search
    VALIDATORS_AVAILABLE = True
except ImportError:
    # Fallback: no validation
    VALIDATORS_AVAILABLE = False
    def validate_selection(inp, max_val):
        return True, list(map(int, inp.replace(' ','').replace('-',',').split(','))), ""
    def sanitize_search(text):
        return True, text, ""


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

@dataclass
class Config:
    """Configuración centralizada"""
    server: str = "reportesdgis.salud.gob.mx"
    user: str = "PWIDGISREPORTES\\DGIS15"
    password: str = "Temp123!"
    
    # Performance
    max_workers: int = 3
    connection_timeout: int = 30
    query_timeout: int = 60
    
    # Output
    output_dir: str = "olap_discovery"
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "olap_discovery.log"
    
    def __post_init__(self):
        Path(self.output_dir).mkdir(exist_ok=True)


# ============================================================================
# LOGGING
# ============================================================================

class ColoredFormatter(logging.Formatter):
    """Formatter con colores para consola"""
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.MAGENTA + Style.BRIGHT,
    }
    
    def format(self, record):
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{Style.RESET_ALL}"
        return super().format(record)


def setup_logging(config: Config):
    """Configura logging"""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config.log_level.upper()))
    logger.handlers.clear()
    
    fh = logging.FileHandler(config.log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(getattr(logging, config.log_level.upper()))
    ch.setFormatter(ColoredFormatter('%(levelname)s - %(message)s'))
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


# ============================================================================
# UTILIDADES
# ============================================================================

def retry_on_failure(max_retries: int = 3, delay: float = 2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (2 ** attempt))
            if last_exception:
                raise last_exception
        return wrapper
    return decorator


def rows_to_df(cursor, rows) -> pd.DataFrame:
    if rows is None or len(rows) == 0:
        if getattr(cursor, "description", None):
            cols = [c[0] for c in cursor.description]
            return pd.DataFrame(columns=cols)
        return pd.DataFrame()
    cols = [c[0] for c in cursor.description] if getattr(cursor, "description", None) else None
    return pd.DataFrame(list(rows), columns=cols) if cols else pd.DataFrame(list(rows))


# ============================================================================
# GESTOR DE CONEXIONES
# ============================================================================

class ConnectionManager:
    def __init__(self, config: Config, catalog: str = None):
        self.config = config
        self.catalog = catalog
        self.conn = None
        self.logger = logging.getLogger(__name__)

    def __enter__(self):
        self.conn = self._create_connection()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            try:
                self.conn.close()
            except:
                pass

    @retry_on_failure(max_retries=2)
    def _create_connection(self):
        if not globals().get('ADODB_AVAILABLE', False):
             raise ImportError("adodbapi no está disponible. No se puede conectar al servidor OLAP.")

        conn_str = (
            "Provider=MSOLAP;"
            f"Data Source={self.config.server};"
            "Persist Security Info=True;"
            f"User ID={self.config.user};"
            f"Password={self.config.password};"
        )
        if self.catalog:
            conn_str += f"Initial Catalog={self.catalog};"
        try:
            return adodbapi.connect(conn_str, timeout=self.config.connection_timeout)
        except Exception as e:
            if "Dispatch('ADODB.Connection') failed" in str(e):
                self.logger.critical(f"\n{Fore.RED}[ERROR CRITICO] Fallo en driver ADODB{Style.RESET_ALL}")
            raise e


# ============================================================================
# SCHEMA INSPECTOR
# ============================================================================

class SchemaInspector:
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()
    
    def get_available_columns(self, cursor, schema_name: str) -> Set[str]:
        cache_key = schema_name
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
        try:
            cursor.execute(f"SELECT * FROM {schema_name} WHERE 1=0")
            available = {col[0].upper() for col in cursor.description} if cursor.description else set()
            with self._lock:
                self._cache[cache_key] = available
            return available
        except:
            return set()
    
    def is_schema_available(self, cursor, schema_name: str) -> bool:
        try:
            cursor.execute(f"SELECT * FROM {schema_name} WHERE 1=0")
            return True
        except:
            return False


# ============================================================================
# SERVIDOR DISCOVERY
# ============================================================================

class ServerDiscovery:
    ALL_SYSTEM_ROWSETS = [
        "$system.DISCOVER_SCHEMA_ROWSETS",
        "$system.DBSCHEMA_CATALOGS",
        "$system.MDSCHEMA_CUBES",
        "$system.MDSCHEMA_DIMENSIONS",
        "$system.MDSCHEMA_HIERARCHIES",
        "$system.MDSCHEMA_LEVELS",
        "$system.MDSCHEMA_MEMBERS",
        "$system.MDSCHEMA_MEASURES",
        "$system.DISCOVER_SESSIONS",
        "$system.DISCOVER_CONNECTIONS",
    ]
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.inspector = SchemaInspector()
        self.discovery_results = {
            'server_info': {},
            'available_rowsets': [],
            'catalogs': [],
            'errors': []
        }
    
    def _check_rowset(self, rowset: str) -> Optional[Dict]:
        try:
            with ConnectionManager(self.config) as conn:
                cursor = conn.cursor()
                if self.inspector.is_schema_available(cursor, rowset):
                    columns = list(self.inspector.get_available_columns(cursor, rowset))
                    return {'rowset': rowset, 'columns': columns}
        except:
            pass
        return None

    def discover_available_rowsets(self):
        self.logger.info("[BUSCANDO] Escaneando rowsets disponibles...")
        available = []
        total_rowsets = len(self.ALL_SYSTEM_ROWSETS)
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_rowset = {executor.submit(self._check_rowset, r): r for r in self.ALL_SYSTEM_ROWSETS}
            
            # Progress bar si tqdm disponible
            if TQDM_AVAILABLE:
                futures_iter = tqdm(as_completed(future_to_rowset), 
                                   total=total_rowsets,
                                   desc="Escaneando schemas",
                                    bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}')
            else:
                futures_iter = as_completed(future_to_rowset)
            
            for future in futures_iter:
                result = future.result()
                if result:
                    available.append(result)
        
        self.discovery_results['available_rowsets'] = available
        self.logger.info(f"   [OK] Rowsets disponibles: {len(available)}")
    
    def discover_generic(self, query_name: str, query: str, result_key: str):
        self.logger.info(f"[BUSCANDO] Descubriendo {query_name}...")
        try:
            with ConnectionManager(self.config) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                df = rows_to_df(cursor, cursor.fetchall())
                if not df.empty:
                    self.discovery_results[result_key] = df.to_dict('records')
                    self.logger.info(f"   [OK] {query_name}: {len(df)}")
                else:
                    self.logger.info(f"   [INFO] {query_name}: 0 encontrados")
        except Exception as e:
            self.logger.debug(f"No se pudo obtener {query_name}: {e}")
            self.discovery_results['errors'].append({'operation': result_key, 'error': str(e)})

    def full_discovery(self):
        self.logger.info("\n" + "="*70)
        self.logger.info(f"{Fore.CYAN}[INICIO] DESCUBRIMIENTO COMPLETO DEL SERVIDOR{Style.RESET_ALL}")
        self.logger.info("="*70 + "\n")
        
        self.discover_generic('Propiedades', "SELECT * FROM $system.DISCOVER_PROPERTIES", 'properties')
        self.discover_available_rowsets()
        self.discover_generic('Catalogos', "SELECT * FROM $system.DBSCHEMA_CATALOGS", 'catalogs')
        
        return self.discovery_results
    
    def export_results(self, results: Dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = Path(self.config.output_dir) / f"server_discovery_{timestamp}.xlsx"
        self.logger.info(f"[EXPORTANDO] Generando Excel: {excel_path}")
        
        try:
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                if results.get('catalogs'):
                    pd.DataFrame(results['catalogs']).to_excel(writer, sheet_name='Catalogos', index=False)
                if results.get('available_rowsets'):
                    pd.DataFrame(results['available_rowsets']).to_excel(writer, sheet_name='Rowsets', index=False)
            self.logger.info(f"{Fore.GREEN}[EXITO] Excel exportado{Style.RESET_ALL}")
        except Exception as e:
            self.logger.error(f"Error exportando: {e}")


# ============================================================================
# EXPLORADOR DE CATÁLOGOS
# ============================================================================

class CatalogExplorer:
    """Explora un catálogo específico"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.inspector = SchemaInspector()
    
    def extract_all_metadata(self, catalog: str) -> Dict:
        """Extrae TODOS los metadatos de un catálogo, incluyendo miembros"""
        self.logger.info(f"\n[EXPLORANDO] Catalogo: {Fore.CYAN}{catalog}{Style.RESET_ALL}")
        
        metadata = {
            'catalog_name': catalog,
            'timestamp': datetime.now().isoformat()
        }
        
        # Consultas ampliadas para obtener detalle completo
        queries = {
            'cubes': ("$system.MDSCHEMA_CUBES", "Cubos"),
            'dimensions': ("$system.MDSCHEMA_DIMENSIONS", "Dimensiones"),
            'hierarchies': ("$system.MDSCHEMA_HIERARCHIES", "Jerarquias"),
            'levels': ("$system.MDSCHEMA_LEVELS", "Niveles (Variables)"),
            'measures': ("$system.MDSCHEMA_MEASURES", "Medidas"),
            'members': ("$system.MDSCHEMA_MEMBERS", "Miembros (Valores)"), # AQUI ESTA EL DETALLE DE VALORES
            'properties': ("$system.MDSCHEMA_PROPERTIES", "Propiedades"),
        }
        
        try:
            with ConnectionManager(self.config, catalog) as conn:
                cursor = conn.cursor()
                
                for key, (schema, label) in queries.items():
                    try:
                        if self.inspector.is_schema_available(cursor, schema):
                            self.logger.info(f"   ... Descargando {label}")
                            
                            # Para miembros, intentamos limitar si es demasiado grande, o traer todo
                            # En este caso traemos todo porque el usuario pidio "todas y cada una"
                            cursor.execute(f"SELECT * FROM {schema}")
                            
                            # Usamos fetchmany en bucle para no saturar RAM de golpe si son millones
                            rows = []
                            while True:
                                chunk = cursor.fetchmany(10000)
                                if not chunk:
                                    break
                                rows.extend(chunk)
                                
                            df = rows_to_df(cursor, rows)
                            
                            if not df.empty:
                                metadata[key] = df.to_dict('records')
                                self.logger.info(f"   [OK] {label}: {len(df)} registros")
                            else:
                                self.logger.info(f"   [INFO] {label}: 0 registros")
                    except Exception as e:
                        self.logger.debug(f"Error en {label}: {e}")
                        
        except Exception as e:
            self.logger.error(f"Error conectando al catalogo {catalog}: {e}")
            metadata['error'] = str(e)
            
        return metadata

    def export_catalog_metadata(self, metadata: Dict):
        """Exporta metadatos a Excel y automáticamente genera CSV de miembros"""
        catalog_name = metadata['catalog_name']
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = Path(self.config.output_dir) / f"catalog_{catalog_name}_{timestamp}.xlsx"
        
        try:
            self.logger.info(f"[EXPORTANDO] Guardando datos detallados en Excel...")
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                # Resumen
                pd.DataFrame({'Info': ['Catalogo', 'Fecha'], 'Valor': [catalog_name, metadata['timestamp']]}).to_excel(writer, sheet_name='RESUMEN', index=False)
                
                # Exportar cada dataset
                for key, data in metadata.items():
                    if isinstance(data, list) and data:
                        df = pd.DataFrame(data)
                        # Limpiar caracteres ilegales para Excel
                        df = df.astype(str).replace(r'[\x00-\x1F\x7F]', '', regex=True)
                        
                        sheet_name = key[:30] # Excel limita nombres a 31 chars
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                        
            self.logger.info(f"{Fore.GREEN}[EXITO] Reporte generado: {excel_path}{Style.RESET_ALL}")
            
            # AUTO-EXPORT: Generar CSV de miembros si existe
            if 'members' in metadata and metadata['members']:
                csv_filename = f"{catalog_name}_miembros_completos.csv"
                csv_path = Path(self.config.output_dir).parent / csv_filename
                
                members_df = pd.DataFrame(metadata['members'])
                members_df.to_csv(csv_path, index=False)
                
                self.logger.info(f"{Fore.GREEN}✓ CSV de miembros: {csv_path}{Style.RESET_ALL}")
                self.logger.info(f"{Fore.CYAN}  (También usado como cache para Opción 4: DATA){Style.RESET_ALL}")
            
            return None
        except Exception as e:
            self.logger.error(f"Error exportando catalogo: {e}")
            return None

    def download_members_only(self, catalog: str) -> bool:
        """Descarga SOLO los miembros de un catálogo (rápido) para cache"""
        try:
            self.logger.info(f"[DESCARGANDO] Miembros de {catalog}...")
            
            with ConnectionManager(self.config, catalog) as conn:
                cursor = conn.cursor()
                
                # Query ultra-simple para compatibilidad total (incluso catálogos 2010-2012)
                query = "SELECT * FROM $system.MDSCHEMA_MEMBERS"
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                # Convertir a DataFrame
                members_df = rows_to_df(cursor, rows)
                
                if members_df.empty:
                    self.logger.warning(f"No se encontraron miembros en {catalog}")
                    return False
                
                # DEBUG: Imprimir columnas disponibles
                self.logger.info(f"Columnas disponibles en MDSCHEMA_MEMBERS: {members_df.columns.tolist()}")

                
                # Seleccionar solo las columnas necesarias si existen
                required_cols = {
                    'DIMENSION_UNIQUE_NAME': 'DIMENSION',
                    'HIERARCHY_UNIQUE_NAME': 'JERARQUIA',
                    'LEVEL_NAME': 'NIVEL_NOMBRE',
                    'MEMBER_CAPTION': 'MIEMBRO_CAPTION',
                    'MEMBER_UNIQUE_NAME': 'MIEMBRO_UNIQUE_NAME',
                    'MEMBER_ORDINAL': 'MIEMBRO_ORDINAL',
                    'MEMBER_KEY': 'MIEMBRO_KEY',
                    'ORDINAL': 'ORDINAL'
                }
                
                # Filtrar columnas que existen
                existing_cols = {old: new for old, new in required_cols.items() if old in members_df.columns}
                
                if not existing_cols:
                    self.logger.error(f"No se encontraron columnas esperadas en {catalog}")
                    return False
                
                # Seleccionar solo columnas necesarias
                members_df = members_df[list(existing_cols.keys())]
                
                # Filtrar miembros "All" si la columna existe
                if 'MEMBER_CAPTION' in members_df.columns:
                    members_df = members_df[members_df['MEMBER_CAPTION'] != 'All']
                
                # Renombrar columnas
                members_df.rename(columns=existing_cols, inplace=True)
                
                # Guardar CSV en cache
                # V2: Usar nuevo nombre de archivo
                csv_filename = f"{catalog}_miembros_completos_v2.csv"
                csv_path = Path(self.config.output_dir).parent / csv_filename
                members_df.to_csv(csv_path, index=False)
                
                # Verificar que el archivo realmente se escribió (fix para VirtualBox shared folders)
                import time
                for _ in range(5):
                    if csv_path.exists() and csv_path.stat().st_size > 0:
                        break
                    time.sleep(0.5)
                
                self.logger.info(f"{Fore.GREEN}✓ {len(members_df)} miembros guardados en cache{Style.RESET_ALL}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error descargando miembros: {e}")
            return False



# ============================================================================
# HERRAMIENTA DE CONSULTAS MDX (DATOS)
# ============================================================================

class MDXQueryTool:
    """Herramienta para construir y ejecutar consultas MDX de datos"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def get_measures(self, catalog: str) -> List[Dict]:
        """Obtiene lista de medidas disponibles"""
        try:
            with ConnectionManager(self.config, catalog) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM $system.MDSCHEMA_MEASURES")
                df = rows_to_df(cursor, cursor.fetchall())
                
                if not df.empty:
                    # Verificar qué columnas existen y usar las disponibles
                    required_cols = []
                    if 'MEASURE_NAME' in df.columns:
                        required_cols.append('MEASURE_NAME')
                    if 'MEASURE_UNIQUE_NAME' in df.columns:
                        required_cols.append('MEASURE_UNIQUE_NAME')
                    
                    if required_cols:
                        # Filtrar medidas visibles si la columna existe
                        if 'MEASURE_IS_VISIBLE' in df.columns:
                            df = df[df['MEASURE_IS_VISIBLE'] == True]
                        
                        result = df[required_cols].drop_duplicates().to_dict('records')
                        self.logger.info(f"   [OK] Encontradas {len(result)} medidas")
                        return result
        except Exception as e:
            self.logger.error(f"Error obteniendo medidas: {e}")
        return []

    def get_hierarchies(self, catalog: str) -> List[Dict]:
        """Obtiene lista de jerarquías navegables (las dimensiones con sus jerarquías específicas)"""
        try:
            with ConnectionManager(self.config, catalog) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM $system.MDSCHEMA_HIERARCHIES")
                df = rows_to_df(cursor, cursor.fetchall())
                
                if not df.empty:
                    # Verificar columnas disponibles
                    required_cols = []
                    if 'HIERARCHY_NAME' in df.columns:
                        required_cols.append('HIERARCHY_NAME')
                    if 'HIERARCHY_UNIQUE_NAME' in df.columns:
                        required_cols.append('HIERARCHY_UNIQUE_NAME')
                    if 'DIMENSION_UNIQUE_NAME' in df.columns:
                        required_cols.append('DIMENSION_UNIQUE_NAME')
                    
                    if required_cols:
                        # Filtrar jerarquías visibles si la columna existe
                        if 'HIERARCHY_IS_VISIBLE' in df.columns:
                            df = df[df['HIERARCHY_IS_VISIBLE'] == True]
                        
                        result = df[required_cols].drop_duplicates().to_dict('records')
                        self.logger.info(f"   [OK] Encontradas {len(result)} jerarquias")
                        return result
        except Exception as e:
            self.logger.error(f"Error obteniendo jerarquias: {e}")
        return []

    def execute_mdx(self, catalog: str, query: str) -> pd.DataFrame:
        """Ejecuta una consulta MDX arbitraria"""
        self.logger.info(f"[MDX] Ejecutando consulta en {catalog}...")
        try:
            with ConnectionManager(self.config, catalog) as conn:
                cursor = conn.cursor()
                start_time = time.time()
                cursor.execute(query)
                rows = cursor.fetchall()
                elapsed = time.time() - start_time
                
                df = rows_to_df(cursor, rows)
                self.logger.info(f"   [OK] Completado en {elapsed:.2f}s: {len(df)} filas")
                return df
        except Exception as e:
            self.logger.error(f"Error ejecutando MDX: {e}")
            print(f"\n{Fore.RED}[ERROR] Fallo al ejecutar consulta MDX:{Style.RESET_ALL}")
            print(f"{Fore.RED}{e}{Style.RESET_ALL}")
            return pd.DataFrame()

    def export_data(self, df: pd.DataFrame, base_filename: str):
        """Exporta datos a CSV (rápido) o Excel (lento) con progress bar"""
        if df.empty:
            print(f"{Fore.YELLOW}[!] No hay datos para exportar{Style.RESET_ALL}")
            return
        
        path = Path(self.config.output_dir) / f"{base_filename}.xlsx"
        row_count = len(df)
        
        try:
            # Advertencia para datasets grandes
            if row_count > 100000:
                print(f"\n{Fore.YELLOW}╔═══ DATASET GRANDE ═══╗{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Filas: {row_count:,}{Style.RESET_ALL}")
                print(f"\n{Fore.CYAN}Opciones de exportación:{Style.RESET_ALL}")
                print(f"  1. CSV (.csv) - ⚡ RÁPIDO (~5 segundos)")
                print(f"  2. Excel (.xlsx) - 🐌 LENTO (~{estimate_export_time(row_count)} minutos)")
                
                choice = safe_input(f"\n{Fore.CYAN}>> Formato (1/2):{Style.RESET_ALL} ").strip()
                use_csv = choice == '1'
            else:
                # Para datasets pequeños, preguntar formato
                print(f"\n{Fore.CYAN}Formato de exportación:{Style.RESET_ALL}")
                print(f"  1. CSV (.csv) - Rápido, abre en Excel")
                print(f"  2. Excel (.xlsx) - Con formato")
                
                choice = safe_input(f"\n{Fore.CYAN}>> Formato (1/2, Enter=CSV):{Style.RESET_ALL} ").strip()
                use_csv = choice != '2'
            
            if use_csv:
                # EXPORT CSV (rápido)
                csv_path = Path(self.config.output_dir) / f"{base_filename}.csv"
                print(f"\n{Fore.CYAN}[EXPORTANDO] Guardando CSV...{Style.RESET_ALL}")
                
                if TQDM_AVAILABLE and row_count > 10000:
                    with tqdm(total=100, desc="Escribiendo CSV", bar_format='{desc}: {percentage:3.0f}%|{bar}|') as pbar:
                        df.to_csv(csv_path, index=False)
                        pbar.update(100)
                else:
                    df.to_csv(csv_path, index=False)
                
                print(f"{Fore.GREEN}✓ Exportado: {csv_path}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}✓ Tamaño: {csv_path.stat().st_size / 1024 / 1024:.2f} MB{Style.RESET_ALL}")
            else:
                # EXPORT EXCEL (lento)
                print(f"\n{Fore.CYAN}[EXPORTANDO] Guardando Excel (esto puede tardar)...{Style.RESET_ALL}")
                
                # Limpiar caracteres ilegales
                df = df.astype(str).replace(r'[\x00-\x1F\x7F]', '', regex=True)
                
                if TQDM_AVAILABLE and row_count > 10000:
                    with tqdm(total=100, desc="Escribiendo Excel", bar_format='{desc}: {percentage:3.0f}%|{bar}|') as pbar:
                        df.to_excel(path, index=False, engine='openpyxl')
                        pbar.update(100)
                else:
                    df.to_excel(path, index=False, engine='openpyxl')
                
                print(f"{Fore.GREEN}✓ Exportado: {path}{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"{Fore.RED}[ERROR] Fallo al exportar: {e}{Style.RESET_ALL}")

    def load_catalog_members_csv(self, catalog: str) -> Optional[pd.DataFrame]:
        """Carga el CSV de miembros del catálogo con cache automático"""
        # V2: Forzar nuevo cache con columnas de ordenamiento
        csv_filename = f"{catalog}_miembros_completos_v2.csv"
        csv_path = Path(self.config.output_dir).parent / csv_filename
        
        # CACHE CHECK + AUTO-DOWNLOAD
        if not csv_path.exists():
            print(f"\n{Fore.YELLOW}[CACHE] No se encontró {csv_filename}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[AUTO] Descargando miembros del catálogo {catalog}...{Style.RESET_ALL}")
            print(f"{Fore.CYAN}      (Esto tomará ~3-5 segundos){Style.RESET_ALL}")
            
            # Descargar automáticamente
            explorer = CatalogExplorer(self.config)
            success = explorer.download_members_only(catalog)
            
            if not success:
                print(f"{Fore.RED}[ERROR] No se pudo descargar miembros{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Sugerencia: Ejecuta Opción 3 (EXPLORE) primero{Style.RESET_ALL}")
                # Si falla descarga, intentar usar cache si existe
                if csv_path.exists():
                     print(f"{Fore.GREEN}[CACHE] Usando cache antiguo como fallback{Style.RESET_ALL}")
                else:
                     return None
            else:
                print(f"{Fore.GREEN}✓ Miembros descargados y guardados en cache{Style.RESET_ALL}")
        else:
            # Usar cache existente
            file_size = csv_path.stat().st_size / 1024 / 1024  # MB
            print(f"\n{Fore.GREEN}[CACHE] Usando {csv_filename} ({file_size:.1f} MB){Style.RESET_ALL}")
        
        # Cargar CSV (ahora garantizado que existe)
        try:
            df = pd.read_csv(csv_path)
            self.logger.info(f"   [OK] Cargados {len(df)} miembros del archivo {csv_filename}")
            return df
        except Exception as e:
            self.logger.error(f"Error cargando CSV: {e}")
            return None

    def get_dimension_members(self, df_members: pd.DataFrame, dimension: str, hierarchy: str, level: str) -> List[Dict]:
        """Obtiene miembros específicos de una dimensión/jerarquía/nivel"""
        # Construcción dinámica del filtro según columnas disponibles
        filters = (df_members['DIMENSION'] == dimension) & (df_members['JERARQUIA'] == hierarchy)
        
        # Agregar filtro de nivel
        if 'NIVEL_NOMBRE' in df_members.columns:
            # Cubo nuevo: filtrar por columna
            filters = filters & (df_members['NIVEL_NOMBRE'] == level)
        else:
            # Cubo viejo: filtrar por profundidad del Unique Name
            # Primero, detectar todos los niveles de esta jerarquía
            extracted_levels = self.extract_levels_from_unique_names(df_members, dimension, hierarchy)
            
            if extracted_levels:
                # Encontrar la profundidad del nivel solicitado
                level_depth = None
                for lev_info in extracted_levels:
                    if lev_info['level_name'] == level:
                        level_depth = lev_info['level_depth']
                        break
                
                if level_depth is not None:
                    # Filtrar miembros que tengan exactamente esa profundidad
                    # Profundidad = número de ocurrencias de '.&[' en el Unique Name
                    temp_members = df_members[filters].copy()
                    temp_members['_depth'] = temp_members['MIEMBRO_UNIQUE_NAME'].str.count(r'\.&\[')
                    filters = filters & (temp_members['_depth'] == level_depth)
        
        # Filtrar "All"
        if 'MIEMBRO_CAPTION' in df_members.columns:
            filters = filters &  (df_members['MIEMBRO_CAPTION'] != 'All')
        
        members = df_members[filters].copy()
        
        # Lógica de ordenamiento robusta
        if 'MIEMBRO_ORDINAL' in members.columns:
            members = members.sort_values('MIEMBRO_ORDINAL')
        elif 'ORDINAL' in members.columns:
            members = members.sort_values('ORDINAL')
        elif 'MIEMBRO_KEY' in members.columns:
            # Intentar convertir KEY a numérico para ordenar correctamente (1, 2, 10...)
            try:
                members['_key_num'] = pd.to_numeric(members['MIEMBRO_KEY'])
                members = members.sort_values('_key_num')
            except:
                # Si no es numérico, usar string
                members = members.sort_values('MIEMBRO_KEY')
        else:
            # Fallback: orden alfabético
            members = members.sort_values('MIEMBRO_CAPTION')
            
        return members[['MIEMBRO_CAPTION', 'MIEMBRO_UNIQUE_NAME']].to_dict('records')
    
    def extract_levels_from_unique_names(self, df_members: pd.DataFrame, dimension: str, hierarchy: str) -> List[Dict]:
        """Extrae niveles de una jerarquía analizando los Unique Names de miembros
        
        Para cubos viejos sin NIVEL_NOMBRE, analiza patrones en MIEMBRO_UNIQUE_NAME.
        Maneja casos donde los niveles intermedios no tienen nombre explícito.
        Ejemplo: [Dim].[Hier].[Entidad].&[1].&[1]&[2] -> Entidad, Nivel 2
        
        Returns: List de dicts con {level_name, level_depth}
        """
        # Filtrar miembros de esta jerarquía
        members_in_hier = df_members[
            (df_members['DIMENSION'] == dimension) &
            (df_members['JERARQUIA'] == hierarchy) &
            (df_members['MIEMBRO_CAPTION'] != 'All')
        ].copy()
        
        if members_in_hier.empty:
            return []
        
        levels_map = {}
        
        # Analizar cada miembro para encontrar estructura
        for _, row in members_in_hier.iterrows():
            unique_name = row['MIEMBRO_UNIQUE_NAME']
            # Contar profundidad en unique name
            depth = unique_name.count('.&[')
            if depth not in levels_map:
                levels_map[depth] = f"Nivel {depth}"
        
        # Si tenemos columna NIVEL_NOMBRE, usarla para mejorar nombres
        if 'NIVEL_NOMBRE' in df_members.columns:
            for depth in levels_map.keys():
                # Encontrar un nombre representativo para este depth
                sample = members_in_hier[members_in_hier['MIEMBRO_UNIQUE_NAME'].str.count(r'\.&\[') == depth]
                if not sample.empty:
                    name = sample.iloc[0]['NIVEL_NOMBRE']
                    levels_map[depth] = name
        
        # Convertir a lista ordenada
        levels_list = [
            {'level_name': name, 'level_depth': depth}
            for depth, name in sorted(levels_map.items())
        ]
        
        return levels_list