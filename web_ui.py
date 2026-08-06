#!/usr/bin/env python3
"""
Web UI for Company-Specific Resume Builder (Enhanced)
Features:
1. Add/Edit Company profiles with job roles, skills, keywords
2. Generate tailored resumes with PDF output (.tex + .pdf)
3. Analyze existing PDF resumes against company requirements
4. Optimize resume suggestions (project reordering, skills, ATS score)
5. Manage saved company profiles

Usage:
  python3 web_ui.py
  Then open http://127.0.0.1:7860 in your browser.
"""

import io
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gradio as gr

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import matplotlib

    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from config import BASE_DIR, DATA_DIR, HOST, OUTPUT_DIR, PORT, SHARE
from resume_builder import (
    build_experience_block,
    build_resume,
    extract_bullets,
    get_placement_companies,
    get_placement_projects,
    get_placement_projects_by_company,
    get_template_path,
    load_company_profile,
    load_section_data,
    rank_projects,
)
from section_renderer import (
    render_coursework,
    render_internship,
)
from utils import latex_escape

try:
    from jd_importer import extract_from_jd_text, extract_from_jd_url, format_jd_result
except ImportError:
    extract_from_jd_text = extract_from_jd_url = format_jd_result = None
    HAS_JD_IMPORTER = False
else:
    HAS_JD_IMPORTER = True

from bullet_enhancer import enhance_bullets, format_enhancement_report
from compare import (
    compare_resume,
    comparison_header,
    create_comparison_chart,
    list_company_roles,
    list_company_slugs,
)
from jd_store import get_jd_store
from parse_preview import format_parse_preview, parse_resume_for_ats
from tracker import (
    APPLICATION_STATUSES,
    JobTracker,
    format_insights,
    get_tracker,
)
from tracker import init_db as init_tracker_db

# Seed tracker DB schema on startup (safe to call multiple times)
try:
    init_tracker_db()
except Exception:
    pass

_tracker = get_tracker()

COMPANY_DIR = str(DATA_DIR / "companies")
OUTPUT_DIR_STR = str(OUTPUT_DIR)
os.makedirs(COMPANY_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR_STR, exist_ok=True)

RESUME_TYPES = ["analytics", "software", "biotech", "finance", "freelance"]

TEMPLATE_TYPES = ["default", "modern", "minimalist", "academic", "jake"]

# ─── Utility Functions ────────────────────────────────────────────────


def slugify(s: str) -> str:
    """Convert string to URL-safe slug."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", s.lower()).strip("_")


def get_company_names() -> List[str]:
    """Returns display names (from each profile's `name` field) of all companies."""
    if not os.path.exists(COMPANY_DIR):
        return []
    names = []
    for fname in os.listdir(COMPANY_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(COMPANY_DIR, fname)
        try:
            with open(path) as f:
                names.append(json.load(f).get("name", ""))
        except Exception:
            names.append(fname.replace(".json", "").replace("_", " ").title())
    return sorted([n for n in names if n])


def resolve_company_key(company_display: str):
    """Return the profile slug (matched_key) for a display name, or None."""
    if not company_display:
        return None
    company_display = company_display.strip()
    for fname in os.listdir(COMPANY_DIR):
        if not fname.endswith(".json"):
            continue
        key = fname.replace(".json", "")
        path = os.path.join(COMPANY_DIR, fname)
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            data = {}
        stored_name = data.get("name", "")
        display = key.replace("_", " ").title()
        if (
            display.lower() == company_display.lower()
            or stored_name.lower() == company_display.lower()
            or key == slugify(company_display)
        ):
            return key
    return None


def get_company_roles(company_display: str) -> List[str]:
    """Return the list of saved job roles for a company display name."""
    if not company_display:
        return []
    try:
        from resume_builder import load_company_profile

        profile = load_company_profile(company_display)
    except Exception:
        return []
    return list(profile.get("job_roles", {}).keys())


def _role_update(company: str):
    """Build a gr.update for a role dropdown from the selected company."""
    roles = get_company_roles(company)
    value = roles[0] if roles else ""
    return gr.update(choices=roles, value=value)


def load_profile() -> Dict:
    """Load the base profile data."""
    path = str(DATA_DIR / "profile.json")
    with open(path) as f:
        return json.load(f)


def get_company_role_configs() -> Dict[str, List[str]]:
    """
    Build mapping: resume_type -> list of (company_display, role) tuples.
    Used for dynamic dropdown population.
    """
    mapping = {rt: [] for rt in RESUME_TYPES}
    for fname in os.listdir(COMPANY_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(COMPANY_DIR, fname)
        with open(path) as f:
            data = json.load(f)
        display = data["name"]
        for role, cfg in data.get("job_roles", {}).items():
            rt = cfg.get("resume_type", "analytics")
            if rt in mapping:
                mapping[rt].append((display, role))
    return mapping


# ─── Company Management ─────────────────────────────────────────────────


def save_company(
    name: str,
    website: str,
    role_name: str,
    resume_type: str,
    required_skills: str,
    keywords: str,
    emphasize_metrics: str,
) -> str:
    """Save a new/edited company profile."""
    if not name or not role_name:
        return "Error: Company name and role name are required."

    slug = slugify(name)
    path = os.path.join(COMPANY_DIR, f"{slug}.json")

    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    else:
        data = {"name": name.title(), "website": website, "job_roles": {}}

    skills = [s.strip() for s in required_skills.split(",") if s.strip()]
    kws = [k.strip() for k in keywords.split(",") if k.strip()]
    metrics = [m.strip() for m in emphasize_metrics.split(",") if m.strip()]

    data["job_roles"][role_name] = {
        "resume_type": resume_type,
        "required_skills": skills,
        "keywords": kws,
        "emphasize_metrics": metrics,
    }

    data["name"] = name.title()
    if website:
        data["website"] = website

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    return f"Saved company profile: {name} / {role_name}"


def list_all_companies() -> str:
    """List all companies and roles in a text area."""
    result = []
    if not os.path.exists(COMPANY_DIR):
        return "No companies saved yet."

    for fname in sorted(os.listdir(COMPANY_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(COMPANY_DIR, fname)) as f:
            data = json.load(f)
        result.append(f"**{data['name']}** ({data.get('website', 'N/A')})")
        for role, cfg in data.get("job_roles", {}).items():
            result.append(f"  - {role} [{cfg.get('resume_type', 'analytics')}]")
        result.append("")

    return "\n".join(result) if result else "No companies saved yet."


def delete_company(name: str) -> str:
    """Delete a company profile by name."""
    key = resolve_company_key(name)
    path = os.path.join(COMPANY_DIR, f"{key}.json") if key else None
    if key and os.path.exists(path):
        os.remove(path)
        return f"Deleted: {name}"
    return f"Not found: {name}"


# ─── Resume Generation ──────────────────────────────────────────────────


def generate_resume_wrapper(company_display: str, role: str, template_type: str = None):
    """Generate resume and return (tex_string, pdf_file, status)."""
    matched_key = resolve_company_key(company_display)

    if not matched_key:
        return None, None, f"Company not found: {company_display}"

    try:
        build_resume(matched_key, role, template_type=template_type)
    except Exception as e:
        return None, None, f"Build error: {str(e)}"

    safe_company = slugify(matched_key)
    safe_role = slugify(role)
    tex_path = os.path.join(OUTPUT_DIR_STR, f"resume_{safe_company}_{safe_role}.tex")
    pdf_path = os.path.join(OUTPUT_DIR_STR, f"resume_{safe_company}_{safe_role}.pdf")

    if not os.path.exists(tex_path):
        return None, None, "Failed to generate .tex file."

    with open(tex_path) as f:
        tex_content = f.read()

    pdf_out = pdf_path if os.path.exists(pdf_path) else None
    return tex_content, pdf_out, f"Generated: {tex_path}"


# ─── PDF Resume Analysis ────────────────────────────────────────────────


def extract_text_from_pdf(pdf_file) -> str:
    """Extract text content from an uploaded PDF file object."""
    if pdfplumber is None:
        return "Error: pdfplumber not installed. Run: pip install pdfplumber"

    if hasattr(pdf_file, "name"):
        path = pdf_file.name
    else:
        # Temporary save
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_file.read() if hasattr(pdf_file, "read") else pdf_file)
            path = tmp.name

    try:
        text_parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts)
    except Exception as e:
        return f"PDF extraction error: {str(e)}"
    finally:
        if not hasattr(pdf_file, "name"):
            try:
                os.unlink(path)
            except Exception:
                pass


def analyze_resume_skills(
    pdf_file, company_display: str, role: str
) -> Tuple[str, Optional[str]]:
    """
    Analyze an uploaded PDF resume against a company/role's required skills.
    Returns (analysis_text, chart_path_or_None).
    """
    # Extract text
    resume_text = extract_text_from_pdf(pdf_file)
    if resume_text.startswith("Error") or resume_text.startswith("PDF"):
        return resume_text, None

    # Normalize for search
    resume_lower = resume_text.lower()

    # Load company profile
    matched_key = resolve_company_key(company_display)

    if not matched_key:
        return "Company not found.", None

    try:
        company = load_company_profile(matched_key)
    except FileNotFoundError:
        return f"Company profile not found: {company_display}", None

    if role not in company.get("job_roles", {}):
        available = list(company.get("job_roles", {}).keys())
        return f"Role not found. Available: {available}", None

    role_cfg = company["job_roles"][role]
    required_skills = role_cfg.get("required_skills", [])
    keywords = role_cfg.get("keywords", [])

    # Skill matching
    matched_skills = []
    missing_skills = []
    for skill in required_skills:
        if skill.lower() in resume_lower:
            matched_skills.append(skill)
        else:
            missing_skills.append(skill)

    # Keyword density (simple presence check)
    present_keywords = []
    missing_keywords = []
    for kw in keywords:
        if kw.lower() in resume_lower:
            present_keywords.append(kw)
        else:
            missing_keywords.append(kw)

    # ATS Score calculation (weighted 60% skills, 40% keywords)
    skill_score = (len(matched_skills) / max(len(required_skills), 1)) * 0.6
    kw_score = (len(present_keywords) / max(len(keywords), 1)) * 0.4
    ats_score = round((skill_score + kw_score) * 100, 1)

    # Build analysis report
    lines = []
    lines.append("=" * 60)
    lines.append("RESUME ANALYSIS REPORT")
    lines.append("=" * 60)
    lines.append(f"\nCompany: {company['name']}")
    lines.append(f"Role: {role}")
    lines.append(f"Resume Type: {role_cfg.get('resume_type', 'analytics')}")
    lines.append("\n" + "-" * 60)
    lines.append("SKILLS MATCH")
    lines.append("-" * 60)
    lines.append(
        f"Matched ({len(matched_skills)}/{len(required_skills)}): {', '.join(matched_skills) if matched_skills else 'None'}"
    )
    lines.append(
        f"Missing ({len(missing_skills)}): {', '.join(missing_skills) if missing_skills else 'None'}"
    )

    lines.append("\n" + "-" * 60)
    lines.append("KEYWORD MATCH")
    lines.append("-" * 60)
    lines.append(
        f"Present ({len(present_keywords)}/{len(keywords)}): {', '.join(present_keywords) if present_keywords else 'None'}"
    )
    lines.append(
        f"Missing ({len(missing_keywords)}): {', '.join(missing_keywords) if missing_keywords else 'None'}"
    )

    lines.append("\n" + "-" * 60)
    lines.append("ATS SCORE")
    lines.append("-" * 60)
    lines.append(f"Overall Score: {ats_score}% (0-100)")
    lines.append(f"  Skills: {round(skill_score*100, 1)}%")
    lines.append(f"  Keywords: {round(kw_score*100, 1)}%")

    # Recommendations
    lines.append("\n" + "-" * 60)
    lines.append("RECOMMENDATIONS")
    lines.append("-" * 60)
    if missing_skills:
        lines.append(
            f"1. Add these missing skills to your resume: {', '.join(missing_skills)}"
        )
    if missing_keywords:
        lines.append(f"2. Incorporate keywords: {', '.join(missing_keywords[:5])}")
    if ats_score < 50:
        lines.append("3. ⚠️ Low ATS score — significant resume revision needed.")
    elif ats_score < 80:
        lines.append("3. ⚠️ Moderate ATS score — add more targeted skills.")
    else:
        lines.append("3. ✅ Strong alignment with role requirements.")

    # Resume length heuristic
    word_count = len(resume_text.split())
    lines.append(f"\nResume length: {word_count} words")
    if word_count < 200:
        lines.append("   ⚠️ Resume may be too short (aim for 300-500 words).")
    elif word_count > 700:
        lines.append("   ⚠️ Resume may be too long (aim for 300-500 words).")

    # Check for common sections
    lines.append("\nSection presence check:")
    sections = ["experience", "education", "skills", "projects", "summary"]
    for sec in sections:
        found = bool(re.search(rf"\b{sec}\b", resume_lower))
        status = "✅" if found else "⚠️"
        lines.append(f"  {status} {sec.title()}")

    report = "\n".join(lines)

    # Generate skill gap chart
    chart_path = None
    if HAS_MATPLOTLIB and (required_skills or keywords):
        chart_path = create_skill_chart(
            matched_skills, missing_skills, present_keywords, missing_keywords
        )

    return report, chart_path


def create_skill_chart(
    matched: List[str], missing: List[str], present_kw: List[str], missing_kw: List[str]
) -> Optional[str]:
    """Create a horizontal bar chart showing skill/keyword match."""
    try:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))

        # Skills chart
        all_skills = matched + missing
        colors_skills = ["#4CAF50"] * len(matched) + ["#F44336"] * len(missing)
        axes[0].barh(
            range(len(all_skills)),
            [1] * len(all_skills),
            color=colors_skills,
            tick_label=all_skills,
            height=0.6,
        )
        axes[0].set_title("Skills: Matched vs Missing", fontweight="bold")
        axes[0].set_xlabel("Present")
        axes[0].set_yticks(range(len(all_skills)))
        axes[0].set_yticklabels(all_skills, fontsize=8)
        axes[0].invert_yaxis()
        # Legend
        from matplotlib.patches import Patch

        legend_elements = [
            Patch(facecolor="#4CAF50", label="Matched"),
            Patch(facecolor="#F44336", label="Missing"),
        ]
        axes[0].legend(handles=legend_elements, loc="lower right", fontsize=8)

        # Keywords chart
        all_kw = present_kw + missing_kw
        colors_kw = ["#2196F3"] * len(present_kw) + ["#FF9800"] * len(missing_kw)
        axes[1].barh(
            range(len(all_kw)),
            [1] * len(all_kw),
            color=colors_kw,
            tick_label=all_kw,
            height=0.6,
        )
        axes[1].set_title("Keywords: Present vs Missing", fontweight="bold")
        axes[1].set_xlabel("Present")
        axes[1].set_yticks(range(len(all_kw)))
        axes[1].set_yticklabels(all_kw, fontsize=8)
        axes[1].invert_yaxis()
        legend_elements_kw = [
            Patch(facecolor="#2196F3", label="Present"),
            Patch(facecolor="#FF9800", label="Missing"),
        ]
        axes[1].legend(handles=legend_elements_kw, loc="lower right", fontsize=8)

        plt.tight_layout()
        chart_path = os.path.join(OUTPUT_DIR_STR, "skill_gap_chart.png")
        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()
        return chart_path
    except Exception as e:
        print(f"Chart generation error: {e}")
        return None


# ─── Resume Optimization ───────────────────────────────────────────────


def get_optimization_suggestions(
    company_display: str, role: str
) -> Tuple[str, List[str]]:
    """
    Generate optimization suggestions for optimizing a resume for a company/role.
    Returns (suggestion_summary, project_reorder_suggestions).
    """
    # Load company profile
    matched_key = resolve_company_key(company_display)

    if not matched_key:
        return "Company not found.", []

    try:
        company = load_company_profile(matched_key)
    except FileNotFoundError:
        return f"Company profile not found: {company_display}", []

    if role not in company.get("job_roles", {}):
        available = list(company.get("job_roles", {}).keys())
        return f"Role not found. Available: {available}", []

    role_cfg = company["job_roles"][role]
    keywords = role_cfg.get("keywords", [])
    resume_type = role_cfg.get("resume_type", "analytics")
    emphasize_metrics = role_cfg.get("emphasize_metrics", [])

    # Load profile projects
    profile = load_profile()
    projects_dir = str(DATA_DIR / "projects")
    all_projects = []
    for fname in os.listdir(projects_dir):
        if fname.endswith(".json"):
            all_projects.append(json.load(open(os.path.join(projects_dir, fname))))

    # Rank projects by keyword relevance
    keyword_weights = {kw: 5 for kw in keywords}
    ranked = rank_projects(all_projects, keyword_weights)

    # Build suggestions
    suggestions = []
    suggestions.append("=" * 60)
    suggestions.append("RESUME OPTIMIZATION SUGGESTIONS")
    suggestions.append("=" * 60)
    suggestions.append(f"\nCompany: {company['name']}")
    suggestions.append(f"Role: {role}")
    suggestions.append(f"Resume Type: {resume_type}")

    suggestions.append("\n--- TOP PROJECTS TO EMPHASIZE ---")
    for i, proj in enumerate(ranked[:5]):
        suggestions.append(f"{i+1}. {proj['name']}")
        # Check which metrics are relevant
        metrics = proj.get("metrics", {}).get(resume_type, [])
        if metrics:
            suggestions.append(f"   → Emphasize: {metrics[0]}")

    suggestions.append("\n--- KEYWORDS TO INCLUDE ---")
    suggestions.append(f"Primary keywords: {', '.join(keywords[:5])}")
    if emphasize_metrics:
        suggestions.append(f"Metrics to highlight: {', '.join(emphasize_metrics)}")

    # Skill section optimization
    suggestions.append("\n--- SKILLS SECTION TIPS ---")
    suggestions.append(
        f"Ensure your skills section includes: {', '.join(role_cfg.get('required_skills', [])[:8])}"
    )

    # Project reorder suggestions
    project_order = [p["name"] for p in ranked[:4]]
    summary = "\n".join(suggestions)

    return summary, project_order


def _validate_all_profiles() -> str:
    """Validate all saved company profiles and return a report."""
    if not os.path.exists(COMPANY_DIR):
        return "No companies directory found."
    results = []
    for fname in sorted(os.listdir(COMPANY_DIR)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(COMPANY_DIR, fname)) as f:
                data = json.load(f)
            name = data.get("name", fname.replace(".json", ""))
            roles = data.get("job_roles", {})
            if not roles:
                results.append(f"⚠️ {name}: no roles defined")
            for role, cfg in roles.items():
                issues = []
                if not cfg.get("resume_type"):
                    issues.append("missing resume_type")
                if not cfg.get("required_skills"):
                    issues.append("missing required_skills")
                if issues:
                    results.append(f"⚠️ {name} / {role}: {', '.join(issues)}")
                else:
                    results.append(f"✅ {name} / {role}: OK")
        except Exception as e:
            results.append(f"❌ {fname}: {str(e)}")
    return "\n".join(results) if results else "All profiles valid."


def _safe_list_all_companies() -> str:
    """Wrapper for list_all_companies that never crashes."""
    try:
        return list_all_companies()
    except Exception as e:
        return f"Error listing companies: {str(e)}"


# ─── Gradio Interface ───────────────────────────────────────────────────

with gr.Blocks(title="Resume Builder Pro") as demo:
    gr.Markdown("# 🚀 Resume Builder Pro")
    gr.Markdown(
        "**Generate tailored, ATS-optimized resumes — analyze, compare, and track every application.**\n\n"
        "Pick a company and role, generate a LaTeX resume from your project portfolio, measure its ATS score "
        "against the job, import job descriptions to extract keywords, enhance weak bullets, and log each "
        "application in the tracker."
    )

    with gr.Tabs():
        # ── Tab 1: Add/Edit Company ──────────────────────
        with gr.Tab("➕ Add/Edit Company"):
            gr.Markdown("### Add a new company profile with job roles")
            with gr.Row():
                with gr.Column(scale=1):
                    company_name = gr.Textbox(
                        label="Company Name", placeholder="e.g. Fractal Analytics"
                    )
                    company_website = gr.Textbox(
                        label="Company Website (optional)",
                        placeholder="https://fractal.ai",
                    )
                    role_name = gr.Textbox(
                        label="Job Role",
                        placeholder="e.g. Decision Analytics Associate",
                    )
                    resume_type = gr.Dropdown(
                        choices=RESUME_TYPES, label="Resume Type", value="analytics"
                    )
                with gr.Column(scale=1):
                    required_skills = gr.Textbox(
                        label="Required Skills (comma-separated)",
                        placeholder="e.g. Python, statistical modeling, data analysis",
                    )
                    keywords = gr.Textbox(
                        label="Role Keywords (comma-separated)",
                        placeholder="e.g. analytics, modeling, stakeholder presentation",
                    )
                    emphasize_metrics = gr.Textbox(
                        label="Emphasize Metrics (comma-separated)",
                        placeholder="e.g. 38,500+ trades labeled, ₹93k profit",
                    )

            save_btn = gr.Button("💾 Save Company Profile", variant="primary")
            save_output = gr.Textbox(label="Status", interactive=False)
            save_btn.click(
                fn=save_company,
                inputs=[
                    company_name,
                    company_website,
                    role_name,
                    resume_type,
                    required_skills,
                    keywords,
                    emphasize_metrics,
                ],
                outputs=save_output,
            )

        # ── Tab 2: Import JD ────────────────────────────
        with gr.Tab("📥 Import JD"):
            gr.Markdown(
                "### Import a job description to auto-extract skills & keywords"
            )
            gr.Markdown(
                "Paste the job description **text** or a **URL**. NLP will extract required skills, keywords, and metrics you can save into a company profile."
            )
            with gr.Row():
                jd_text_input = gr.Textbox(
                    label="Job Description",
                    lines=15,
                    placeholder="Paste the full job description here...",
                )
                with gr.Column():
                    jd_url_input = gr.Textbox(
                        label="Or Job Description URL", placeholder="https://..."
                    )
                    extract_btn = gr.Button(
                        "🔍 Extract Skills & Keywords", variant="primary"
                    )
            jd_result_state = gr.State(value=None)
            jd_output = gr.Textbox(
                label="Extracted Results", lines=15, interactive=False
            )

            gr.Markdown("### Save Extracted Data to a Company Profile")
            with gr.Row():
                save_company_name = gr.Textbox(
                    label="Company Name", placeholder="e.g. Acme Corp"
                )
                save_role_name = gr.Textbox(
                    label="Role Name", placeholder="e.g. Data Engineer"
                )
            save_jd_btn = gr.Button("💾 Save to Profile", variant="secondary")
            save_jd_status = gr.Textbox(label="Save Status", interactive=False)

            if HAS_JD_IMPORTER:

                def jd_extract_wrapper(text, url):
                    try:
                        if url and url.strip():
                            if not extract_from_jd_url:
                                return (
                                    "Error: requests/beautifulsoup4 not installed. pip install requests beautifulsoup4",
                                    None,
                                )
                            result = extract_from_jd_url(url.strip())
                        elif text and text.strip():
                            result = extract_from_jd_text(text)
                        else:
                            return "Please provide job description text or a URL.", None
                        return format_jd_result(result), result
                    except Exception as e:
                        return f"Extraction error: {str(e)}", None

                def save_jd_result(jd_result, company_name, role_name):
                    if jd_result is None:
                        return "No extraction result to save. Run extraction first."
                    if not company_name or not role_name:
                        return "Company name and role name are required."
                    return save_company(
                        company_name,
                        "",
                        role_name,
                        jd_result.get("resume_type", "analytics"),
                        ", ".join(jd_result.get("required_skills", [])),
                        ", ".join(jd_result.get("keywords", [])),
                        ", ".join(jd_result.get("emphasize_metrics", [])),
                    )

                extract_btn.click(
                    fn=jd_extract_wrapper,
                    inputs=[jd_text_input, jd_url_input],
                    outputs=[jd_output, jd_result_state],
                )

                save_jd_btn.click(
                    fn=save_jd_result,
                    inputs=[jd_result_state, save_company_name, save_role_name],
                    outputs=save_jd_status,
                )

                # ── Tier B: JD Library + auto-propose ────────────
                gr.Markdown("### JD Library & Auto-Propose (Tier B)")
                with gr.Row():
                    jd_lib_btn = gr.Button("📦 Save to JD Library", variant="secondary")
                    jd_propose_btn = gr.Button(
                        "📝 Propose Company Profile", variant="secondary"
                    )
                jd_propose_preview = gr.Textbox(
                    label="Proposed Profile (JSON preview)",
                    lines=10,
                    interactive=False,
                )
                jd_lib_status = gr.Textbox(label="JD Library Status", interactive=False)
                jd_propose_save_btn = gr.Button("💾 Save Proposed Profile")
                jd_propose_save_status = gr.Textbox(
                    label="Save Proposed Status", interactive=False
                )

                def jd_library_save(text, url, jd_result):
                    raw = url.strip() if (url or "").strip() else (text or "")
                    if not raw.strip():
                        return "Provide JD text or a URL before saving to the library."
                    if jd_result is None:
                        return "No extraction to save. Run extraction first."
                    store = get_jd_store()
                    slug = store.save_jd(
                        company="", role="", raw_text=raw, extraction=jd_result
                    )
                    return f"Saved JD → {slug}. Total in library: {store.count()}"

                def jd_propose(company, role, jd_result):
                    if jd_result is None:
                        return "Run extraction first."
                    from resume_builder import propose_company_profile

                    profile = propose_company_profile(
                        company or "New Company", role or "Role", jd_result
                    )
                    return json.dumps(profile, ensure_ascii=False, indent=2)

                def jd_propose_save(company, role, jd_result):
                    if jd_result is None:
                        return "Run extraction first."
                    from resume_builder import (
                        propose_company_profile,
                        save_company_profile,
                    )

                    profile = propose_company_profile(
                        company or "New Company", role or "Role", jd_result
                    )
                    path = save_company_profile(profile)
                    store = get_jd_store()
                    store.save_jd(
                        company or "New Company",
                        role or "Role",
                        "",
                        jd_result,
                    )
                    return f"Saved profile → {path}"

                jd_lib_btn.click(
                    fn=jd_library_save,
                    inputs=[jd_text_input, jd_url_input, jd_result_state],
                    outputs=jd_lib_status,
                )
                jd_propose_btn.click(
                    fn=jd_propose,
                    inputs=[save_company_name, save_role_name, jd_result_state],
                    outputs=jd_propose_preview,
                )
                jd_propose_save_btn.click(
                    fn=jd_propose_save,
                    inputs=[save_company_name, save_role_name, jd_result_state],
                    outputs=jd_propose_save_status,
                )

            else:
                jd_output.value = "JD Importer unavailable. Install dependencies: pip install spacy requests beautifulsoup4 rake-nltk"

        # ── Tab 3: Generate Resume ────────────────────────
        with gr.Tab("📄 Generate Resume"):
            gr.Markdown("### Generate a tailored resume")
            with gr.Row():
                company_dropdown = gr.Dropdown(
                    choices=get_company_names(),
                    label="Company",
                    value=get_company_names()[0] if get_company_names() else "",
                )
                role_value = (
                    get_company_roles(get_company_names()[0])
                    if get_company_names()
                    else []
                )
                role_input = gr.Dropdown(
                    choices=role_value,
                    value=role_value[0] if role_value else "",
                    label="Job Profile",
                )
                custom_role = gr.Textbox(
                    label="Custom role (optional)",
                    placeholder="Override role (optional)",
                    interactive=True,
                )

            with gr.Row():
                template_selector = gr.Dropdown(
                    choices=TEMPLATE_TYPES, label="Resume Template", value="default"
                )

            company_dropdown.change(
                fn=_role_update,
                inputs=company_dropdown,
                outputs=role_input,
            )

            gen_btn = gr.Button("🚀 Generate Resume", variant="primary")
            with gr.Row():
                tex_display = gr.Textbox(
                    label=".tex Source", lines=20, interactive=False
                )
                status_output = gr.Textbox(label="Status", interactive=False)

            pdf_file = gr.File(label="📥 Download PDF", visible=False)
            tex_file = gr.File(label="📥 Download .tex", visible=False)

            def gen_wrapper(company_disp, role, custom_role, template_type):
                effective_role = (custom_role or "").strip() or role or ""
                tex_content, pdf_path, status = generate_resume_wrapper(
                    company_disp, effective_role, template_type
                )
                outputs = [
                    gr.update(value=tex_content or "No output"),
                    gr.update(value=status),
                ]
                safe_company = slugify(company_disp)
                safe_role = slugify(effective_role)
                tex_path = os.path.join(
                    OUTPUT_DIR_STR, f"resume_{safe_company}_{safe_role}.tex"
                )

                if pdf_path and os.path.exists(pdf_path):
                    outputs.append(gr.update(value=pdf_path, visible=True))
                else:
                    outputs.append(gr.update(visible=False))

                if os.path.exists(tex_path):
                    outputs.append(gr.update(value=tex_path, visible=True))
                else:
                    outputs.append(gr.update(visible=False))

                return outputs

            gen_btn.click(
                fn=gen_wrapper,
                inputs=[company_dropdown, role_input, custom_role, template_selector],
                outputs=[tex_display, status_output, pdf_file, tex_file],
            )

            refresh_btn = gr.Button("🔄 Refresh Company List")
            refresh_btn.click(
                fn=lambda: gr.update(choices=get_company_names()),
                inputs=None,
                outputs=company_dropdown,
            )

        # ── Tab 3: Analyze Resume ──────────────────────────
        with gr.Tab("🔍 Analyze Resume"):
            gr.Markdown(
                "### Upload a PDF resume to analyze skill/keyword match against a company"
            )
            with gr.Row():
                pdf_input = gr.File(
                    label="📄 Upload PDF Resume",
                    file_count="single",
                    file_types=[".pdf"],
                )
                with gr.Column():
                    analyze_company = gr.Dropdown(
                        choices=get_company_names(),
                        label="Company",
                        value=get_company_names()[0] if get_company_names() else "",
                    )
                    analyze_role_choices = (
                        get_company_roles(get_company_names()[0])
                        if get_company_names()
                        else []
                    )
                    analyze_role = gr.Dropdown(
                        choices=analyze_role_choices,
                        value=analyze_role_choices[0] if analyze_role_choices else "",
                        label="Job Profile",
                    )
                    analyze_custom_role = gr.Textbox(
                        label="Custom role (optional)",
                        placeholder="Override role (optional)",
                    )

            analyze_company.change(
                fn=_role_update,
                inputs=analyze_company,
                outputs=analyze_role,
            )

            analyze_btn = gr.Button("📊 Run Analysis", variant="primary")
            analysis_output = gr.Textbox(
                label="Analysis Report", lines=30, interactive=False
            )
            chart_output = gr.Image(label="Skill Gap Chart", visible=False)

            def analyze_wrapper(pdf_file, company_disp, role, custom_role):
                if pdf_file is None:
                    return gr.update(value="Please upload a PDF resume."), gr.update(
                        visible=False
                    )
                effective_role = (custom_role or "").strip() or role or ""
                report, chart_path = analyze_resume_skills(
                    pdf_file, company_disp, effective_role
                )
                chart_update = (
                    gr.update(value=chart_path, visible=chart_path is not None)
                    if chart_path
                    else gr.update(visible=False)
                )
                return gr.update(value=report), chart_update

            analyze_btn.click(
                fn=analyze_wrapper,
                inputs=[pdf_input, analyze_company, analyze_role, analyze_custom_role],
                outputs=[analysis_output, chart_output],
            )

            gr.Markdown("### 🔍 ATS Parse Preview (simulated)")
            gr.Markdown(
                "See what an ATS parser would extract from the uploaded PDF — contact info, sections, skills, metrics, and length."
            )

            def parse_preview_wrapper(pdf_file):
                if pdf_file is None:
                    return "Please upload a PDF resume.", gr.update(visible=False)
                text = extract_text_from_pdf(pdf_file)
                if not text or not text.strip():
                    return (
                        "Could not extract text from this PDF. Is it a scanned/image PDF?",
                        gr.update(visible=False),
                    )
                result = parse_resume_for_ats(text)
                return format_parse_preview(result), gr.update(visible=True)

            with gr.Row():
                preview_btn = gr.Button("🧩 Run ATS Parse Preview", variant="secondary")
                preview_output = gr.Textbox(
                    label="ATS Parse Preview", lines=28, interactive=False
                )

            preview_btn.click(
                fn=parse_preview_wrapper, inputs=[pdf_input], outputs=preview_output
            )

            refresh_analyze_btn = gr.Button("🔄 Refresh Company List")
            refresh_analyze_btn.click(
                fn=lambda: gr.update(choices=get_company_names()),
                inputs=None,
                outputs=analyze_company,
            )

        # ── Tab 4: Optimize Resume ────────────────────────
        with gr.Tab("⚡ Optimize Resume"):
            gr.Markdown(
                "### Get suggestions to optimize your resume for a specific company"
            )
            with gr.Row():
                opt_company = gr.Dropdown(
                    choices=get_company_names(),
                    label="Company",
                    value=get_company_names()[0] if get_company_names() else "",
                )
                opt_role_choices = (
                    get_company_roles(get_company_names()[0])
                    if get_company_names()
                    else []
                )
                opt_role = gr.Dropdown(
                    choices=opt_role_choices,
                    value=opt_role_choices[0] if opt_role_choices else "",
                    label="Job Profile",
                )
                opt_custom_role = gr.Textbox(
                    label="Custom role (optional)",
                    placeholder="Override role (optional)",
                )

            opt_company.change(
                fn=_role_update,
                inputs=opt_company,
                outputs=opt_role,
            )

            opt_btn = gr.Button("💡 Get Suggestions", variant="primary")
            suggestions_output = gr.Textbox(
                label="Optimization Suggestions", lines=25, interactive=False
            )
            project_order_output = gr.Textbox(
                label="Recommended Project Order", interactive=False
            )

            def opt_wrapper(company_disp, role, custom_role):
                effective_role = (custom_role or "").strip() or role or ""
                suggestions, project_order = get_optimization_suggestions(
                    company_disp, effective_role
                )
                return gr.update(value=suggestions), gr.update(
                    value=(
                        ", ".join(project_order) if project_order else "No suggestions"
                    )
                )

            opt_btn.click(
                fn=opt_wrapper,
                inputs=[opt_company, opt_role, opt_custom_role],
                outputs=[suggestions_output, project_order_output],
            )

            refresh_opt_btn = gr.Button("🔄 Refresh Company List")
            refresh_opt_btn.click(
                fn=lambda: gr.update(choices=get_company_names()),
                inputs=None,
                outputs=opt_company,
            )

        # ── Tab: Compare Companies ───────────────────────
        with gr.Tab("⚖️ Compare Companies"):
            gr.Markdown("### Compare the same resume against multiple companies")
            gr.Markdown(
                "Upload one resume and see an ATS score for every saved company (first role per company by default)."
            )

            def _company_choice_items():
                items = []
                for slug in list_company_slugs():
                    try:
                        from resume_builder import load_company_profile

                        display = load_company_profile(slug).get("name", slug)
                    except Exception:
                        display = slug
                    items.append((f"{display} ({slug})", slug))
                return items

            _COMPARE_CHOICES = _company_choice_items()
            _COMPARE_SLUGS = [slug for _, slug in _COMPARE_CHOICES]

            with gr.Row():
                cmp_pdf = gr.File(
                    label="📄 Upload PDF Resume",
                    file_count="single",
                    file_types=[".pdf"],
                )
                cmp_company_group = gr.CheckboxGroup(
                    choices=_COMPARE_CHOICES,
                    label="Companies to compare (empty = all)",
                    value=_COMPARE_SLUGS,
                )
                cmp_role_override = gr.Textbox(
                    label="Role (optional; empty = each company's first role)"
                )

            cmp_btn = gr.Button("🏁 Run Comparison", variant="primary")
            cmp_status = gr.Textbox(label="Status", interactive=False)
            cmp_table = gr.Dataframe(
                headers=[
                    "Company",
                    "Role",
                    "ATS Score",
                    "Rules Passed",
                    "Top Suggestions",
                ],
                datatype=["str", "str", "str", "str", "str"],
                interactive=False,
                label="ATS Score Comparison",
            )
            cmp_chart = gr.Image(label="Comparison Chart", visible=False)

            def _compare_wrapper(pdf_file, slugs, role_override):
                if pdf_file is None:
                    return "Please upload a PDF resume.", [], gr.update(visible=False)
                text = extract_text_from_pdf(pdf_file)
                if not text or not text.strip():
                    return (
                        "Could not extract text from this PDF.",
                        [],
                        gr.update(visible=False),
                    )

                selected = list(slugs) if slugs else None
                roles = {}
                if role_override and role_override.strip():
                    roles = {
                        s: role_override.strip()
                        for s in (selected or list_company_slugs())
                    }

                results = compare_resume(text, companies=selected, roles=roles)
                if not results:
                    return (
                        "No company profiles found to compare.",
                        [],
                        gr.update(visible=False),
                    )
                headers, rows = comparison_header(results)
                chart = create_comparison_chart(results)
                summary = f"Compared {len(results)} company/role combo(s). "
                summary += (
                    "Top match: "
                    + results[0]["company"]
                    + " ("
                    + str(results[0]["ats_score"])
                    + "%)"
                )
                chart_update = (
                    gr.update(value=chart, visible=chart is not None)
                    if chart
                    else gr.update(visible=False)
                )
                return summary, rows, chart_update

            cmp_btn.click(
                fn=_compare_wrapper,
                inputs=[cmp_pdf, cmp_company_group, cmp_role_override],
                outputs=[cmp_status, cmp_table, cmp_chart],
            )

        # ── Tab: Enhance Bullets ─────────────────────────
        with gr.Tab("✨ Enhance Bullets"):
            gr.Markdown(
                "### Turn weak resume bullets into strong, metric-driven achievements"
            )
            gr.Markdown(
                "Paste one bullet per line. Weak bullets are auto-detected and rewritten. If a local **Ollama** server is available it is used; otherwise a built-in rule-based enhancer applies (never errors)."
            )

            with gr.Row():
                enh_input = gr.Textbox(
                    label="Bullets (one per line)",
                    lines=12,
                    placeholder="Responsible for sales\nWorked on the A/B testing pipeline\nImproved model accuracy by 15%",
                )
                enh_output = gr.Textbox(
                    label="Enhanced Bullets", lines=16, interactive=False
                )

            with gr.Row():
                enh_use_llm = gr.Checkbox(label="Try Ollama LLM first", value=True)
                enh_model = gr.Dropdown(
                    choices=["gemma2:2b", "llama3.2", "gemma2:9b", "llama3.1:8b"],
                    value="gemma2:2b",
                    label="Ollama Model",
                )
                enh_btn = gr.Button("🚀 Enhance Bullets", variant="primary")

            enh_summary = gr.Textbox(label="Summary", interactive=False)
            enh_copy = gr.Textbox(
                label="Enhanced Bullets (copy-friendly)", lines=10, interactive=True
            )

            def _enhance_wrapper(bullets_text, use_llm, model):
                if not bullets_text or not bullets_text.strip():
                    return "Please paste at least one bullet.", "", ""
                bullets = [b.strip() for b in bullets_text.splitlines() if b.strip()]
                payload = enhance_bullets(bullets, use_llm=bool(use_llm), model=model)
                report = format_enhancement_report(payload)
                copy = "\n".join(r["improved"] for r in payload["results"])
                return report, copy, payload["summary"]

            enh_btn.click(
                fn=_enhance_wrapper,
                inputs=[enh_input, enh_use_llm, enh_model],
                outputs=[enh_output, enh_copy, enh_summary],
            )

        # ── Tab 6: .tex Editor ───────────────────────────
        with gr.Tab("✏️ .tex Editor"):
            gr.Markdown("### Edit LaTeX source and compile to PDF")
            gr.Markdown(
                "Write or paste LaTeX source. Click **Compile** to build a PDF, or **Load** an existing .tex / **Save** your work."
            )

            def _list_tex_files():
                if not os.path.exists(OUTPUT_DIR_STR):
                    return []
                tex_files = [
                    f for f in os.listdir(OUTPUT_DIR_STR) if f.endswith(".tex")
                ]
                return sorted(tex_files)

            with gr.Row():
                tex_file_selector = gr.Dropdown(
                    choices=_list_tex_files(),
                    label="Select .tex file",
                    value=_list_tex_files()[0] if _list_tex_files() else "",
                )

            tex_editor = gr.Code(
                label="LaTeX Source",
                language="latex",
                lines=30,
                value="% Paste or load LaTeX source here, then click Compile",
            )

            with gr.Row():
                load_tex_btn = gr.Button("📂 Load Selected", variant="secondary")
                save_tex_btn = gr.Button("💾 Save As", variant="secondary")
                compile_tex_btn = gr.Button("🚀 Compile to PDF", variant="primary")
            tex_editor_status = gr.Textbox(label="Status", interactive=False)
            tex_editor_pdf = gr.File(label="📥 Generated PDF", visible=False)

            def load_tex_wrapper(filename):
                if not filename:
                    return "Please select a .tex file to load.", gr.update(
                        visible=False
                    )
                path = os.path.join(OUTPUT_DIR_STR, filename)
                if not os.path.exists(path):
                    return f"File not found: {filename}", gr.update(visible=False)
                with open(path, "r") as f:
                    content = f.read()
                return content, gr.update(visible=False)

            def save_tex_wrapper(content, name):
                if not content:
                    return "Editor is empty - nothing to save.", gr.update(
                        visible=False
                    )
                if not name:
                    return "Please provide a filename.", gr.update(visible=False)
                fname = name if name.endswith(".tex") else name + ".tex"
                os.makedirs(OUTPUT_DIR_STR, exist_ok=True)
                path = os.path.join(OUTPUT_DIR_STR, fname)
                with open(path, "w") as f:
                    f.write(content)
                return f"Saved: {path}", gr.update(visible=False)

            def compile_tex_wrapper(content):
                if not content or not content.strip():
                    return "Editor is empty - nothing to compile.", gr.update(
                        visible=False
                    )
                safe_name = "resume_editor_custom"
                tex_path = os.path.join(OUTPUT_DIR_STR, f"{safe_name}.tex")
                os.makedirs(OUTPUT_DIR_STR, exist_ok=True)
                with open(tex_path, "w") as f:
                    f.write(content)
                try:
                    result = subprocess.run(
                        ["tectonic", "--outdir", OUTPUT_DIR_STR, tex_path],
                        capture_output=True,
                        text=True,
                        cwd=BASE_DIR,
                    )
                except Exception as e:
                    return f"Compile error: {str(e)}", gr.update(visible=False)

                pdf_path = os.path.join(OUTPUT_DIR_STR, f"{safe_name}.pdf")
                if result.returncode == 0 and os.path.exists(pdf_path):
                    return f"PDF generated: {pdf_path}", gr.update(
                        value=pdf_path, visible=True
                    )
                return f"Compilation issue: {result.stderr[:500]}", gr.update(
                    visible=False
                )

            load_tex_btn.click(
                fn=load_tex_wrapper,
                inputs=[tex_file_selector],
                outputs=[tex_editor, tex_editor_pdf],
            )
            save_tex_btn.click(
                fn=save_tex_wrapper,
                inputs=[tex_editor, tex_file_selector],
                outputs=[tex_editor_status, tex_editor_pdf],
            )
            compile_tex_btn.click(
                fn=compile_tex_wrapper,
                inputs=[tex_editor],
                outputs=[tex_editor_status, tex_editor_pdf],
            )

        # ── Tab: Job Tracker ────────────────────────────
        with gr.Tab("📌 Job Tracker"):
            gr.Markdown("### Track job applications, interview status, and ATS scores")

            def _applications_df(status):
                apps = _tracker.list_applications(status_filter=status)
                headers, rows = _tracker.to_dataframe_rows(apps)
                return rows, f"Showing {len(apps)} application(s)"

            def _counts_str():
                counts = _tracker.get_status_counts()
                if not counts:
                    return "No applications yet."
                return " | ".join(f"{k}: {v}" for k, v in counts.items())

            with gr.Group():
                with gr.Row():
                    trk_company = gr.Textbox(
                        label="Company", placeholder="e.g. Zerodha"
                    )
                    trk_role = gr.Textbox(
                        label="Role", placeholder="e.g. Quant Developer"
                    )
                with gr.Row():
                    trk_status = gr.Dropdown(
                        choices=APPLICATION_STATUSES, label="Status", value="Applied"
                    )
                    trk_score = gr.Number(label="ATS Score (optional)", value=None)
                    trk_date = gr.Textbox(
                        label="Applied Date (YYYY-MM-DD, empty = today)"
                    )
                trk_notes = gr.Textbox(label="Notes", lines=2)
                trk_add_btn = gr.Button("➕ Add Application", variant="primary")
                trk_add_out = gr.Textbox(label="Status", interactive=False)

            def _add_application(company, role, status, score, date_val, notes):
                try:
                    aid = _tracker.add_application(
                        company=company.strip(),
                        role=role.strip(),
                        status=status,
                        ats_score=score if score is not None else None,
                        applied_date=date_val.strip() if date_val.strip() else None,
                        notes=notes.strip(),
                    )
                    return f"Added application #{aid} for {company} ({role})"
                except Exception as e:
                    return f"Error: {str(e)}"

            trk_add_btn.click(
                fn=_add_application,
                inputs=[
                    trk_company,
                    trk_role,
                    trk_status,
                    trk_score,
                    trk_date,
                    trk_notes,
                ],
                outputs=trk_add_out,
            )

            with gr.Row():
                trk_filter = gr.Dropdown(
                    choices=["All"] + APPLICATION_STATUSES,
                    value="All",
                    label="Filter By Status",
                )
                trk_counts = gr.Textbox(
                    label="Status Counts", value=_counts_str(), interactive=False
                )
                trk_refresh_btn = gr.Button("🔄 Refresh Table")

            trk_table = gr.Dataframe(
                headers=["ID", "Company", "Role", "Applied", "Status", "ATS", "Notes"],
                datatype=["number", "str", "str", "str", "str", "number", "str"],
                interactive=False,
                label="Applications",
            )
            trk_summary = gr.Textbox(label="Summary", interactive=False)

            def _refresh_display(status):
                rows, summary = _applications_df(status)
                return rows, summary, _counts_str()

            trk_filter.change(
                fn=_applications_df,
                inputs=[trk_filter],
                outputs=[trk_table, trk_summary],
            )
            trk_refresh_btn.click(
                fn=_refresh_display,
                inputs=[trk_filter],
                outputs=[trk_table, trk_summary, trk_counts],
            )

            gr.Markdown("---")
            gr.Markdown("### Update Status / Delete")
            with gr.Row():
                trk_update_id = gr.Number(
                    label="Application ID", value=None, precision=0
                )
                trk_update_status = gr.Dropdown(
                    choices=APPLICATION_STATUSES, value="Applied", label="New Status"
                )
                trk_update_btn = gr.Button("🔄 Update Status")
            trk_update_out = gr.Textbox(label="Update/Delete Status", interactive=False)

            def _update_status(aid, status):
                if aid is None:
                    return "Please provide an Application ID."
                try:
                    _tracker.update_status(int(aid), status=status)
                    return f"Updated application {int(aid)} → {status}"
                except Exception as e:
                    return f"Error: {str(e)}"

            def _delete_app(app_id):
                if app_id is None:
                    return "Please provide an Application ID."
                try:
                    _tracker.delete_application(int(app_id))
                    return f"Deleted application #{int(app_id)}"
                except Exception as e:
                    return f"Error: {str(e)}"

            with gr.Row():
                trk_delete_id = gr.Number(
                    label="Application ID to Delete", value=None, precision=0
                )
                trk_delete_btn = gr.Button("🗑️ Delete Application", variant="danger")

            trk_update_btn.click(
                fn=_update_status,
                inputs=[trk_update_id, trk_update_status],
                outputs=trk_update_out,
            )
            trk_delete_btn.click(
                fn=_delete_app, inputs=[trk_delete_id], outputs=trk_update_out
            )

            gr.Markdown("---")
            gr.Markdown("### Insights (Tier B)")
            insights_btn = gr.Button("📊 Show Insights", variant="primary")
            insights_text = gr.Textbox(label="Insights", lines=8, interactive=False)
            insights_chart = gr.Image(label="Avg ATS by Status", interactive=False)
            jd_library_info = gr.Textbox(
                label="JD Library",
                value=f"Saved JDs: {get_jd_store().count()}",
                interactive=False,
            )

            def _show_insights():
                ins = _tracker.analyze_insights()
                return (
                    format_insights(ins),
                    ins.get("chart_path") or None,
                    f"Saved JDs: {get_jd_store().count()}",
                )

            insights_btn.click(
                fn=_show_insights,
                inputs=[],
                outputs=[insights_text, insights_chart, jd_library_info],
            )

        # ── Tab 5: Manage Companies ───────────────────────
        with gr.Tab("📋 Manage Companies"):
            gr.Markdown("### Saved Company Profiles")
            refresh_list_btn = gr.Button("🔄 Refresh List")
            company_list_display = gr.Textbox(
                label="Companies",
                value=_safe_list_all_companies(),
                lines=25,
                interactive=False,
            )
            refresh_list_btn.click(
                fn=list_all_companies, inputs=None, outputs=company_list_display
            )

            with gr.Row():
                delete_input = gr.Textbox(label="Delete Company (by name)")
                delete_btn = gr.Button("🗑️ Delete Company", variant="danger")
                delete_status = gr.Textbox(label="Delete Status")
                delete_btn.click(
                    fn=delete_company, inputs=delete_input, outputs=delete_status
                )

            validate_all_btn = gr.Button(
                "✅ Validate All Profiles", variant="secondary"
            )
            validate_all_out = gr.Textbox(
                label="Validation Results", lines=10, interactive=False
            )

            validate_all_btn.click(
                fn=_validate_all_profiles, inputs=None, outputs=validate_all_out
            )

        # ── Tab: Placement Projects ──────────────────
        with gr.Tab("🏢 Placement Projects"):
            gr.Markdown("### Placement & Projects — Tesla, GEP, Tredence, ZS")
            gr.Markdown(
                "Browse all placement company projects. Select a company to see its projects, then generate a tailored resume."
            )

            placement_company = gr.Dropdown(
                choices=get_placement_companies(),
                label="Placement Company",
                value=get_placement_companies()[0] if get_placement_companies() else "",
            )
            placement_projects_display = gr.Textbox(
                label="Projects for Selected Company",
                lines=25,
                interactive=False,
            )
            placement_role = gr.Dropdown(
                choices=[],
                label="Job Role (for resume generation)",
            )
            placement_template = gr.Dropdown(
                choices=TEMPLATE_TYPES,
                label="Resume Template",
                value="default",
            )

            def _placement_projects(company_name):
                projects = get_placement_projects_by_company(company_name)
                if not projects:
                    return "No projects found for this company."
                lines = []
                for p in projects:
                    lines.append(f"📌 {p.get('name', 'Untitled')}")
                    lines.append(
                        f"   Tech: {', '.join(p.get('technologies', p.get('tags', [])))}"
                    )
                    lines.append(f"   {p.get('short_description', '')[:200]}")
                    lines.append("")
                return "\n".join(lines)

            def _placement_roles(company_name):
                try:
                    from resume_builder import load_company_profile

                    profile = load_company_profile(company_name)
                except Exception:
                    return gr.update(choices=[], value="")
                roles = list(profile.get("job_roles", {}).keys())
                return gr.update(choices=roles, value=roles[0] if roles else "")

            placement_company.change(
                fn=_placement_projects,
                inputs=placement_company,
                outputs=placement_projects_display,
            )
            placement_company.change(
                fn=_placement_roles,
                inputs=placement_company,
                outputs=placement_role,
            )

            placement_gen_btn = gr.Button(
                "🚀 Generate Resume for Placement", variant="primary"
            )
            placement_tex = gr.Textbox(label=".tex Source", lines=15, interactive=False)
            placement_status = gr.Textbox(label="Status", interactive=False)
            placement_pdf = gr.File(label="📥 Download PDF", visible=False)
            placement_tex_file = gr.File(label="📥 Download .tex", visible=False)

            def _placement_generate(company, role, template_type):
                from resume_builder import build_resume as _build
                from resume_builder import slugify

                effective_role = (role or "").strip()
                if not effective_role:
                    return (
                        "",
                        "Please select a role.",
                        gr.update(visible=False),
                        gr.update(visible=False),
                    )
                try:
                    tex_content, pdf_path, status = _build(
                        company, effective_role, template_type=template_type
                    )
                except Exception as e:
                    return (
                        "",
                        f"Error: {str(e)}",
                        gr.update(visible=False),
                        gr.update(visible=False),
                    )

                safe_company = slugify(company)
                safe_role = slugify(effective_role)
                tex_path = os.path.join(
                    OUTPUT_DIR_STR,
                    f"resume_{safe_company}_{safe_role}.tex",
                )

                outputs = [
                    gr.update(value=tex_content or "No output"),
                    gr.update(value=status),
                ]
                if pdf_path and os.path.exists(pdf_path):
                    outputs.append(gr.update(value=pdf_path, visible=True))
                else:
                    outputs.append(gr.update(visible=False))
                if os.path.exists(tex_path):
                    outputs.append(gr.update(value=tex_path, visible=True))
                else:
                    outputs.append(gr.update(visible=False))
                return outputs

            placement_gen_btn.click(
                fn=_placement_generate,
                inputs=[placement_company, placement_role, placement_template],
                outputs=[
                    placement_tex,
                    placement_status,
                    placement_pdf,
                    placement_tex_file,
                ],
            )

    # ─── Section Management ──────────────────────────────────────────

    SECTIONS_DIR = os.path.join(DATA_DIR, "sections")

    def save_section_data(section_name, company_display, json_data):
        """Save section data to data/sections/<section_name>/<company>.json."""
        company_key = slugify(company_display)
        section_dir = os.path.join(SECTIONS_DIR, section_name)
        os.makedirs(section_dir, exist_ok=True)
        path = os.path.join(section_dir, f"{company_key}.json")
        try:
            data = json.loads(json_data)
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            return f"Saved {section_name} data for {company_display}"
        except json.JSONDecodeError as e:
            return f"JSON parse error: {e}"

    def load_section_data_for_ui(section_name, company_display):
        """Load section data for editing in a textbox."""
        company_key = slugify(company_display)
        path = os.path.join(SECTIONS_DIR, section_name, f"{company_key}.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.dumps(json.load(f), indent=2)
        # Return default empty structure
        if section_name == "coursework":
            return json.dumps({"items": []}, indent=2)
        elif section_name == "internship":
            return json.dumps({"items": []}, indent=2)
        return "{}"

    with gr.Tab("📝 Sections"):
        gr.Markdown("### Manage per-company section data (coursework, internship)")

        with gr.Row():
            sec_company = gr.Dropdown(
                choices=get_company_names(),
                label="Company",
                value=get_company_names()[0] if get_company_names() else "",
            )
            sec_section = gr.Dropdown(
                choices=["coursework", "internship"],
                label="Section",
                value="coursework",
            )

        sec_json = gr.Code(
            label="Section Data (JSON)",
            language="json",
            lines=20,
        )

        sec_load_btn = gr.Button("📂 Load", variant="secondary")
        sec_save_btn = gr.Button("💾 Save", variant="primary")
        sec_status = gr.Textbox(label="Status", interactive=False)

        def _sec_load(company, section):
            return load_section_data_for_ui(section, company)

        def _sec_save(company, section, json_data):
            return save_section_data(section, company, json_data)

        sec_load_btn.click(
            fn=_sec_load,
            inputs=[sec_company, sec_section],
            outputs=sec_json,
        )
        sec_save_btn.click(
            fn=_sec_save,
            inputs=[sec_company, sec_section, sec_json],
            outputs=sec_status,
        )


if __name__ == "__main__":
    from config import auth_enabled, auth_password, auth_user

    auth = (auth_user(), auth_password()) if auth_enabled() else None
    demo.queue().launch(
        server_name=HOST,
        server_port=PORT,
        share=SHARE,
        auth=auth,
    )
