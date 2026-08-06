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
from pathlib import Path
from typing import Any, Dict, List, Optional

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

CREATE TABLE IF NOT EXISTS resume_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER,
    version_number INTEGER NOT NULL,
    file_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES applications(id)
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
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def add_application(
        self,
        company: str,
        role: str,
        applied_date: Optional[str] = None,
        status: str = "Applied",
        notes: str = "",
        ats_score: Optional[float] = None,
        resume_version: int = 0,
    ) -> int:
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

    def update_status(
        self, app_id: int, status: str, notes: Optional[str] = None
    ) -> None:
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
        allowed = {
            "company",
            "role",
            "applied_date",
            "status",
            "notes",
            "ats_score",
            "resume_version",
        }
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

    def list_applications(
        self, status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
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
            row = conn.execute(
                "SELECT * FROM applications WHERE id = ?", (app_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_status_counts(self) -> Dict[str, int]:
        """Return counts of applications per status."""
        conn = self._connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM applications GROUP BY status"
            ).fetchall()
            return {r["status"]: r["cnt"] for r in rows}
        finally:
            conn.close()

    @staticmethod
    def to_dataframe_rows(applications: List[Dict[str, Any]]) -> List[list]:
        """Convert list of dicts to a dataframe-friendly list of rows."""
        headers = ["ID", "Company", "Role", "Applied", "Status", "ATS", "Notes"]
        rows = []
        for a in applications:
            rows.append(
                [
                    a["id"],
                    a["company"],
                    a["role"],
                    a.get("applied_date", ""),
                    a.get("status", ""),
                    a.get("ats_score", 0),
                    a.get("notes", "") or "",
                ]
            )
        return headers, rows

    # ── Resume versioning ──────────────────────────────
    def add_resume_version(self, application_id: int, file_path: str) -> int:
        """Record a resume .tex/.pdf snapshot for an application. Returns version number."""
        conn = self._connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) as v FROM resume_versions "
                "WHERE application_id = ?",
                (application_id,),
            ).fetchone()
            next_v = row["v"] + 1
            conn.execute(
                "INSERT INTO resume_versions (application_id, version_number, file_path) "
                "VALUES (?, ?, ?)",
                (application_id, next_v, file_path),
            )
            conn.execute(
                "UPDATE applications SET resume_version = ?, updated_at = ? WHERE id = ?",
                (next_v, datetime.now().isoformat(), application_id),
            )
            conn.commit()
            return next_v
        finally:
            conn.close()

    def list_resume_versions(self, application_id: int) -> List[Dict[str, Any]]:
        """List resume versions for an application (oldest first)."""
        conn = self._connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT id, application_id, version_number, file_path, created_at "
                "FROM resume_versions WHERE application_id = ? ORDER BY version_number",
                (application_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Insights (Tier B) ──────────────────────────────
    def analyze_insights(self) -> Dict[str, Any]:
        """Compute descriptive insights over tracked applications.

        Returns a dict with status counts, average ATS per status, best
        application per company, and a chart path (best-effort).
        """
        apps = self.list_applications()
        insights: Dict[str, Any] = {"total": len(apps)}
        insights["status_counts"] = self.get_status_counts()

        ats_by_status: Dict[str, List[float]] = {}
        for a in apps:
            score = a.get("ats_score")
            if score is None:
                continue
            ats_by_status.setdefault(a.get("status") or "?", []).append(float(score))
        insights["avg_ats_by_status"] = {
            k: round(sum(v) / len(v), 1) for k, v in ats_by_status.items()
        }

        best: Dict[str, Dict[str, Any]] = {}
        for a in apps:
            score = a.get("ats_score") or 0.0
            cur = best.get(a["company"])
            if cur is None or score > cur.get("ats_score", -1.0):
                best[a["company"]] = {
                    "role": a.get("role", ""),
                    "ats_score": score,
                    "status": a.get("status", ""),
                }
        insights["best_per_company"] = best

        insights["chart_path"] = self._insights_chart(ats_by_status)
        return insights

    def _insights_chart(self, ats_by_status: Dict[str, List[float]]) -> Optional[str]:
        """Bar chart of avg ATS by status. Returns path or None."""
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception:
            return None
        if not ats_by_status:
            return None
        labels = list(ats_by_status.keys())
        values = [round(sum(v) / len(v), 1) for v in ats_by_status.values()]
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(labels, values, color="#2c2c4a")
        ax.set_ylabel("Avg ATS Score")
        ax.set_title("Average ATS Score by Application Status")
        for i, v in enumerate(values):
            ax.text(i, v + 1, str(v), ha="center")
        out_dir = DATA_DIR / "comparisons"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = str(out_dir / "job_insights.png")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path


def format_insights(insights: Dict[str, Any]) -> str:
    """Human-readable summary of analyze_insights() output."""
    lines = [f"Total applications tracked: {insights.get('total', 0)}"]
    status_counts = insights.get("status_counts") or {}
    if status_counts:
        lines.append(
            "By status: " + " | ".join(f"{k}: {v}" for k, v in status_counts.items())
        )

    avg_ats = insights.get("avg_ats_by_status") or {}
    if avg_ats:
        lines.append(
            "Avg ATS by status: " + " | ".join(f"{k}: {v}" for k, v in avg_ats.items())
        )

    best = insights.get("best_per_company") or {}
    if best:
        lines.append("Highest-scoring application per company:")
        for company, info in best.items():
            lines.append(
                f"  • {company} — {info['role']} (ATS {info['ats_score']}, {info['status']})"
            )
    else:
        lines.append("No applications yet — add some to unlock insights.")
    return "\n".join(lines)


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
