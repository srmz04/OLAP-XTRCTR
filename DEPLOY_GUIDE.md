# 🚀 Guía Paso a Paso: Desplegar OLAP XTRCTR en GitHub

---

## PASO 1: Instalar GitHub CLI (si no lo tienes)

### 1.1 Verificar si ya tienes `gh`
```bash
gh --version
```

**Si aparece un número de versión** → Salta al PASO 2

**Si dice "command not found"** → Continúa con 1.2

### 1.2 Instalar GitHub CLI en Linux
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install gh -y

# Verificar instalación
gh --version
```

### 1.3 Autenticarte con GitHub
```bash
gh auth login
```

**Respuestas a las preguntas:**
1. `? What account do you want to log into?` → **GitHub.com**
2. `? What is your preferred protocol for Git operations?` → **HTTPS**
3. `? Authenticate Git with your GitHub credentials?` → **Yes**
4. `? How would you like to authenticate GitHub CLI?` → **Login with a web browser**
5. Se abrirá tu navegador → **Ingresa el código que aparece en terminal**
6. Autoriza la aplicación en el navegador

**Verificar que funcionó:**
```bash
gh auth status
```
Debe mostrar: `✓ Logged in to github.com as TU_USUARIO`

---

## PASO 2: Crear el Repositorio

### 2.1 Navegar a la carpeta OLAP XTRCTR
```bash
cd "/home/uy/Dropbox/srmz04/OLAP XTRCTR"
```

### 2.2 Verificar que estás en el lugar correcto
```bash
ls -la
```
**Debe mostrar:** README.md, scanner/, backend/, frontend/, etc.

### 2.3 Inicializar Git
```bash
git init
```
**Salida esperada:** `Initialized empty Git repository in .../OLAP XTRCTR/.git/`

### 2.4 Agregar todos los archivos
```bash
git add .
```
(Este comando no muestra salida si funciona bien)

### 2.5 Verificar qué se va a commitear
```bash
git status
```
**Debe mostrar:** Lista de archivos en verde (new file: ...)

### 2.6 Hacer el primer commit
```bash
git commit -m "Initial: OLAP XTRCTR with scanner + GUI"
```
**Salida:** `[master (root-commit) abc123] Initial: OLAP XTRCTR...`

### 2.7 Crear el repo en GitHub y subir
```bash
gh repo create OLAP-XTRCTR --public --source=. --push
```

**Respuestas a las preguntas (si aparecen):**
- `? Create a new repository on GitHub?` → **Yes**
- `? Repository name?` → **OLAP-XTRCTR** (Enter para aceptar)

**Salida exitosa:**
```
✓ Created repository TU_USUARIO/OLAP-XTRCTR on GitHub
✓ Added remote https://github.com/TU_USUARIO/OLAP-XTRCTR.git
✓ Pushed commits to https://github.com/TU_USUARIO/OLAP-XTRCTR.git
```

### 2.8 Verificar que se creó
```bash
gh repo view --web
```
**Esto abrirá tu navegador mostrando el repositorio.**

---

## PASO 3: Configurar GitHub Secrets

### 3.1 Abrir la página de Secrets
**Opción A - Desde terminal:**
```bash
gh secret list
```
(Esto mostrará secrets existentes, probablemente vacío)

**Opción B - Desde el navegador:**
1. Ve a: `https://github.com/TU_USUARIO/OLAP-XTRCTR`
2. Click en **Settings** (pestaña arriba, junto a Insights)
3. En el menú izquierdo, busca **Security** → **Secrets and variables** → **Actions**
4. Click en **New repository secret**

### 3.2 Agregar Secret: DGIS_SERVER

**Desde terminal:**
```bash
gh secret set DGIS_SERVER
```
Cuando pida el valor, escribe:
```
reportesdgis.salud.gob.mx
```
Presiona Enter

**O desde navegador:**
- Name: `DGIS_SERVER`
- Secret: `reportesdgis.salud.gob.mx`
- Click **Add secret**

### 3.3 Agregar Secret: DGIS_USER

**Desde terminal:**
```bash
gh secret set DGIS_USER
```
Cuando pida el valor, escribe:
```
PWIDGISREPORTES\DGIS15
```
⚠️ **IMPORTANTE**: Solo UNA barra invertida `\`, NO dos

**O desde navegador:**
- Name: `DGIS_USER`
- Secret: `PWIDGISREPORTES\DGIS15`
- Click **Add secret**

### 3.4 Agregar Secret: DGIS_PASSWORD

**Desde terminal:**
```bash
gh secret set DGIS_PASSWORD
```
Cuando pida el valor, escribe tu contraseña real (la que usas actualmente):
```
TU_CONTRASEÑA_REAL_AQUI
```

**O desde navegador:**
- Name: `DGIS_PASSWORD`
- Secret: `TU_CONTRASEÑA_REAL`
- Click **Add secret**

### 3.5 Verificar que se crearon los 3 secrets
```bash
gh secret list
```

**Salida esperada:**
```
DGIS_PASSWORD  Updated 2025-12-10
DGIS_SERVER    Updated 2025-12-10
DGIS_USER      Updated 2025-12-10
```

---

## PASO 4: Ejecutar el Workflow

### 4.1 Ir a la pestaña Actions

**Opción A - Desde terminal:**
```bash
gh workflow list
```
Debe mostrar: `OLAP Scanner  active  12345678`

**Opción B - Desde navegador:**
1. Ve a: `https://github.com/TU_USUARIO/OLAP-XTRCTR`
2. Click en pestaña **Actions** (arriba, junto a Pull requests)

### 4.2 Ejecutar el workflow manualmente

**Desde terminal:**
```bash
gh workflow run olap_scan.yml -f mode=discover
```

**O desde navegador:**
1. En la lista de workflows, click en **OLAP Scanner**
2. Verás un banner azul: "This workflow has a workflow_dispatch event trigger"
3. Click en botón **Run workflow** (lado derecho)
4. Aparece un dropdown:
   - **Branch**: main
   - **Catalog to scan**: dejar vacío (o escribir `sis2011`)
   - **Scan mode**: `discover`
5. Click en botón verde **Run workflow**

### 4.3 Ver el progreso

**Desde terminal:**
```bash
gh run list --limit 1
```
Mostrará el estado: `in_progress`, `completed`, o `failure`

**Ver logs en vivo:**
```bash
gh run watch
```

**Desde navegador:**
1. Después de dar click en Run workflow, recarga la página (F5)
2. Aparecerá una nueva ejecución en la lista
3. Click en ella para ver los logs

### 4.4 Revisar resultados

**Si fue exitoso:**
1. En la página del workflow run, busca sección **Artifacts**
2. Descarga `olap-scan-results`
3. Contendrá los archivos Excel/CSV generados

**Si falló:**
1. Click en el job que falló (ej: `scan`)
2. Revisa los logs rojos para ver el error
3. Errores comunes:
   - "Cannot connect" → Firewall bloqueando, o credenciales incorrectas
   - "Secret not found" → Revisa que los 3 secrets estén configurados

---

## 📋 Resumen de Comandos (Quick Reference)

```bash
# 1. Ir a la carpeta
cd "/home/uy/Dropbox/srmz04/OLAP XTRCTR"

# 2. Inicializar y subir
git init
git add .
git commit -m "Initial: OLAP XTRCTR with scanner + GUI"
gh repo create OLAP-XTRCTR --public --source=. --push

# 3. Configurar secrets
gh secret set DGIS_SERVER     # → reportesdgis.salud.gob.mx
gh secret set DGIS_USER       # → PWIDGISREPORTES\DGIS15
gh secret set DGIS_PASSWORD   # → TU_CONTRASEÑA

# 4. Verificar secrets
gh secret list

# 5. Ejecutar workflow
gh workflow run olap_scan.yml -f mode=discover

# 6. Ver progreso
gh run watch
```

---

## ❓ Troubleshooting

| Error | Solución |
|-------|----------|
| `gh: command not found` | Instalar: `sudo apt install gh` |
| `not logged in` | Ejecutar: `gh auth login` |
| `repository already exists` | El repo ya existe, usar otro nombre o eliminarlo primero |
| `Permission denied (publickey)` | Usar HTTPS en vez de SSH: `gh auth login` y elegir HTTPS |
| Workflow falla en "Run OLAP Scanner" | Revisar que los 3 secrets estén bien configurados |
