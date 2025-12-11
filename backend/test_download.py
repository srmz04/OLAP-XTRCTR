import sys
import os
import logging
from DGIS_SCAN_2 import Config, CatalogExplorer

# Configurar logging básico
logging.basicConfig(level=logging.INFO)

# Configuración dummy
config = Config(
    output_dir="output",
    connection_string="Provider=MSOLAP;Data Source=192.168.1.5;Catalog=SIS_2025;",
    log_level="INFO",
    log_file="test_download.log"
)

print("Iniciando descarga de prueba para SIS_2025...")
explorer = CatalogExplorer(config)
success = explorer.download_members_only("SIS_2025")

if success:
    print("Descarga exitosa")
else:
    print("Fallo la descarga")
