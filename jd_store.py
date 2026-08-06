#!/usr/bin/env python3
"""
Job Description Store (Tier B)
Persists imported job descriptions (raw text + extracted fields + optional
embedding) as JSON files under data/jds/, indexed in a small SQLite database.
This builds the local JD corpus that powers insights and future fine-tuning.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import DATA_DIR

JD_DIR = DATA_DIR / "jds"
JD_DB = DATA_DIR / "jds.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT,
    role TEXT,
    slug TEXT UNIQUE,
    file_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s or "jd"


def _make_slug(company: str, role: str, raw_text: str) -> str:
    base = _slugify(company or role)
    digest = hashlib.sha1(raw_text.encode("utf-8", "ignore")).hexdigest()[:8]
    return f"{base}_{digest}" if base != "jd" else f"jd_{digest}"


class JDStore:
    """SQLite + JSON store for job descriptions."""

    def __init__(self, db_path: Optional[str] = None, jd_dir: Optional[str] = None):
        self.db_path = db_path or str(JD_DB)
        self.jd_dir = jd_dir or str(JD_DIR)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.jd_dir, exist_ok=True)
        self.init_db()

    @staticmethod
    def _connect(db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        conn = self._connect(self.db_path)
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def save_jd(
        self,
        company: str,
        role: str,
        raw_text: str,
        extraction: Dict[str, Any],
    ) -> str:
        """Persist a JD (JSON file + index row). Returns the slug."""
        company = (company or "").strip()
        role = (role or "").strip()
        raw_text = raw_text or ""

        embed_vector = None
        try:
            import embeddings

            if embeddings.available() and raw_text.strip():
                embed_vector = embeddings.embed(raw_text[:800])
        except Exception:
            embed_vector = None

        slug = _make_slug(company, role, raw_text)
        record = {
            "slug": slug,
            "company": company,
            "role": role,
            "raw_text": raw_text,
            "embedding": embed_vector,
            "extraction": extraction,
            "created_at": datetime.now().isoformat(),
        }
        file_path = os.path.join(self.jd_dir, f"{slug}.json")
        with open(file_path, "w") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        conn = self._connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO jds (company, role, slug, file_path) "
                "VALUES (?, ?, ?, ?)",
                (company, role, slug, file_path),
            )
            conn.commit()
        finally:
            conn.close()
        return slug

    def list_jds(self) -> List[Dict[str, Any]]:
        conn = self._connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT id, company, role, slug, file_path, created_at "
                "FROM jds ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_jd(self, slug: str) -> Optional[Dict[str, Any]]:
        conn = self._connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT file_path FROM jds WHERE slug = ?", (slug,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            with open(row["file_path"]) as f:
                return json.load(f)
        except Exception:
            return None

    def count(self) -> int:
        conn = self._connect(self.db_path)
        try:
            row = conn.execute("SELECT COUNT(*) AS c FROM jds").fetchone()
            return int(row["c"])
        finally:
            conn.close()


_store = None


def get_jd_store() -> JDStore:
    """Lazily-created shared JDStore instance."""
    global _store
    if _store is None:
        _store = JDStore()
    return _store


def init_jd_db() -> None:
    """Ensure JD DB schema + dir exist (safe at startup)."""
    get_jd_store().init_db()
