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
    import adodbapi
    import openpyxl
except ImportError as e:
    print(f"\n{Fore.RED}[ERROR CRITICO] Faltan dependencias{Style.RESET_ALL}")
    print(f"Falta la libreria: {e.name}")
    sys.exit(1)

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
        
        # ESTRATEGIA ROBUSTA:
        # 1. Buscar los miembros más profundos (Unique Name más largo)
        members_in_hier['len'] = members_in_hier['MIEMBRO_UNIQUE_NAME'].str.len()
        sample_members = members_in_hier.nlargest(50, 'len')['MIEMBRO_UNIQUE_NAME']
        
        levels_found = {}  # {depth: level_name}
        max_depth = 0
        
        for unique_name in sample_members:
            # Contar profundidad real basada en ocurrencias de .&[
            # Esto es lo más fiable para saber cuántos niveles hay
            depth = unique_name.count('.&[')
            if depth > max_depth:
                max_depth = depth
            
            # Intentar extraer nombres explícitos
            # Split por .&[
            parts = unique_name.split('.&[')
            
            # La primera parte contiene la jerarquía y el primer nivel explícito si existe
            # Ejemplo: [D Clues].[Unidad médica].[Entidad]
            first_part = parts[0]
            if '].[' in first_part:
                last_segment = first_part.split('].[')[-1].replace('[', '').replace(']', '')
                # Si el último segmento no es la jerarquía misma, es el Nivel 1
                hier_clean = hierarchy.split('.')[-1].replace('[', '').replace(']', '')
                if last_segment != hier_clean:
                    levels_found[1] = last_segment
        
        # Construir lista final de niveles
        levels_list = []
        for d in range(1, max_depth + 1):
            # Usar nombre encontrado o genérico
            name = levels_found.get(d, f"Nivel {d}")
            
            # Si el nivel 1 se llama igual que la jerarquía, mejor llamarlo "Nivel 1" o dejarlo
            # Pero para Entidad, queremos ver "Entidad"
            
            levels_list.append({
                'level_name': name,
                'level_depth': d
            })
            
        return levels_list
    
    def _show_mdx_preview(self, mdx: str, title: str = "MDX QUERY PREVIEW"):
        """Show MDX with syntax highlighting using rich"""
        if RICH_AVAILABLE:
            syntax = Syntax(mdx, "sql", theme="monokai", line_numbers=False)
            panel = Panel(syntax, title=f"[bold cyan]{title}[/bold cyan]", border_style="cyan")
            console.print(panel)
        else:
            print(f"\n{Fore.CYAN}{'='*70}")
            print(f"[{title}]")
            print(f"{'='*70}{Style.RESET_ALL}")
            print(mdx)
            print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    
    def _show_selection_summary(self, selections: Dict):
        """Show current selections in a nice table"""
        if RICH_AVAILABLE:
            table = Table(title="Current Selection", show_header=True, header_style="bold magenta")
            table.add_column("Category", style="cyan")
            table.add_column("Count", justify="right", style="green")
            table.add_column("Items", style="yellow")
            
            for category, items in selections.items():
                if items:
                    count = len(items) if isinstance(items, list) else 1
                    preview = str(items)[:50] + "..." if len(str(items)) > 50 else str(items)
                    table.add_row(category, str(count), preview)
            
            console.print(table)
        else:
            print(f"\n{Fore.YELLOW}[CURRENT SELECTION]{Style.RESET_ALL}")
            for category, items in selections.items():
                if items:
                    count = len(items) if isinstance(items, list) else 1
                    print(f"  {category}: {count} items")
    
    def _show_validation_warning(self, message: str, suggestion: str = None):
        """Show validation warning"""
        if RICH_AVAILABLE:
            text = Text(message, style="bold red")
            if suggestion:
                text.append(f"\n Suggestion: {suggestion}", style="yellow")
            panel = Panel(text, title="[bold red]VALIDATION ERROR[/bold red]", border_style="red")
            console.print(panel)
        else:
            print(f"\n{Fore.RED}[!] ERROR: {message}{Style.RESET_ALL}")
            if suggestion:
                print(f"{Fore.YELLOW}    Suggestion: {suggestion}{Style.RESET_ALL}")
    
    def _estimate_and_warn_cardinality(self, dimensions: List[Dict], catalog_name: str) -> int:
        """Estimate result size and warn if too large"""
        if not dimensions:
            return 0
        
        # Load members count for estimation
        df = self.load_catalog_members_csv(catalog_name)
        if df is None:
            return 0
        
        estimated = 1
        for dim in dimensions:
            # Intentar filtrar por nivel si existe columna NIVEL_NOMBRE
            if 'NIVEL_NOMBRE' in df.columns:
                count = len(df[
                    (df['DIMENSION'] == dim['dimension']) &
                    (df['JERARQUIA'] == dim['hierarchy']) &
                    (df['NIVEL_NOMBRE'] == dim['level'])
                ])
            else:
                # Si no hay NIVEL_NOMBRE, estimar usando todos los miembros de la jerarquía
                # (Una estimación conservadora es mejor que nada)
                count = len(df[
                    (df['DIMENSION'] == dim['dimension']) &
                    (df['JERARQUIA'] == dim['hierarchy'])
                ])
            
            estimated *= max(count, 1)
        
        if estimated > 100_000:
            self._show_validation_warning(
                f"Large result set: ~{estimated:,} rows estimated",
                "Consider adding filters to reduce result size"
            )
        
        return estimated

    def interactive_hierarchical_builder(self, catalog: str):
        """Constructor interactivo tipo Pivot Table - Sistema completo de navegación"""
        print(f"\n{Fore.CYAN}{'='*70}")
        print(f"[PIVOT TABLE NAVIGATOR] Catálogo: {catalog}")
        print(f"{'='*70}{Style.RESET_ALL}")
        
        # Cargar miembros del CSV
        df_members = self.load_catalog_members_csv(catalog)
        if df_members is None:
            print(f"{Fore.YELLOW}[!] No se puede continuar sin el archivo de miembros{Style.RESET_ALL}")
            return
        
        # ========== PASO 1: MEDIDA ==========
        measures = self.get_measures(catalog)
        if not measures:
            print(f"{Fore.RED}[ERROR] No se encontraron medidas.{Style.RESET_ALL}")
            return

        print(f"\n{Fore.YELLOW}╔═══ PASO 1: MEDIDA (Qué contar) ═══╗{Style.RESET_ALL}")
        for idx, m in enumerate(measures, 1):
            print(f"  {idx}. {m['MEASURE_NAME']}")
        
        print(f"\n{Fore.CYAN}Selección múltiple: 1,2,5-10,15 (mixto permitido){Style.RESET_ALL}")
        sel_m = safe_input(f"{Fore.CYAN}>> Números:{Style.RESET_ALL} ").strip()
        
        # Parsear selección de medidas
        selected_measures = []
        try:
            if '-' in sel_m:
                start, end = map(int, sel_m.split('-'))
                for i in range(start, min(end+1, len(measures)+1)):
                    if 1 <= i <= len(measures):
                        selected_measures.append(measures[i-1])
            else:
                indices = [int(x.strip()) for x in sel_m.split(',')]
                for idx in indices:
                    if 1 <= idx <= len(measures):
                        selected_measures.append(measures[idx-1])
        except:
            print(f"{Fore.RED}[!] Selección inválida{Style.RESET_ALL}")
            return
        
        if not selected_measures:
            print(f"{Fore.RED}[!] Debe seleccionar al menos una medida{Style.RESET_ALL}")
            return
        
        for m in selected_measures:
            print(f"{Fore.GREEN}✓ {m['MEASURE_NAME']}{Style.RESET_ALL}")
        
        # ========== PASO 2: APARTADO ==========
        # Búsqueda dinámica de variables (compatible con sis2011 y nuevos)
        mask_dim = df_members['DIMENSION'].str.upper().str.contains('VARIABLE', na=False)
        mask_hier = df_members['JERARQUIA'].str.upper().str.contains('APARTADO', na=False)
        
        df_vars = df_members[mask_dim & mask_hier].copy()
        
        if df_vars.empty:
            # Fallback: intentar solo por jerarquía
            df_vars = df_members[mask_hier].copy()

        # Filtrar apartados - fallback si no hay NIVEL_NOMBRE
        if 'NIVEL_NOMBRE' in df_vars.columns:
            apartados = df_vars[df_vars['NIVEL_NOMBRE'] == 'Apartado'].copy()
        else:
            # Sin NIVEL_NOMBRE: buscar patrón en Unique Name (ej: [Apartado].&[...])
            # Ojo: En sis2011 los apartados tienen [Apartado].&[Nombre]
            # Y las variables tienen [Apartado].&[Nombre].&[Variable]
            # Así que buscamos los que NO tienen el segundo .&
            
            # Regex: Buscar [Apartado].&[Algo] pero NO seguido de .&[Algo]
            # O más simple: contar los '&'
            # Apartado: [Dim].[Hier].[Apartado].&[A]  (1 '&')
            # Variable: [Dim].[Hier].[Apartado].&[A].&[V] (2 '&')
            
            # Contar ocurrencias de '&['
            apartados = df_vars[
                df_vars['MIEMBRO_UNIQUE_NAME'].str.count(r'&\[') == 1
            ].copy()
            
            if apartados.empty:
                # Fallback simple: usar todos los únicos
                apartados = df_vars.drop_duplicates(subset=['MIEMBRO_UNIQUE_NAME']).copy()
        
        apartados = apartados.sort_values('MIEMBRO_CAPTION')
        
        print(f"\n{Fore.YELLOW}╔═══ PASO 2: APARTADO ({len(apartados)} disponibles) ═══╗{Style.RESET_ALL}")
        filtro = safe_input(f"{Fore.CYAN}>> Buscar (Enter=todos):{Style.RESET_ALL} ").strip().upper()
        
        if filtro:
            apartados_filtered = apartados[apartados['MIEMBRO_CAPTION'].str.upper().str.contains(filtro, na=False)]
        else:
            apartados_filtered = apartados
        
        apartados_list = apartados_filtered.to_dict('records')
        for idx, ap in enumerate(apartados_list, 1):
            print(f"  {idx:3d}. {ap['MIEMBRO_CAPTION']}")
        
        print(f"\n{Fore.CYAN}Selección múltiple: 1,2,5-10,15 (mixto permitido){Style.RESET_ALL}")
        sel_ap = safe_input(f"{Fore.CYAN}>> Números:{Style.RESET_ALL} ").strip()
        
        # Parsear selección de apartados
        selected_apartados = []
        try:
            if '-' in sel_ap:
                start, end = map(int, sel_ap.split('-'))
                for i in range(start, min(end+1, len(apartados_list)+1)):
                    if 1 <= i <= len(apartados_list):
                        selected_apartados.append(apartados_list[i-1])
            else:
                # Soporte para lista separada por comas (1,2,5)
                parts = sel_ap.split(',')
                for part in parts:
                    if '-' in part:
                        s, e = map(int, part.split('-'))
                        for i in range(s, min(e+1, len(apartados_list)+1)):
                             if 1 <= i <= len(apartados_list):
                                selected_apartados.append(apartados_list[i-1])
                    elif part.strip().isdigit():
                        idx = int(part.strip())
                        if 1 <= idx <= len(apartados_list):
                            selected_apartados.append(apartados_list[idx-1])
        except ValueError:
            pass
            
        if not selected_apartados:
            print(f"{Fore.RED}[!] Selección inválida{Style.RESET_ALL}")
            safe_input("\nPresiona Enter para continuar...")
            return
        
        for ap in selected_apartados:
            print(f"{Fore.GREEN}✓ {ap['MIEMBRO_CAPTION']}{Style.RESET_ALL}")
        
        # ========== PASO 3: VARIABLE ==========
        # Combinar variables de TODOS los apartados seleccionados
        all_variables = pd.DataFrame()
        for apartado in selected_apartados:
            parent_unique = apartado['MIEMBRO_UNIQUE_NAME']
            
            if 'PARENT_UNIQUE_NAME' in df_vars.columns:
                vars_from_apartado = df_vars[df_vars['PARENT_UNIQUE_NAME'] == parent_unique].copy()
            else:
                # Fallback: Buscar hijos por prefijo de Unique Name
                # El hijo debe empezar con el unique name del padre
                vars_from_apartado = df_vars[
                    (df_vars['MIEMBRO_UNIQUE_NAME'].str.startswith(parent_unique)) &
                    (df_vars['MIEMBRO_UNIQUE_NAME'] != parent_unique)
                ].copy()
                
            all_variables = pd.concat([all_variables, vars_from_apartado], ignore_index=True)
        
        if all_variables.empty:
            # Usar los apartados como variables
            selected_variables = selected_apartados
            print(f"{Fore.YELLOW}[!] Usando apartados completos (sin variables hijas){Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}╔═══ PASO 3: VARIABLE ({len(all_variables)} disponibles de {len(selected_apartados)} apartado(s)) ═══╗{Style.RESET_ALL}")
            filtro_var = safe_input(f"{Fore.CYAN}>> Buscar (Enter=todas):{Style.RESET_ALL} ").strip().upper()
            
            if filtro_var:
                variables_filtered = all_variables[all_variables['MIEMBRO_CAPTION'].str.upper().str.contains(filtro_var, na=False)]
            else:
                variables_filtered = all_variables
            
            variables_list = variables_filtered.to_dict('records')
            for idx, var in enumerate(variables_list, 1):
                print(f"  {idx:3d}. {var['MIEMBRO_CAPTION']}")
            
            print(f"\n{Fore.CYAN}Selección múltiple: 1,2,5-10,15 (mixto permitido){Style.RESET_ALL}")
            sel_var = safe_input(f"{Fore.CYAN}>> Números:{Style.RESET_ALL} ").strip()
            
            # Parsear selección de variables
            selected_variables = []
            try:
                if '-' in sel_var:
                    start, end = map(int, sel_var.split('-'))
                    for i in range(start, min(end+1, len(variables_list)+1)):
                        if 1 <= i <= len(variables_list):
                            selected_variables.append(variables_list[i-1])
                else:
                    indices = [int(x.strip()) for x in sel_var.split(',')]
                    for idx in indices:
                        if 1 <= idx <= len(variables_list):
                            selected_variables.append(variables_list[idx-1])
            except:
                print(f"{Fore.RED}[!] Selección inválida{Style.RESET_ALL}")
                return
            
            if not selected_variables:
                print(f"{Fore.RED}[!] Debe seleccionar al menos una variable{Style.RESET_ALL}")
                return
            
            for var in selected_variables:
                print(f"{Fore.GREEN}✓ {var['MIEMBRO_CAPTION']}{Style.RESET_ALL}")
        
        # ========== PASO 4: PIVOT TABLE - DIMENSIONES ==========
        print(f"\n{Fore.YELLOW}╔═══ PASO 4: CONFIGURAR PIVOT TABLE ═══╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Puedes agregar hasta 3 desgloses (ROWS) + filtros ilimitados (WHERE){Style.RESET_ALL}\n")
        
        # Obtener jerarquías disponibles
        # 1. Filtrar dimensiones que NO son variables ni medidas
        mask_vars = df_members['DIMENSION'].str.upper().str.contains('VARIABLE', na=False)
        mask_measures = df_members['DIMENSION'].str.upper().str.contains('MEASURE', na=False)
        mask_dim = df_members['DIMENSION'].str.upper() == 'DIMENSION'
        
        # 2. Obtener dimensiones únicas
        unique_hierarchies = df_members[
            ~mask_vars & ~mask_measures & ~mask_dim
        ][['DIMENSION', 'JERARQUIA']].drop_duplicates()
        
        hierarchy_map = {}  # {dimension|hierarchy: {dimension, hierarchy, levels: [...]}}
        
        # 3. Para cada jerarquía, detectar niveles
        for _, row in unique_hierarchies.iterrows():
            dimension = row['DIMENSION']
            hierarchy = row['JERARQUIA']
            key = f"{dimension}|{hierarchy}"
            
            levels_list = []
            
            # CASO A: Cubo nuevo (con NIVEL_NOMBRE)
            if 'NIVEL_NOMBRE' in df_members.columns:
                # Obtener niveles directamente de la columna
                levels_in_hier = df_members[
                    (df_members['DIMENSION'] == dimension) &
                    (df_members['JERARQUIA'] == hierarchy) &
                    (df_members['NIVEL_NOMBRE'].notna()) &
                    (df_members['NIVEL_NOMBRE'] != 'All') &
                    (df_members['NIVEL_NOMBRE'] != '(All)')
                ]['NIVEL_NOMBRE'].unique()
                
                for level_name in levels_in_hier:
                    levels_list.append({
                        'level_name': level_name,
                        'has_nivel_nombre': True
                    })
            
            # CASO B: Cubo viejo (sin NIVEL_NOMBRE)
            else:
                # Extraer niveles analizando Unique Names
                extracted_levels = self.extract_levels_from_unique_names(df_members, dimension, hierarchy)
                
                if extracted_levels:
                    for level_info in extracted_levels:
                        levels_list.append({
                            'level_name': level_info['level_name'],
                            'level_depth': level_info['level_depth'],
                            'has_nivel_nombre': False
                        })
                else:
                    # Fallback: usar nombre de jerarquía como nivel único
                    level_name = hierarchy.split('.')[-1].replace('[', '').replace(']', '')
                    levels_list.append({
                        'level_name': level_name,
                        'has_nivel_nombre': False
                    })
            
            # Agregar jerarquía al mapa
            if levels_list:
                hierarchy_map[key] = {
                    'dimension': dimension,
                    'hierarchy': hierarchy,
                    'levels': levels_list,
                    'display': f"{dimension} → {hierarchy}"
                }
        
        hierarchy_list = list(hierarchy_map.values())
        
        # Acumuladores
        row_dimensions = []  # Para CROSSJOIN (máx 3)
        where_filters = []   # Para WHERE clause
        
        while True:
            print(f"\n{Fore.CYAN}{'─'*70}")
            print(f"Estado actual:")
            print(f"  • Desgloses (ROWS): {len(row_dimensions)}/3")
            print(f"  • Filtros (WHERE): {len(where_filters)}")
            print(f"{'─'*70}{Style.RESET_ALL}\n")
            
            print("Dimensiones disponibles:")
            for idx, h in enumerate(hierarchy_list[:15], 1):
                print(f"  {idx:2d}. {h['display']}")
            
            print(f"\n{Fore.YELLOW}0. Terminar y generar consulta{Style.RESET_ALL}")
            
            sel = safe_input(f"\n{Fore.CYAN}>> Seleccionar dimensión (0=terminar):{Style.RESET_ALL} ").strip()
            
            if sel == '0':
                break
            
            if not sel.isdigit() or not (1 <= int(sel) <= len(hierarchy_list[:15])):
                continue
            
            selected_hier = hierarchy_list[int(sel)-1]
            
            # Si la jerarquía tiene múltiples niveles, preguntar cuál usar
            selected_level = None
            if len(selected_hier['levels']) > 1:
                print(f"\n{Fore.CYAN}╔═══ Niveles en {selected_hier['hierarchy']} ═══╗{Style.RESET_ALL}")
                for idx, level_info in enumerate(selected_hier['levels'], 1):
                    print(f"  {idx}. {level_info['level_name']}")
                
                level_sel = safe_input(f"\n{Fore.CYAN}>> Seleccionar nivel (1-{len(selected_hier['levels'])}):{Style.RESET_ALL} ").strip()
                
                if not level_sel.isdigit() or not (1 <= int(level_sel) <= len(selected_hier['levels'])):
                    print(f"{Fore.RED}[!] Selección inválida{Style.RESET_ALL}")
                    continue
                
                selected_level = selected_hier['levels'][int(level_sel)-1]
            else:
                # Jerarquía con un solo nivel
                selected_level = selected_hier['levels'][0]
            
            # Preguntar: ¿Desglose o Filtro?
            print(f"\n{Fore.YELLOW}Selección: {selected_hier['display']} → {selected_level['level_name']}{Style.RESET_ALL}")
            print(f"1. DESGLOSE (mostrar en filas - ver todos los valores)")
            print(f"2. FILTRO (limitar a valores específicos)")
            
            tipo = safe_input(f"\n{Fore.CYAN}>> Tipo (1/2):{Style.RESET_ALL} ").strip()
            
            if tipo == '1':
                # DESGLOSE
                if len(row_dimensions) >= 3:
                    self._show_validation_warning(
                        "Maximum 3 row dimensions reached",
                        "Use filters (WHERE clause) instead"
                    )
                    continue
                
                # VALIDACIÓN: No permitir la misma jerarquía dos veces
                hierarchy_path = f"{selected_hier['dimension']}.{selected_hier['hierarchy']}"
                already_used = any(
                    f"{d.get('dimension', '')}.{d.get('hierarchy', '')}" == hierarchy_path 
                    for d in row_dimensions
                )
                
                if already_used:
                    self._show_validation_warning(
                        f"Hierarchy '{selected_hier['hierarchy']}' already in use",
                        "MDX does not allow the same hierarchy twice in CROSSJOIN. Use a FILTER instead."
                    )
                    continue
                
                # Construcción robusta del path MDX
                dim_name = selected_hier['dimension']
                hier_name = selected_hier['hierarchy']
                level_name = selected_level['level_name']
                
                # Asegurar brackets si no los tiene
                if not dim_name.startswith('['): dim_name = f"[{dim_name}]"
                if not hier_name.startswith('['): hier_name = f"[{hier_name}]"
                
                # Construcción del MDX path y DIMENSION PROPERTIES
                mdx_path = ""
                dim_properties = []
                
                # Si el nivel es inferido (no existe NIVEL_NOMBRE), usar estrategia especial
                if selected_level.get('has_nivel_nombre', False):
                    # Cubo nuevo: usar nivel explícito
                    if not level_name.startswith('['): level_name = f"[{level_name}]"
                    mdx_path = f"{dim_name}.{hier_name}.{level_name}.MEMBERS"
                else:
                    # Cubo viejo: detectar si hay múltiples niveles
                    all_levels_info = selected_hier.get('levels', [])
                    
                    if len(all_levels_info) > 1:
                        # Jerarquía multinivel
                        is_generic_name = selected_level['level_name'].startswith("Nivel ")
                        
                        if is_generic_name:
                            # Usar sintaxis .Levels(depth)
                            # depth es 1-based en mi lógica, pero en MDX Levels(0) es All.
                            # Levels(1) es el primer nivel.
                            depth = selected_level.get('level_depth', 1)
                            mdx_path = f"{hier_name}.Levels({depth}).MEMBERS"
                        else:
                            # Usar nombre explícito
                            if not level_name.startswith('['): level_name = f"[{level_name}]"
                            mdx_path = f"{hier_name}.{level_name}.MEMBERS"
                        
                        # Agregar niveles superiores como DIMENSION PROPERTIES
                        # Solo si tienen nombres explícitos (no genéricos)
                        try:
                            # Encontrar índice actual
                            current_idx = -1
                            for i, l in enumerate(all_levels_info):
                                if l['level_name'] == selected_level['level_name']:
                                    current_idx = i
                                    break
                            
                            if current_idx > 0:
                                parent_levels = all_levels_info[:current_idx]
                                for parent in parent_levels:
                                    p_name = parent['level_name']
                                    if not p_name.startswith("Nivel "):
                                        dim_properties.append(f"{hier_name}.[{p_name}]")
                        except Exception:
                            pass
                    else:
                        # Jerarquía simple: usar solo la jerarquía
                        mdx_path = f"{hier_name}.MEMBERS"
                
                row_dimensions.append({
                    'display': f"{selected_hier['display']} → {selected_level['level_name']}",
                    'mdx': mdx_path,
                    'dimension': selected_hier['dimension'],
                    'hierarchy': selected_hier['hierarchy'],
                    'level': selected_level['level_name'],
                    'dim_properties': dim_properties  # Guardar para usarlo después
                })
                print(f"{Fore.GREEN}[OK] Desglose agregado{Style.RESET_ALL}")
                
                # Show estimated cardinality
                self._estimate_and_warn_cardinality(row_dimensions, catalog)
                
            elif tipo == '2':
                # FILTRO - Mostrar miembros
                print(f"\n{Fore.CYAN}Cargando miembros...{Style.RESET_ALL}")
                members = self.get_dimension_members(
                    df_members,
                    selected_hier['dimension'],
                    selected_hier['hierarchy'],
                    selected_level['level_name']
                )
                
                if not members:
                    print(f"{Fore.RED}[!] No hay miembros disponibles{Style.RESET_ALL}")
                    continue
                
                print(f"\n{Fore.YELLOW}Miembros disponibles ({len(members)}):{Style.RESET_ALL}")
                for idx, mem in enumerate(members, 1):
                    print(f"  {idx:3d}. {mem['MIEMBRO_CAPTION']}")
                
                print(f"\n{Fore.CYAN}Selección múltiple: 1,3,5-10,15 (mixto permitido){Style.RESET_ALL}")
                sel_members = safe_input(f"{Fore.CYAN}>> Números:{Style.RESET_ALL} ").strip()
                
                # Parsear selección
                selected_members = []
                try:
                    if '-' in sel_members:
                        # Rango: 1-10
                        start, end = map(int, sel_members.split('-'))
                        for i in range(start, min(end+1, len(members)+1)):
                            if 1 <= i <= len(members):
                                selected_members.append(members[i-1])
                    else:
                        # Lista: 1,3,5
                        indices = [int(x.strip()) for x in sel_members.split(',')]
                        for idx in indices:
                            if 1 <= idx <= len(members):
                                selected_members.append(members[idx-1])
                except:
                    print(f"{Fore.RED}[!] Selección inválida{Style.RESET_ALL}")
                    continue
                
                if selected_members:
                    # Construir SET de miembros
                    member_set = ", ".join([m['MIEMBRO_UNIQUE_NAME'] for m in selected_members])
                    where_filters.append({
                        'display': f"{selected_hier['display']}: {', '.join([m['MIEMBRO_CAPTION'][:20] for m in selected_members[:3]])}{'...' if len(selected_members) > 3 else ''}",
                        'mdx': f"{{{member_set}}}"
                    })
                    print(f"{Fore.GREEN}✓ Filtro agregado ({len(selected_members)} valores){Style.RESET_ALL}")
        
        # ========== GENERAR MDX ==========
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
        
        # COLUMNS clause (Medidas)
        if len(selected_measures) == 1:
            columns_clause = f"{{ {selected_measures[0]['MEASURE_UNIQUE_NAME']} }}"
        else:
            measures_set = ", ".join([m['MEASURE_UNIQUE_NAME'] for m in selected_measures])
            columns_clause = f"{{ {measures_set} }}"
        
        # ROWS clause (Variables + Dimensiones)
        if len(selected_variables) == 1:
            variables_set = f"{{ {selected_variables[0]['MIEMBRO_UNIQUE_NAME']} }}"
        else:
            vars_unique = ", ".join([v['MIEMBRO_UNIQUE_NAME'] for v in selected_variables])
            variables_set = f"{{ {vars_unique} }}"
        
        if row_dimensions:
            rows_clause = variables_set
            for dim in row_dimensions:
                rows_clause = f"CROSSJOIN({dim['mdx']}, {rows_clause})"
        else:
            rows_clause = variables_set
        
        # Construir DIMENSION PROPERTIES clause si hay propiedades
        dim_props_clause = ""
        all_dim_props = []
        for dim in row_dimensions:
            if dim.get('dim_properties'):
                all_dim_props.extend(dim['dim_properties'])
        
        if all_dim_props:
            # Formato: DIMENSION PROPERTIES [Hier].[Level1], [Hier].[Level2]
            dim_props_clause = f"\n    DIMENSION PROPERTIES {', '.join(all_dim_props)}"
        
        # Incorporar filtros (where_filters) mediante CROSSJOIN en ROWS
        if where_filters:
            for wf in where_filters:
                rows_clause = f"CROSSJOIN({wf['mdx']}, {rows_clause})"
        
        # No WHERE clause necesario
        where_clause = ""
        mdx = f"""SELECT 
    {columns_clause} ON COLUMNS,
    NON EMPTY {rows_clause} ON ROWS{dim_props_clause}
FROM {cube_name}{where_clause}"""
        
        # Show preview with rich
        self._show_mdx_preview(mdx, "GENERATED MDX QUERY")
        
        # Show selection summary
        self._show_selection_summary({
            "Measures": [m['MEASURE_NAME'] for m in selected_measures],
            "Variables": [v['MIEMBRO_CAPTION'] for v in selected_variables],
            "Row Dimensions": [d['display'] for d in row_dimensions],
            "Filters": [f"{f['display'][:40]}" for f in where_filters]
        })
        
        # EJECUTAR
        if safe_input(f"\n{Fore.CYAN}>> ¿Ejecutar consulta? (s/n):{Style.RESET_ALL} ").lower() == 's':
            df = self.execute_mdx(catalog, mdx)
            
            if not df.empty:
                print(f"\n{Fore.GREEN}{'═'*70}")
                print(f"[RESULTADOS: {len(df)} FILAS]")
                print(f"{'═'*70}{Style.RESET_ALL}")
                print(df.head(20))
                if len(df) > 20:
                    print(f"\n{Fore.CYAN}... Mostrando 20 de {len(df)} filas totales{Style.RESET_ALL}")
                
                # Prompt de exportación más claro
                if safe_input(f"\n{Fore.CYAN}>> ¿Exportar datos (CSV/Excel)? (s/n):{Style.RESET_ALL} ").lower() == 's':
                    # Nombre con múltiples apartados/variables
                    apartsample = selected_apartados[0]['MIEMBRO_CAPTION'][:15] if selected_apartados else "DATA"
                    var_sample = selected_variables[0]['MIEMBRO_CAPTION'][:15] if selected_variables else "QUERY"
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    name = f"PIVOT_{len(selected_measures)}M_{len(selected_variables)}V_{timestamp}"
                    name = "".join([c if c.isalnum() or c == '_' else "_" for c in name])
                    self.export_data(df, name)
            else:
                print(f"\n{Fore.YELLOW}[!] La consulta no devolvió resultados o ocurrió un error.{Style.RESET_ALL}")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def estimate_export_time(rows: int) -> int:
    """Estima tiempo de exportación en minutos para Excel"""
    # Aproximadamente 3 minutos por cada 500k filas
    return max(1, int((rows / 500000) * 3))

# ============================================================================
# MENÚ INTERACTIVO
# ============================================================================

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    clear_screen()
    print(f"{Fore.CYAN}" + "="*70)
    print(f"[DGIS OLAP FULL DISCOVERY SCANNER v4.1]")
    print("="*70 + f"{Style.RESET_ALL}")

def safe_input(prompt: str) -> str:
    """Input seguro sin buffering"""
    print(prompt, end='', flush=True)
    return sys.stdin.readline().strip()

def menu_principal(config: Config):
    while True:
        print_header()
        print(f"\n{Fore.YELLOW}[OPCIONES PRINCIPALES]{Style.RESET_ALL}\n")
        print("1. [SCAN] Escaneo COMPLETO del servidor")
        print("2. [LIST] Listar catalogos disponibles")
        print("3. [CACHE] Descargar miembros de catalogo (opcional)")
        print("4. [DATA] Extraer Datos (MDX) - Consultas Numericas Mejoradas")
        print("5. [CONF] Ver configuracion actual")
        print("0. [EXIT] Salir")
        
        print(f"\n{Fore.CYAN}" + "="*70 + f"{Style.RESET_ALL}")
        opcion = safe_input(">> Selecciona una opcion: ")
        
        if opcion == '0':
            print(f"\n{Fore.GREEN}[SALIR] Hasta luego{Style.RESET_ALL}")
            break
        
        elif opcion == '1':
            print(f"\n{Fore.CYAN}[INICIO] ESCANEO COMPLETO...{Style.RESET_ALL}")
            if safe_input("\nContinuar? (s/n): ").lower() == 's':
                discovery = ServerDiscovery(config)
                results = discovery.full_discovery()
                discovery.export_results(results)
                safe_input("\nPresiona Enter para continuar...")
        
        elif opcion == '2':
            print(f"\n{Fore.CYAN}[BUSCANDO] Catalogos...{Style.RESET_ALL}")
            try:
                discovery = ServerDiscovery(config)
                discovery.discover_generic('Catalogos', "SELECT * FROM $system.DBSCHEMA_CATALOGS", 'catalogs')
                catalogs = discovery.discovery_results.get('catalogs', [])
                
                if catalogs:
                    print(f"\n[OK] Encontrados {len(catalogs)} catalogos:\n")
                    for idx, cat in enumerate(catalogs, 1):
                        print(f"{idx:3d}. {Fore.GREEN}{cat.get('CATALOG_NAME', 'N/A')}{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.RED}[ERROR] No se encontraron catalogos{Style.RESET_ALL}")
            except Exception as e:
                print(f"Error: {e}")
            safe_input("\nPresiona Enter para continuar...")
            
        elif opcion == '3':
            print(f"\n{Fore.CYAN}[DESCARGA] Miembros de Catálogo (Cache){Style.RESET_ALL}")
            try:
                discovery = ServerDiscovery(config)
                discovery.discover_generic('Catalogos', "SELECT * FROM $system.DBSCHEMA_CATALOGS", 'catalogs')
                catalogs = discovery.discovery_results.get('catalogs', [])
                
                if not catalogs:
                    print(f"{Fore.RED}[ERROR] No se encontraron catalogos{Style.RESET_ALL}")
                    safe_input("\nPresiona Enter para continuar...")
                    continue
                
                # Mostrar lista
                print(f"\n[SELECCION] Elige un catalogo para descargar miembros:\n")
                for idx, cat in enumerate(catalogs, 1):
                    cat_name = cat.get('CATALOG_NAME', 'N/A')
                    # Verificar si ya existe en cache
                    csv_path = Path(config.output_dir).parent / f"{cat_name}_miembros_completos.csv"
                    status = f"{Fore.GREEN}[CACHE]{Style.RESET_ALL}" if csv_path.exists() else ""
                    print(f"{idx:3d}. {cat_name} {status}")
                
                num = safe_input(f"\n{Fore.CYAN}>> Numero de catalogo (0=cancelar):{Style.RESET_ALL} ")
                
                if not num.isdigit() or int(num) == 0:
                    continue
                    
                idx_sel = int(num) - 1
                if idx_sel < 0 or idx_sel >= len(catalogs):
                    print(f"{Fore.RED}[ERROR] Numero invalido{Style.RESET_ALL}")
                    safe_input("\nPresiona Enter para continuar...")
                    continue
                
                catalog_name = catalogs[idx_sel]['CATALOG_NAME']
                
                print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}[DESCARGANDO] Miembros de: {catalog_name}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}\n")
                
                # Usar el método rápido de solo miembros
                explorer = CatalogExplorer(config)
                success = explorer.download_members_only(catalog_name)
                
                if success:
                    print(f"\n{Fore.GREEN}✓ Miembros descargados exitosamente{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}  Archivo: {catalog_name}_miembros_completos.csv{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}  Ahora puedes usar Opción 4 (DATA) con este catálogo{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.RED}[ERROR] No se pudieron descargar los miembros{Style.RESET_ALL}")
                
            except Exception as e:
                print(f"Error: {e}")
            
            safe_input("\nPresiona Enter para continuar...")

        elif opcion == '4':
            print(f"\n{Fore.CYAN}[DATA] EXTRACCION DE DATOS (MDX){Style.RESET_ALL}")
            # 1. Seleccionar Catalogo
            try:
                discovery = ServerDiscovery(config)
                discovery.discover_generic('Catalogos', "SELECT * FROM $system.DBSCHEMA_CATALOGS", 'catalogs')
                catalogs = discovery.discovery_results.get('catalogs', [])
                
                if not catalogs:
                    print(f"\n{Fore.RED}[ERROR] No se encontraron catalogos{Style.RESET_ALL}")
                    safe_input("\nPresiona Enter para continuar...")
                    continue
                
                print(f"\n[SELECCION] Elige un catalogo para consultar:\n")
                catalog_names = []
                for idx, cat in enumerate(catalogs, 1):
                    cat_name = cat.get('CATALOG_NAME', 'N/A')
                    catalog_names.append(cat_name)
                    print(f"{idx:3d}. {Fore.GREEN}{cat_name}{Style.RESET_ALL}")
                
                sel = safe_input("\n>> Numero de catalogo: ")
                selected_catalog = None
                if sel.isdigit():
                    idx = int(sel) - 1
                    if 0 <= idx < len(catalog_names):
                        selected_catalog = catalog_names[idx]
                
                if selected_catalog:
                    tool = MDXQueryTool(config)
                    print(f"\n{Fore.CYAN}══════════════════════════════════════════════════════════{Style.RESET_ALL}")
                    tool.interactive_hierarchical_builder(selected_catalog)
                else:
                    print(f"\n{Fore.YELLOW}[!] Seleccion invalida{Style.RESET_ALL}")

            except Exception as e:
                print(f"Error: {e}")
            safe_input("\nPresiona Enter para continuar...")

        elif opcion == '5':
            print(f"\n{Fore.CYAN}[CONFIG] CONFIGURACION ACTUAL{Style.RESET_ALL}")
            print(f"Server:   {config.server}")
            print(f"User:     {config.user}")
            print(f"Workers:  {config.max_workers}")
            print(f"Output:   {config.output_dir}")
            safe_input("\nPresiona Enter para continuar...")

        

def main():
    config = Config()
    logger = setup_logging(config)
    logger.info("Sistema iniciado v4.1")
    try:
        menu_principal(config)
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}[!] Operacion interrumpida{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}[FATAL] Error: {e}{Style.RESET_ALL}")
        sys.exit(1)

if __name__ == "__main__":
    main()