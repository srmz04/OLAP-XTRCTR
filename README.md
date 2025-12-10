# OLAP XTRCTR

🔍 **DGIS OLAP Metadata Extractor** - Herramienta para descubrir y extraer metadatos de cubos OLAP (SQL Server Analysis Services)

## 🚀 Quick Start

### Opción 1: GitHub Actions (Recomendado)

1. **Configurar Secrets** en GitHub → Settings → Secrets:
   - `DGIS_SERVER`: `reportesdgis.salud.gob.mx`
   - `DGIS_USER`: `PWIDGISREPORTES\DGIS15`
   - `DGIS_PASSWORD`: Tu contraseña

2. **Ejecutar** desde Actions → OLAP Scanner → Run workflow

3. **Descargar** resultados desde Artifacts

### Opción 2: Local (Windows)

```powershell
# 1. Clonar
git clone https://github.com/usuario/OLAP-XTRCTR.git
cd OLAP-XTRCTR

# 2. Configurar
copy .env.example .env
notepad .env  # Editar credenciales

# 3. Instalar OLEDB Provider (admin requerido)
msiexec /i software\SQL_AS_OLEDB.msi /quiet

# 4. Instalar dependencias Python
pip install -r scanner/requirements.txt

# 5. Ejecutar
cd scanner
python DGIS_SCAN_2_stable.py
```

---

## 📁 Estructura

```
OLAP XTRCTR/
├── .github/workflows/      # CI/CD
│   └── olap_scan.yml       # GitHub Actions workflow
├── scanner/                # Core scanner
│   ├── DGIS_SCAN_2_stable.py
│   ├── validators.py
│   └── requirements.txt
├── software/               # Drivers documentation
├── backend/                # FastAPI (Phase 2)
├── frontend/               # React UI (Phase 2)
├── .env.example
└── .gitignore
```

---

## 🔧 Modos de Ejecución

| Modo | Descripción |
|------|-------------|
| `discover` | Escanea rowsets y catálogos disponibles |
| `explore` | Extrae metadatos completos de un catálogo |
| `data` | Constructor interactivo de consultas MDX |

---

## 🛠️ Requisitos

- **OS**: Windows (COM/DCOM requerido)
- **Python**: 3.8+
- **Driver**: SQL Server Analysis Services OLEDB Provider
- **Red**: Acceso a `reportesdgis.salud.gob.mx:2383`

---

## 📝 GitHub Secrets Necesarios

| Secret | Descripción |
|--------|-------------|
| `DGIS_SERVER` | Hostname del servidor OLAP |
| `DGIS_USER` | Usuario (formato `DOMAIN\\user`) |
| `DGIS_PASSWORD` | Contraseña |

---

## 🚧 Roadmap

- [x] **Phase 1**: Scanner + GitHub Actions
- [ ] **Phase 2**: Backend API (FastAPI)
- [ ] **Phase 2**: Frontend GUI (React + Drag & Drop)
- [ ] **Phase 2**: Docker Compose

---

## 📄 Licencia

Uso interno DGIS.
