# OLAP XTRCTR

Aplicación de escritorio para explorar servidores SQL Server Analysis Services, construir consultas MDX y exportar resultados sin escribir cada consulta desde cero.

## Qué hace

- Comprueba los componentes necesarios para conectarse mediante MSOLAP.
- Guarda perfiles sin incluir contraseñas en el archivo de configuración.
- Explora catálogos, dimensiones, jerarquías, niveles y medidas.
- Construye consultas MDX desde una interfaz visual.
- Conserva un catálogo local y un historial de consultas.
- Funciona con datos sintéticos en Linux y macOS para desarrollo y demostración.

## Privacidad y configuración

El repositorio no contiene servidores, usuarios, contraseñas ni metadatos operativos. En Windows puede introducir una conexión desde la interfaz o cargar un archivo privado externo mediante `OLAP_XTRCTR_ENV_FILE`:

```dotenv
OLAP_SERVER=olap.example.test
OLAP_USER=usuario
OLAP_PASSWORD=contraseña
OLAP_CATALOG=DEMO_CUBE
```

```powershell
$env:OLAP_XTRCTR_ENV_FILE = "C:\ruta\privada\olap.env"
python xtractor_ui\__main__.py
```

El archivo privado debe permanecer fuera del clon. Las contraseñas guardadas desde la interfaz usan el almacén de credenciales del sistema; si no está disponible, la aplicación usa un archivo local cifrado.

## Instalación

```bash
git clone https://github.com/srmz04/OLAP-XTRCTR.git
cd OLAP-XTRCTR
python -m venv .venv
```

En Linux o macOS:

```bash
.venv/bin/pip install -e "./xtractor_ui[dev]"
cd xtractor_ui
../.venv/bin/python __main__.py
```

En Windows se requieren además el proveedor OLE DB de Analysis Services, `pywin32` y `adodbapi`.

## Arquitectura

```text
xtractor_ui/ui/       pantallas y navegación PyQt
xtractor_ui/core/     proveedores, caché y credenciales
backend/              adaptador MSOLAP y datos sintéticos
xtractor_ui/tests/    pruebas de caché, perfiles y constructor
```

## Verificación

```bash
cd xtractor_ui
pytest
```

La configuración de demostración solo genera consultas y resultados ficticios. Cada organización debe autorizar y proteger sus propios accesos al servidor OLAP.
