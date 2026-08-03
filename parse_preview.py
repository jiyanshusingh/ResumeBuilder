#!/usr/bin/env python3
"""
ATS Parse Preview Module

Simulates what an Applicant Tracking System (ATS) parser would extract from a
resume so users can verify their resume is machine-readable.

Pure stdlib - reuses skill/action-verb vocabularies from jd_importer and
ats_scorer where available.
"""

import re
from typing import Any, Dict, List, Optional

STANDARD_SECTIONS = [
    "Contact",
    "Summary",
    "Objective",
    "Experience",
    "Education",
    "Skills",
    "Projects",
    "Certifications",
    "Awards",
    "Languages",
    "Interests",
    "Publications",
    "References",
]

# Contact regexes
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w-]+", re.IGNORECASE)
GITHUB_RE = re.compile(r"github\.com/[\w-]+", re.IGNORECASE)
YEARS_RE = re.compile(
    r"(\d{1,2})\s*\+?\s*years?\s*(?:of)?\s*(?:professional\s*)?experience",
    re.IGNORECASE,
)


def _load_skill_vocab():
    """Return skill categories and action verbs (with graceful fallback)."""
    try:
        from jd_importer import ACTION_VERBS, SKILL_CATEGORIES

        return SKILL_CATEGORIES, ACTION_VERBS
    except Exception:
        return {}, []


def extract_contact_fields(text: str) -> Dict[str, str]:
    """Extract contact info from resume text via regex."""
    fields: Dict[str, str] = {}
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    linkedin = LINKEDIN_RE.search(text)
    github = GITHUB_RE.search(text)

    fields["email"] = email.group(0) if email else ""
    fields["phone"] = phone.group(0) if phone else ""
    fields["linkedin"] = linkedin.group(0) if linkedin else ""
    fields["github"] = github.group(0) if github else ""

    # First non-empty line is typically the name
    for line in text.splitlines():
        line = line.strip()
        if line and not re.search(r"[\d@]", line) and len(line) < 60:
            fields["name"] = line.strip()
            break
    else:
        fields["name"] = ""
    return fields


def detect_sections(text: str) -> List[str]:
    """Return the list of standard section headers present in the resume."""
    lower = text.lower()
    found = []
    for sec in STANDARD_SECTIONS:
        if re.search(rf"\b{re.escape(sec.lower())}\b", lower):
            found.append(sec)
    return found


def extract_skills(text: str) -> List[str]:
    """Extract recognized skill tokens from the text, preserving order."""
    try:
        from ats_scorer import ATSScorer

        found = ATSScorer._extract_skills_from_text(text)
        if found:
            return found
    except Exception:
        pass

    # Fallback: use jd_importer vocabulary
    try:
        from jd_importer import SKILL_CATEGORIES

        lower = text.lower()
        found = []
        for skills in SKILL_CATEGORIES.values():
            for s in skills:
                if s.lower() in lower and s.lower() not in [f.lower() for f in found]:
                    found.append(s)
        return found
    except Exception:
        return []


def extract_action_verbs(text: str) -> List[str]:
    """Return recognized action verbs present in the resume."""
    verbs = _load_skill_vocab()[1]
    if not verbs:
        return []
    lower = text.lower()
    return [v for v in verbs if v.lower() in lower][:15]


def extract_metrics(text: str) -> List[str]:
    """Return snippets containing numeric metrics (%, $, #, K, etc)."""
    patterns = [
        r"[\+\-]?[\d,]+(?:\.\d+)?\s*%",
        r"[₹$€£]\s?[\d,]+(?:\.\d+)?[KkMm]?",
        r"\b\d+(?:,\d{3})+\b",
        r"\b\d+[Kk]\+?\b",
    ]
    found = []
    combined = r"|".join(patterns)
    for m in re.finditer(combined, text):
        s = text[max(0, m.start() - 30) : m.end() + 10].replace("\n", " ")
        if s not in found:
            found.append(s)
        if len(found) >= 20:
            break
    return found


def estimate_pages(word_count: int) -> str:
    """Heuristic page estimate (~500 words/page)."""
    if word_count <= 0:
        return "unknown"
    pages = word_count / 500
    if pages < 0.8:
        return "<1 (short)"
    if pages <= 1.3:
        return "1"
    if pages <= 2.3:
        return "2"
    return "3+"


def parse_resume_for_ats(text: str) -> Dict[str, Any]:
    """Run a simulated ATS parse over the resume text."""
    if not text or not text.strip():
        return {"error": "No text to parse."}

    contact = extract_contact_fields(text)
    sections = detect_sections(text)
    skills = extract_skills(text)
    word_count = len(text.split())
    metrics = extract_metrics(text)
    action_verbs = extract_action_verbs(text)

    years = YEARS_RE.search(text)

    return {
        "contact": contact,
        "sections_found": sections,
        "missing_sections": [
            s for s in STANDARD_SECTIONS if s not in sections and s != "Contact"
        ],
        "skills_extracted": skills,
        "action_verbs": action_verbs,
        "metrics_found": metrics,
        "word_count": word_count,
        "pages_estimate": estimate_pages(word_count),
        "years_experience": years.group(0) if years else "",
        "parseable": word_count > 0,
    }


SECTION_LOOKUP = {
    "Skills": ["Skills", "Technical Skills", "Core Competencies"],
    "Experience": ["Experience", "Work Experience", "Professional Experience"],
    "Education": ["Education", "Academic"],
    "Projects": ["Projects", "Personal Projects"],
    "Certifications": ["Certification", "Courses"],
    "Awards": ["Awards", "Honors"],
}


def format_parse_preview(result: Dict[str, Any]) -> str:
    """Render the parsed ATS result as a readable report."""
    if "error" in result:
        return result["error"]

    lines = []
    lines.append("=" * 60)
    lines.append("ATS PARSE PREVIEW (simulated)")
    lines.append("=" * 60)

    contact = result.get("contact", {})
    lines.append("\n--- CONTACT INFO PARSED ---")
    for key in ["name", "email", "phone", "linkedin", "github"]:
        val = contact.get(key, "")
        lines.append(f"{key.capitalize()}: {val if val else '(none found)'}")

    lines.append("\n--- SECTIONS RECOGNIZED ---")
    found = result.get("sections_found", [])
    missing = result.get("missing_sections", [])
    lines.append(f"Found ({len(found)}): {', '.join(found) if found else 'none'}")
    lines.append(f"Missing: {', '.join(missing) if missing else 'none (great!)'}")

    lines.append("\n--- SKILLS EXTRACTED ---")
    skills = result.get("skills_extracted", [])
    lines.append(", ".join(skills[:20]) if skills else "(none recognized)")

    lines.append("\n--- ACTION VERBS DETECTED ---")
    verbs = result.get("action_verbs", [])
    lines.append(", ".join(verbs) if verbs else "(none)")

    lines.append("\n--- QUANTIFIED METRICS DETECTED ---")
    metrics = result.get("metrics_found", [])
    lines.append("\n".join(f"• {m}" for m in metrics) if metrics else "(none)")

    lines.append("\n--- DOCUMENT METADATA ---")
    lines.append(f"Words: {result.get('word_count', 0)}")
    lines.append(f"Estimated length: {result.get('pages_estimate', 'unknown')}")
    lines.append(f"Stated experience: {result.get('years_experience', 'n/a')}")

    return "\n".join(lines)
