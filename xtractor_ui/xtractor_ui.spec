# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

# Modulos importados dinamicamente que PyInstaller no detecta.
# Backend/*.py son data files — PyInstaller no escanea sus imports.
# Hay que declararlos todos aqui.
hidden_imports = [
    # Windows COM / OLAP
    'win32com.client',
    'win32com.server',
    'pythoncom',
    'adodbapi',
    'adodbapi.adodbapi',
    'adodbapi.apibase',
    # Asyncio con submodulos Windows (olap_service lo importa a nivel modulo)
    'asyncio',
    'asyncio.windows_events',
    'asyncio.windows_utils',
    'concurrent.futures',
    # Data / crypto
    'pandas',
    'pandas.core',
    'pandas.io',
    'dotenv',
    'keyring',
    'keyring.backends.Windows',
    'cryptography.fernet',
    # Stdlib usado en backend
    'sqlite3',
    'uuid',
    'queue',
    'logging.handlers',
]

excludes = [
    # Mock provider — solo para dev Linux, no va en el exe
    'mock_service',
    'provider_mock',
    'core.provider_mock',
    # No necesarios en el exe
    'matplotlib',
    'tkinter',
    'test',
    'unittest',
    'pytest',
    'IPython',
]

backend_path = os.path.abspath(os.path.join('.', '..', 'backend'))

datas_list = [
    ('ui/resources/style.qss', 'ui/resources'),
    (backend_path, 'backend'),
]

a = Analysis(
    ['__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=datas_list,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='xtractor_ui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # True para diagnostico en V1
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='xtractor_ui',
)
