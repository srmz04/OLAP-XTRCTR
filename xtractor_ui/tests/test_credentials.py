"""Tests del ProfileStore + credential_store."""
from __future__ import annotations
import sys
from pathlib import Path

import pytest
from core.config import ConnectionProfile, ProfileStore
from core import credential_store as cs


@pytest.fixture
def tmp_store(tmp_path):
    return ProfileStore(path=tmp_path / "profiles.json")


def test_store_empty_at_start(tmp_store):
    assert tmp_store.list_profiles() == []


def test_save_and_load(tmp_store):
    p = ConnectionProfile(name="demo", server="olap.example.test",
                          user="demo_user", default_catalog="DEMO_CUBE")
    tmp_store.save(p, password="s3cr3t")
    loaded = tmp_store.load("demo")
    assert loaded is not None
    assert loaded.server == "olap.example.test"
    assert loaded.default_catalog == "DEMO_CUBE"
    assert tmp_store.load_password("demo") == "s3cr3t"


def test_list_profiles(tmp_store):
    tmp_store.save(ConnectionProfile("a", "s1", "u1"), password="p1")
    tmp_store.save(ConnectionProfile("b", "s2", "u2"), password="p2")
    names = tmp_store.list_profiles()
    assert "a" in names and "b" in names


def test_delete_profile(tmp_store):
    tmp_store.save(ConnectionProfile("del", "srv", "usr"), password="pw")
    tmp_store.delete("del")
    assert "del" not in tmp_store.list_profiles()


def test_overwrite_profile(tmp_store):
    tmp_store.save(ConnectionProfile("dup", "s1", "u1"), password="p1")
    tmp_store.save(ConnectionProfile("dup", "s2", "u2"), password="p2")
    assert tmp_store.load("dup").server == "s2"
    assert tmp_store.load_password("dup") == "p2"


def test_file_fallback_encrypts(tmp_path, monkeypatch):
    """El fallback escribe Fernet, no texto plano."""
    creds_file = tmp_path / ".creds"
    monkeypatch.setattr(cs, "_CREDS_FILE", creds_file)
    cs._file_save("test_prof", "MySecret99!")
    raw = creds_file.read_bytes()
    assert b"MySecret99!" not in raw
    assert raw.startswith(b"gAAAAA")  # Fernet token prefix
    assert cs._file_load("test_prof") == "MySecret99!"


def test_file_fallback_delete(tmp_path, monkeypatch):
    creds_file = tmp_path / ".creds"
    monkeypatch.setattr(cs, "_CREDS_FILE", creds_file)
    cs._file_save("a", "pw_a")
    cs._file_save("b", "pw_b")
    cs._file_delete("a")
    assert cs._file_load("a") == ""
    assert cs._file_load("b") == "pw_b"


def test_file_fallback_migrates_legacy_base64(tmp_path, monkeypatch):
    """Archivos base64 legacy se migran a Fernet al leerlos."""
    import base64, json
    creds_file = tmp_path / ".creds"
    monkeypatch.setattr(cs, "_CREDS_FILE", creds_file)
    # Escribir en formato legacy (base64)
    legacy = base64.b64encode(json.dumps({"old_prof": "old_pw"}).encode())
    creds_file.write_bytes(legacy)
    # Leer debe funcionar y migrar
    assert cs._file_load("old_prof") == "old_pw"
    # Verificar que el archivo ya no es base64 plano
    raw = creds_file.read_bytes()
    assert raw.startswith(b"gAAAAA")
