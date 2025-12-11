
import os
import sys
import json
import logging
import pandas as pd
import traceback
from pathlib import Path

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Asegurar que podemos importar DGIS_SCAN_2
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from DGIS_SCAN_2 import Config, ConnectionManager, MDXQueryTool, rows_to_df
    import adodbapi
except ImportError as e:
    logger.error(f"Faltan dependencias críticas: {e}")
    sys.exit(1)

def run_test_connection(config: Config):
    """Prueba básica de conectividad"""
    logger.info(f"Probando conexión a {config.server}...")
    try:
        with ConnectionManager(config) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM $system.DBSCHEMA_CATALOGS")
            rows = cursor.fetchall()
            df = rows_to_df(cursor, rows)
            
            logger.info(f"✅ Conexión exitosa. Encontrados {len(df)} catálogos.")
            
            # Guardar resultado
            output = Path("results_catalogs.csv")
            df.to_csv(output, index=False)
            logger.info(f"Guardado en {output}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Falló la conexión: {e}")
        traceback.print_exc()
        return False

def run_scan_with_metadata(config: Config, catalog: str):
    """
    Simula la 'Opción 4': Usa metadatos conocidos para hacer una consulta de muestra.
    Usa backend/mock_data.csv (la copia de SIS_2025...) como referencia si existe,
    o descarga fresca.
    """
    logger.info(f"Ejecutando escaneo inteligente en {catalog}...")
    
    # 1. Verificar metadata local (el CSV que el usuario mencionó)
    metadata_file = Path("backend/mock_data.csv")
    if not metadata_file.exists():
        metadata_file = Path("SIS_2025_miembros_completos.csv")
    
    if metadata_file.exists():
        logger.info(f"📂 Usando metadata de referencia: {metadata_file}")
        try:
            meta_df = pd.read_csv(metadata_file)
            logger.info(f"   Cargados {len(meta_df)} registros de metadata.")
            
            # Analizar dimensiones disponibles
            if 'DIMENSION' in meta_df.columns:
                dims = meta_df['DIMENSION'].unique()
                logger.info(f"   Dimensiones conocidas: {dims[:5]}...")
        except Exception as e:
            logger.warning(f"   No se pudo leer metadata local: {e}")
    else:
        logger.warning("⚠️ No se encontró mock_data.csv ni SIS_2025...csv. Se procederá sin guía local.")

    # 2. Ejecutar consulta real
    tool = MDXQueryTool(config)
    
    # Consulta de prueba: Total por alguna dimensión común (ej. Entidad o Año)
    # Intentamos adivinar una consulta segura basada en dimensiones estándar
    queries = [
        # Query 1: Metadata básica (Miembros) - Rápido y seguro
        (f"SELECT * FROM [{catalog}].$system.MDSCHEMA_MEMBERS", "members_dump"),
        
        # Query 2: Una medida simple (si supiéramos el nombre)
        # "SELECT {[Measures].AllMembers} ON COLUMNS FROM [{catalog}]" 
    ]
    
    success_count = 0
    
    for mdx, label in queries:
        logger.info(f"Ejecutando MDX [{label}]: {mdx[:100]}...")
        try:
            # Limitamos a 1000 filas para no saturar el runner
            with ConnectionManager(config, catalog) as conn:
                cursor = conn.cursor()
                cursor.execute(mdx)
                
                # Fetch parcial
                rows = cursor.fetchmany(1000)
                df = rows_to_df(cursor, rows)
                
                if not df.empty:
                    filename = f"results_{label}.csv"
                    df.to_csv(filename, index=False)
                    logger.info(f"✅ {label}: {len(df)} filas guardadas en {filename}")
                    success_count += 1
                else:
                    logger.warning(f"⚠️ {label}: Sin resultados")
                    
        except Exception as e:
            logger.error(f"❌ Error en {label}: {e}")
            
    return success_count > 0

def main():
    # Obtener credenciales de ENV
    server = os.environ.get('DGIS_SERVER')
    user = os.environ.get('DGIS_USER')
    password = os.environ.get('DGIS_PASSWORD')
    
    if not all([server, user, password]):
        logger.error("❌ Faltan variables de entorno (DGIS_SERVER/USER/PASSWORD)")
        sys.exit(1)
        
    config = Config(
        server=server,
        user=user,
        password=password,
        connection_timeout=60
    )
    
    # Argumentos simples
    mode = sys.argv[1] if len(sys.argv) > 1 else "test"
    catalog = sys.argv[2] if len(sys.argv) > 2 else "SIS_2025"
    
    logger.info(f"🚀 Iniciando Action Runner. Modo: {mode}, Catalogo: {catalog}")
    
    success = False
    if mode == "test":
        success = run_test_connection(config)
    elif mode == "scan":
        success = run_scan_with_metadata(config, catalog)
    else:
        logger.error(f"Modo desconocido: {mode}")
        
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
