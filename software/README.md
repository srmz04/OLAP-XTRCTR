# SOFTWARE Requirements

This directory documents the required software for running `DGIS_SCAN_2_stable.py`.

## Required Software

### 1. Python 3.8+
- **Download**: https://www.python.org/downloads/
- **Note**: Must be Windows version (COM support required)

### 2. SQL Server Analysis Services OLEDB Provider
- **Package**: `x64_17.0.9001.0_SQL_AS_OLEDB.msi` (or latest version)
- **Download**: https://docs.microsoft.com/en-us/analysis-services/client-libraries
- **Install command** (silent):
  ```powershell
  msiexec /i x64_17.0.9001.0_SQL_AS_OLEDB.msi /quiet /norestart
  ```

## GitHub Actions Auto-Install

The CI workflow automatically installs these dependencies. See `.github/workflows/olap_scan.yml`.

## Manual Installation (Windows)

```powershell
# 1. Install Python dependencies
pip install -r scanner/requirements.txt

# 2. Install OLEDB Provider (requires admin)
msiexec /i SOFTWARE\x64_17.0.9001.0_SQL_AS_OLEDB.msi /quiet /norestart
```
