#!/usr/bin/env python3
"""
Resume Comparison Module
Runs ATS scoring for the same resume against multiple companies and/or roles,
producing a side-by-side comparison table and an optional bar chart.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from ats_scorer import ATSScorer
from config import DATA_DIR
from resume_builder import load_company_profile

COMPANY_DIR = DATA_DIR / "companies"


def list_company_slugs() -> List[str]:
    """Return slugs of all saved company profiles."""
    if not os.path.isdir(COMPANY_DIR):
        return []
    return [
        f.replace(".json", "") for f in os.listdir(COMPANY_DIR) if f.endswith(".json")
    ]


def list_company_roles() -> Dict[str, List[str]]:
    """Return mapping of company slug -> list of job roles."""
    out = {}
    for slug in list_company_slugs():
        try:
            profile = load_company_profile(slug)
            out[slug] = list(profile.get("job_roles", {}).keys())
        except Exception:
            out[slug] = []
    return out


def compare_resume(
    resume_text: str,
    companies: Optional[List[str]] = None,
    roles: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Score the same resume text against one or more companies.
    companies: list of company slugs. Defaults to all.
    roles: optional dict slug -> role name. Defaults to first role per company.
    Returns a list of result dicts, one per company.
    """
    companies = companies or list_company_slugs()
    roles = roles or {}
    results = []

    for slug in companies:
        if slug not in list_company_slugs():
            continue
        try:
            profile = load_company_profile(slug)
        except Exception:
            continue

        available_roles = list(profile.get("job_roles", {}).keys())
        if not available_roles:
            continue
        role = roles.get(slug) or available_roles[0]
        if role not in available_roles:
            role = available_roles[0]

        try:
            result = ATSScorer(resume_text, file_extension=".pdf").score(slug, role)
        except Exception as e:
            results.append(
                {
                    "slug": slug,
                    "company": profile.get("name", slug),
                    "role": role,
                    "ats_score": None,
                    "passed_rules": 0,
                    "total_rules": 0,
                    "suggestions": [f"Error scoring: {e}"],
                    "error": True,
                }
            )
            continue

        passed = result.get("passed_rules", 0)
        total = result.get("total_rules", 0)
        suggestions = result.get("suggestions", [])[:3]
        results.append(
            {
                "slug": slug,
                "company": profile.get("name", slug),
                "role": role,
                "ats_score": round(result.get("overall_score", 0), 1),
                "passed_rules": passed,
                "total_rules": total,
                "suggestions": suggestions,
                "error": False,
            }
        )

    # Sort by score descending (None last)
    results.sort(key=lambda r: (r["ats_score"] is None, -(r["ats_score"] or 0)))
    return results


def comparison_header(results: List[Dict[str, Any]]) -> List[list]:
    """Produce a dataframe-friendly matrix."""
    headers = ["Company", "Role", "ATS Score", "Rules Passed", "Top Suggestions"]
    rows = []
    for r in results:
        sug = "; ".join(r["suggestions"]) if r["suggestions"] else ""
        rows.append(
            [
                r["company"],
                r["role"],
                r["ats_score"] if r["ats_score"] is not None else "—",
                (
                    f"{r['passed_rules']}/{r['total_rules']}"
                    if r.get("passed_rules") is not None
                    else "—"
                ),
                sug,
            ]
        )
    return headers, rows


def create_comparison_chart(
    results: List[Dict[str, Any]], output_dir: Optional[str] = None
) -> Optional[str]:
    """Build a bar chart of ATS scores per company. Returns chart filepath."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    scored = [r for r in results if r["ats_score"] is not None]
    if not scored:
        return None

    labels = [f"{r['company']}\n{r['role']}" for r in scored]
    values = [r["ats_score"] for r in scored]

    out_dir = output_dir or str(DATA_DIR / "comparisons")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "ats_comparison.png")

    fig, ax = plt.subplots(figsize=(9, max(4, 1.2 * len(labels))))
    bars = ax.barh(labels, values, color="#2563eb")
    ax.axvline(80, color="green", linestyle="--", linewidth=1, label="Target 80+")
    ax.axvline(50, color="orange", linestyle=":", linewidth=1, label="Moderate 50")
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{val}%",
            va="center",
            fontsize=9,
        )
    ax.set_xlim(0, max(values) + 20)
    ax.set_xlabel("ATS Score (%)")
    ax.set_title("Resume ATS Score by Company")
    ax.legend(loc="lower right")
    plt.tight_layout()
    saved = []
    try:
        plt.savefig(path, dpi=120)
        saved.append(path)
    finally:
        plt.close(fig)
    return path or None
