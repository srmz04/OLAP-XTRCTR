"""
Perfiles de conexion: serializa/deserializa JSON sin guardar passwords.
Los passwords van en credential_store.py (keyring o fallback encriptado).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ConnectionProfile:
    name: str
    server: str
    user: str
    default_catalog: str = ""

    def to_dict(self):
        return {
            "name": self.name,
            "server": self.server,
            "user": self.user,
            "default_catalog": self.default_catalog,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConnectionProfile":
        return cls(
            name=d.get("name", ""),
            server=d.get("server", ""),
            user=d.get("user", ""),
            default_catalog=d.get("default_catalog", ""),
        )


class ProfileStore:
    """Persiste perfiles de conexion en JSON local (sin passwords)."""

    def __init__(self, path: Optional[Path] = None):
        if path is None:
            base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
            path = base / "xtractor_ui" / "profiles.json"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> List[ConnectionProfile]:
        if not self.path.exists():
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return [ConnectionProfile.from_dict(d) for d in data]
        except Exception:
            return []

    def save_all(self, profiles: List[ConnectionProfile]):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in profiles], f, indent=2, ensure_ascii=False)

    def list_profiles(self) -> List[str]:
        return [p.name for p in self.load_all()]

    def load(self, name: str) -> "Optional[ConnectionProfile]":
        for p in self.load_all():
            if p.name == name:
                return p
        return None

    def save(self, profile: "ConnectionProfile", password: str = ""):
        existing = self.load_all()
        existing = [p for p in existing if p.name != profile.name]
        existing.append(profile)
        self.save_all(existing)
        if password:
            from core.credential_store import save_password
            save_password(profile.name, password)

    def load_password(self, name: str) -> str:
        from core.credential_store import load_password
        return load_password(name)

    def delete(self, name: str):
        existing = [p for p in self.load_all() if p.name != name]
        self.save_all(existing)
