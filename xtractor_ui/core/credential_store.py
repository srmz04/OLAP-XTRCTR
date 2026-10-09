"""
credential_store: guarda passwords de forma segura.
Intenta keyring primero; si no disponible usa Fernet (AES-128-CBC)
con clave derivada del machine-id del sistema.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_SERVICE = "xtractor_ui"
_CREDS_FILE = Path(os.environ.get("APPDATA", Path.home() / ".config")) / "xtractor_ui" / ".creds"


def _derive_key() -> bytes:
    """Deriva clave Fernet del machine-id (Linux) o MAC address (fallback)."""
    seed = ""
    try:
        seed = Path("/etc/machine-id").read_text().strip()
    except Exception:
        pass
    if not seed:
        seed = str(uuid.getnode())
    raw = hashlib.sha256(f"xtractor_ui:{seed}".encode()).digest()
    return base64.urlsafe_b64encode(raw)


_fernet = Fernet(_derive_key())


def save_password(profile_name: str, password: str) -> bool:
    """Guarda password. Retorna True si OK."""
    try:
        import keyring  # type: ignore
        keyring.set_password(_SERVICE, profile_name, password)
        return True
    except Exception:
        return _file_save(profile_name, password)


def load_password(profile_name: str) -> str:
    """Carga password. Retorna '' si no existe."""
    try:
        import keyring  # type: ignore
        pw = keyring.get_password(_SERVICE, profile_name)
        return pw or ""
    except Exception:
        return _file_load(profile_name)


def delete_password(profile_name: str):
    """Elimina password del store."""
    try:
        import keyring  # type: ignore
        keyring.delete_password(_SERVICE, profile_name)
    except Exception:
        pass
    _file_delete(profile_name)


# ── Fallback file-based store (Fernet encrypted) ──────────────────

def _file_save(name: str, pw: str) -> bool:
    _CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = _file_read_all()
    data[name] = pw
    encrypted = _fernet.encrypt(json.dumps(data).encode())
    _CREDS_FILE.write_bytes(encrypted)
    return True


def _file_load(name: str) -> str:
    data = _file_read_all()
    return data.get(name, "")


def _file_delete(name: str):
    data = _file_read_all()
    data.pop(name, None)
    if data:
        encrypted = _fernet.encrypt(json.dumps(data).encode())
        _CREDS_FILE.write_bytes(encrypted)
    elif _CREDS_FILE.exists():
        _CREDS_FILE.unlink()


def _file_read_all() -> dict:
    if not _CREDS_FILE.exists():
        return {}
    raw = _CREDS_FILE.read_bytes()
    # Intentar Fernet primero
    try:
        return json.loads(_fernet.decrypt(raw))
    except InvalidToken:
        pass
    # Fallback: migrar desde base64 legacy
    try:
        data = json.loads(base64.b64decode(raw))
        # Re-guardar encriptado
        _CREDS_FILE.write_bytes(_fernet.encrypt(json.dumps(data).encode()))
        return data
    except Exception:
        return {}
