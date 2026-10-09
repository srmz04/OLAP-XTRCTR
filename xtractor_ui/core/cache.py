"""
MetadataCache: SQLite local para metadata OLAP descargada.
Ubicacion: %LOCALAPPDATA%/xtractor_ui/ en Windows,
           ~/.local/share/xtractor_ui/ en Linux.
NO guardar en Dropbox (corrupcion por sync).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


def _default_dir() -> Path:
    import sys, os
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "xtractor_ui"
    d.mkdir(parents=True, exist_ok=True)
    return d


class MetadataCache:
    """
    Cache SQLite thread-safe (WAL mode, un solo writer).
    Almacena catalogs, measures y members con timestamp de expiracion.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = _default_dir() / "metadata_cache.db"
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = self._open_db()

    def _open_db(self) -> sqlite3.Connection:
        try:
            db = sqlite3.connect(str(self._path), check_same_thread=False)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            self._init_schema(db)
        except sqlite3.DatabaseError:
            db.close()
            self._path.unlink(missing_ok=True)
            db = sqlite3.connect(str(self._path), check_same_thread=False)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            self._init_schema(db)
        return db

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_schema(self, db: sqlite3.Connection):
        db.executescript("""
            CREATE TABLE IF NOT EXISTS catalog_meta (
                catalog     TEXT PRIMARY KEY,
                data_json   TEXT,
                fetched_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS members (
                catalog         TEXT NOT NULL,
                dimension       TEXT NOT NULL,
                hierarchy       TEXT NOT NULL,
                level_name      TEXT NOT NULL,
                member_caption  TEXT NOT NULL,
                member_unique   TEXT NOT NULL,
                ordinal         INTEGER DEFAULT 0,
                fetched_at      TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_members_lookup
                ON members(catalog, dimension, hierarchy, level_name);

            CREATE TABLE IF NOT EXISTS queries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog     TEXT NOT NULL,
                name        TEXT NOT NULL,
                mdx         TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                last_used   TEXT
            );
        """)
        db.commit()

    # ── Staleness ─────────────────────────────────────────────────────────────

    def is_stale(self, catalog: str, max_age_hours: int = 24) -> bool:
        row = self._db.execute(
            "SELECT fetched_at FROM catalog_meta WHERE catalog = ?", (catalog,)
        ).fetchone()
        if not row:
            return True
        try:
            fetched = datetime.fromisoformat(row[0])
            return datetime.now() - fetched > timedelta(hours=max_age_hours)
        except ValueError:
            return True

    def touch_catalog(self, catalog: str, meta: Optional[dict] = None):
        """Registra que el catalogo fue descargado ahora."""
        self._db.execute(
            """INSERT INTO catalog_meta(catalog, data_json, fetched_at)
               VALUES(?, ?, ?)
               ON CONFLICT(catalog) DO UPDATE
               SET data_json=excluded.data_json, fetched_at=excluded.fetched_at""",
            (catalog, json.dumps(meta or {}), datetime.now().isoformat()),
        )
        self._db.commit()

    # ── Members ───────────────────────────────────────────────────────────────

    def save_members(self, catalog: str, dimension: str, hierarchy: str,
                     level_name: str, members: List[Dict]) -> int:
        """Guarda miembros de un nivel, reemplazando los anteriores."""
        self._db.execute(
            "DELETE FROM members WHERE catalog=? AND dimension=? AND hierarchy=? AND level_name=?",
            (catalog, dimension, hierarchy, level_name),
        )
        now = datetime.now().isoformat()
        rows = [
            (catalog, dimension, hierarchy, level_name,
             m.get("caption", ""), m.get("unique_name", m.get("uniqueName", "")),
             i, now)
            for i, m in enumerate(members)
        ]
        self._db.executemany(
            """INSERT INTO members
               (catalog, dimension, hierarchy, level_name, member_caption,
                member_unique, ordinal, fetched_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._db.commit()
        return len(rows)

    def get_members(self, catalog: str, dimension: str,
                    hierarchy: str, level_name: str = "") -> List[Dict]:
        if level_name:
            rows = self._db.execute(
                """SELECT member_caption, member_unique FROM members
                   WHERE catalog=? AND dimension=? AND hierarchy=? AND level_name=?
                   ORDER BY ordinal""",
                (catalog, dimension, hierarchy, level_name),
            ).fetchall()
        else:
            rows = self._db.execute(
                """SELECT member_caption, member_unique FROM members
                   WHERE catalog=? AND dimension=? AND hierarchy=?
                   ORDER BY level_name, ordinal""",
                (catalog, dimension, hierarchy),
            ).fetchall()
        return [{"caption": r[0], "unique_name": r[1]} for r in rows]

    def has_members(self, catalog: str, dimension: str,
                    hierarchy: str, level_name: str) -> bool:
        count = self._db.execute(
            """SELECT COUNT(*) FROM members
               WHERE catalog=? AND dimension=? AND hierarchy=? AND level_name=?""",
            (catalog, dimension, hierarchy, level_name),
        ).fetchone()[0]
        return count > 0

    def clear_catalog(self, catalog: str):
        self._db.execute("DELETE FROM catalog_meta WHERE catalog=?", (catalog,))
        self._db.execute("DELETE FROM members WHERE catalog=?", (catalog,))
        self._db.commit()

    def get_catalog_meta(self, catalog: str) -> Optional[dict]:
        """Retorna metadata JSON del catalogo o None."""
        row = self._db.execute(
            "SELECT data_json FROM catalog_meta WHERE catalog = ?", (catalog,)
        ).fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, ValueError):
            return None

    # ── Saved queries ─────────────────────────────────────────────────────────

    def save_query(self, catalog: str, name: str, mdx: str) -> int:
        cur = self._db.execute(
            """INSERT INTO queries(catalog, name, mdx, created_at)
               VALUES(?, ?, ?, ?)""",
            (catalog, name, mdx, datetime.now().isoformat()),
        )
        self._db.commit()
        return cur.lastrowid

    def list_queries(self, catalog: str = "") -> List[Dict]:
        if catalog:
            rows = self._db.execute(
                "SELECT id, catalog, name, mdx, created_at FROM queries WHERE catalog=? ORDER BY id DESC",
                (catalog,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT id, catalog, name, mdx, created_at FROM queries ORDER BY id DESC"
            ).fetchall()
        return [
            {"id": r[0], "catalog": r[1], "name": r[2], "mdx": r[3], "created_at": r[4]}
            for r in rows
        ]

    def delete_query(self, query_id: int):
        self._db.execute("DELETE FROM queries WHERE id=?", (query_id,))
        self._db.commit()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self):
        self._db.close()

    @property
    def path(self) -> Path:
        return self._path

    @staticmethod
    def default_path() -> Path:
        return _default_dir() / "metadata_cache.db"
