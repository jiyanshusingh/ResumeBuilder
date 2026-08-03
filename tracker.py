#!/usr/bin/env python3
"""
Job Application Tracker Module
Stores and manages job applications in a SQLite database.

Uses stdlib sqlite3 only - no external dependencies.
The database is config-driven via DATA_DIR (see config.py).
"""
import os
import sqlite3
from datetime import date, datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from config import DATA_DIR

DEFAULT_DB_PATH = DATA_DIR / "job_applications.db"

# Allowed job application status values
APPLICATION_STATUSES = [
    "Applied",
    "Interview Scheduled",
    "Interviewed",
    "Offer",
    "Rejected",
    "On Hold",
    "Withdrawn",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    applied_date TEXT,
    status TEXT,
    notes TEXT,
    ats_score REAL,
    resume_version INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class JobTracker:
    """SQLite-backed job application tracker."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(DEFAULT_DB_PATH)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    @staticmethod
    def _connect(db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._connect(self.db_path)
        try:
            conn.execute(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def add_application(self, company: str, role: str,
                        applied_date: Optional[str] = None,
                        status: str = "Applied",
                        notes: str = "",
                        ats_score: Optional[float] = None,
                        resume_version: int = 0) -> int:
        """Add a new application. Returns the new row id."""
        if not company or not role:
            raise ValueError("Company and role are required.")
        if status not in APPLICATION_STATUSES:
            # Don't strictly enforce to avoid breaking UI lists; store as-is.
            pass
        applied_date = applied_date or date.today().isoformat()

        conn = self._connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO applications "
                "(company, role, applied_date, status, notes, ats_score, resume_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (company, role, applied_date, status, notes, ats_score, resume_version),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def update_status(self, app_id: int, status: str, notes: Optional[str] = None) -> None:
        """Update status (and optionally notes) for an application."""
        conn = self._connect(self.db_path)
        try:
            if notes is None:
                conn.execute(
                    "UPDATE applications SET status = ?, updated_at = ? WHERE id = ?",
                    (status, datetime.now().isoformat(), app_id),
                )
            else:
                conn.execute(
                    "UPDATE applications SET status = ?, notes = ?, updated_at = ? WHERE id = ?",
                    (status, notes, datetime.now().isoformat(), app_id),
                )
            conn.commit()
        finally:
            conn.close()

    def update_application(self, app_id: int, **fields) -> None:
        """Generic field update for an application row."""
        allowed = {"company", "role", "applied_date", "status", "notes",
                   "ats_score", "resume_version"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        conn = self._connect(self.db_path)
        try:
            sets = ", ".join(f"{k} = ?" for k in updates)
            vals = list(updates.values())
            vals.append(app_id)
            conn.execute(
                f"UPDATE applications SET {sets}, updated_at = ? WHERE id = ?",
                [*vals[:-1], datetime.now().isoformat(), app_id],
            )
            conn.commit()
        finally:
            conn.close()

    def delete_application(self, app_id: int) -> None:
        """Delete an application by id."""
        conn = self._connect(self.db_path)
        try:
            conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
            conn.commit()
        finally:
            conn.close()

    def list_applications(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List applications, optionally filtered by status. Newest first."""
        conn = self._connect(self.db_path)
        try:
            if status_filter and status_filter != "All":
                rows = conn.execute(
                    "SELECT * FROM applications WHERE status = ? ORDER BY applied_date DESC",
                    (status_filter,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM applications ORDER BY applied_date DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_application(self, app_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single application by id."""
        conn = self._connect(self.db_path)
        try:
            row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_status_counts(self) -> Dict[str, int]:
        """Return counts of applications per status."""
        conn = self._connect(self.db_path)
        try:
            rows = conn.execute("SELECT status, COUNT(*) as cnt FROM applications GROUP BY status").fetchall()
            return {r["status"]: r["cnt"] for r in rows}
        finally:
            conn.close()

    @staticmethod
    def to_dataframe_rows(applications: List[Dict[str, Any]]) -> List[list]:
        """Convert list of dicts to a dataframe-friendly list of rows."""
        headers = ["ID", "Company", "Role", "Applied", "Status", "ATS", "Notes"]
        rows = []
        for a in applications:
            rows.append([
                a["id"],
                a["company"],
                a["role"],
                a.get("applied_date", ""),
                a.get("status", ""),
                a.get("ats_score", 0),
                a.get("notes", "") or "",
            ])
        return headers, rows


# Convenience module-level singleton (lazy)
_tracker = None


def get_tracker() -> JobTracker:
    """Return a lazily-created shared JobTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = JobTracker()
    return _tracker


def init_db() -> None:
    """Ensure DB schema exists (safe to call at startup)."""
    get_tracker().init_db()