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
import gradio as gr
import json
import os
import re
import io
import subprocess
import tempfile
from typing import List, Dict, Tuple, Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from resume_builder import (
    build_resume, load_company_profile,
    DATA_DIR, OUTPUT_DIR
)
from resume_builder import latex_escape, rank_projects, extract_bullets, build_experience_block

# ─── Constants & Setup ────────────────────────────────────────────────
COMPANY_DIR = os.path.join(DATA_DIR, "companies")
os.makedirs(COMPANY_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

RESUME_TYPES = ["analytics", "software", "biotech", "finance", "freelance"]

# ─── Utility Functions ────────────────────────────────────────────────

def slugify(s: str) -> str:
    """Convert string to URL-safe slug."""
    return re.sub(r'[^a-zA-Z0-9]+', '_', s.lower()).strip('_')


def get_company_names() -> List[str]:
    """Returns display names of all company profiles."""
    if not os.path.exists(COMPANY_DIR):
        return []
    files = [f for f in os.listdir(COMPANY_DIR) if f.endswith(".json")]
    return [f.replace(".json", "").replace("_", " ").title() for f in files]


def load_profile() -> Dict:
    """Load the base profile data."""
    path = os.path.join(DATA_DIR, "profile.json")
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

def save_company(name: str, website: str, role_name: str, resume_type: str,
                 required_skills: str, keywords: str, emphasize_metrics: str) -> str:
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
            result.append(f"  - {role} [{cfg['resume_type']}]")
        result.append("")

    return "\n".join(result) if result else "No companies saved yet."


def delete_company(name: str) -> str:
    """Delete a company profile by name."""
    slug = slugify(name)
    path = os.path.join(COMPANY_DIR, f"{slug}.json")
    if os.path.exists(path):
        os.remove(path)
        return f"Deleted: {name}"
    return f"Not found: {name}"

# ─── Resume Generation ──────────────────────────────────────────────────

def generate_resume_wrapper(company_display: str, role: str):
    """Generate resume and return (tex_string, pdf_file, status)."""
    # Resolve company slug
    slug = slugify(company_display)
    # Try exact display -> file mapping
    matched_key = None
    for fname in os.listdir(COMPANY_DIR):
        if fname.endswith(".json"):
            key = fname.replace(".json", "")
            display = key.replace("_", " ").title()
            if display.lower() == company_display.strip().lower() or key == slug:
                matched_key = key
                break

    if not matched_key:
        return None, None, f"Company not found: {company_display}"

    try:
        build_resume(matched_key, role)
    except Exception as e:
        return None, None, f"Build error: {str(e)}"

    safe_company = slugify(matched_key)
    safe_role = slugify(role)
    tex_path = os.path.join(OUTPUT_DIR, f"resume_{safe_company}_{safe_role}.tex")
    pdf_path = os.path.join(OUTPUT_DIR, f"resume_{safe_company}_{safe_role}.pdf")

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

    if hasattr(pdf_file, 'name'):
        path = pdf_file.name
    else:
        # Temporary save
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_file.read() if hasattr(pdf_file, 'read') else pdf_file)
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
        if not hasattr(pdf_file, 'name'):
            try:
                os.unlink(path)
            except Exception:
                pass


def analyze_resume_skills(pdf_file, company_display: str, role: str) -> Tuple[str, Optional[str]]:
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
    slug = slugify(company_display)
    matched_key = None
    for fname in os.listdir(COMPANY_DIR):
        if fname.endswith(".json"):
            key = fname.replace(".json", "")
            display = key.replace("_", " ").title()
            if display.lower() == company_display.strip().lower() or key == slug:
                matched_key = key
                break

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
    lines.append(f"Resume Type: {role_cfg['resume_type']}")
    lines.append("\n" + "-" * 60)
    lines.append("SKILLS MATCH")
    lines.append("-" * 60)
    lines.append(f"Matched ({len(matched_skills)}/{len(required_skills)}): {', '.join(matched_skills) if matched_skills else 'None'}")
    lines.append(f"Missing ({len(missing_skills)}): {', '.join(missing_skills) if missing_skills else 'None'}")

    lines.append("\n" + "-" * 60)
    lines.append("KEYWORD MATCH")
    lines.append("-" * 60)
    lines.append(f"Present ({len(present_keywords)}/{len(keywords)}): {', '.join(present_keywords) if present_keywords else 'None'}")
    lines.append(f"Missing ({len(missing_keywords)}): {', '.join(missing_keywords) if missing_keywords else 'None'}")

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
        lines.append(f"1. Add these missing skills to your resume: {', '.join(missing_skills)}")
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
        found = bool(re.search(rf'\b{sec}\b', resume_lower))
        status = "✅" if found else "⚠️"
        lines.append(f"  {status} {sec.title()}")

    report = "\n".join(lines)

    # Generate skill gap chart
    chart_path = None
    if HAS_MATPLOTLIB and (required_skills or keywords):
        chart_path = create_skill_chart(matched_skills, missing_skills, present_keywords, missing_keywords)

    return report, chart_path


def create_skill_chart(matched: List[str], missing: List[str], present_kw: List[str], missing_kw: List[str]) -> Optional[str]:
    """Create a horizontal bar chart showing skill/keyword match."""
    try:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))

        # Skills chart
        all_skills = matched + missing
        colors_skills = ['#4CAF50'] * len(matched) + ['#F44336'] * len(missing)
        axes[0].barh(range(len(all_skills)), [1] * len(all_skills),
                     color=colors_skills, tick_label=all_skills, height=0.6)
        axes[0].set_title('Skills: Matched vs Missing', fontweight='bold')
        axes[0].set_xlabel('Present')
        axes[0].set_yticks(range(len(all_skills)))
        axes[0].set_yticklabels(all_skills, fontsize=8)
        axes[0].invert_yaxis()
        # Legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='#4CAF50', label='Matched'),
            Patch(facecolor='#F44336', label='Missing')
        ]
        axes[0].legend(handles=legend_elements, loc='lower right', fontsize=8)

        # Keywords chart
        all_kw = present_kw + missing_kw
        colors_kw = ['#2196F3'] * len(present_kw) + ['#FF9800'] * len(missing_kw)
        axes[1].barh(range(len(all_kw)), [1] * len(all_kw),
                     color=colors_kw, tick_label=all_kw, height=0.6)
        axes[1].set_title('Keywords: Present vs Missing', fontweight='bold')
        axes[1].set_xlabel('Present')
        axes[1].set_yticks(range(len(all_kw)))
        axes[1].set_yticklabels(all_kw, fontsize=8)
        axes[1].invert_yaxis()
        legend_elements_kw = [
            Patch(facecolor='#2196F3', label='Present'),
            Patch(facecolor='#FF9800', label='Missing')
        ]
        axes[1].legend(handles=legend_elements_kw, loc='lower right', fontsize=8)

        plt.tight_layout()
        chart_path = os.path.join(OUTPUT_DIR, "skill_gap_chart.png")
        plt.savefig(chart_path, dpi=150, bbox_inches='tight')
        plt.close()
        return chart_path
    except Exception as e:
        print(f"Chart generation error: {e}")
        return None

# ─── Resume Optimization ───────────────────────────────────────────────

def get_optimization_suggestions(company_display: str, role: str) -> Tuple[str, List[str]]:
    """
    Generate optimization suggestions for optimizing a resume for a company/role.
    Returns (suggestion_summary, project_reorder_suggestions).
    """
    # Load company profile
    slug = slugify(company_display)
    matched_key = None
    for fname in os.listdir(COMPANY_DIR):
        if fname.endswith(".json"):
            key = fname.replace(".json", "")
            display = key.replace("_", " ").title()
            if display.lower() == company_display.strip().lower() or key == slug:
                matched_key = key
                break

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
    projects_dir = os.path.join(DATA_DIR, "projects")
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
    suggestions.append(f"Ensure your skills section includes: {', '.join(role_cfg.get('required_skills', [])[:8])}")

    # Project reorder suggestions
    project_order = [p["name"] for p in ranked[:4]]
    summary = "\n".join(suggestions)

    return summary, project_order


# ─── Gradio Interface ───────────────────────────────────────────────────

with gr.Blocks(title="Resume Builder Pro") as demo:
    gr.Markdown("# Resume Builder Pro")
    gr.Markdown("*Generate, analyze, and optimize company-specific resumes.*")

    with gr.Tabs():
        # ── Tab 1: Add/Edit Company ──────────────────────
        with gr.Tab("➕ Add/Edit Company"):
            gr.Markdown("### Add a new company profile with job roles")
            with gr.Row():
                with gr.Column(scale=1):
                    company_name = gr.Textbox(label="Company Name", placeholder="e.g. Fractal Analytics")
                    company_website = gr.Textbox(label="Company Website (optional)", placeholder="https://fractal.ai")
                    role_name = gr.Textbox(label="Job Role", placeholder="e.g. Decision Analytics Associate")
                    resume_type = gr.Dropdown(choices=RESUME_TYPES, label="Resume Type", value="analytics")
                with gr.Column(scale=1):
                    required_skills = gr.Textbox(label="Required Skills (comma-separated)",
                                                 placeholder="e.g. Python, statistical modeling, data analysis")
                    keywords = gr.Textbox(label="Role Keywords (comma-separated)",
                                          placeholder="e.g. analytics, modeling, stakeholder presentation")
                    emphasize_metrics = gr.Textbox(label="Emphasize Metrics (comma-separated)",
                                                   placeholder="e.g. 38,500+ trades labeled, ₹93k profit")

            save_btn = gr.Button("💾 Save Company Profile", variant="primary")
            save_output = gr.Textbox(label="Status", interactive=False)
            save_btn.click(fn=save_company,
                           inputs=[company_name, company_website, role_name, resume_type,
                                   required_skills, keywords, emphasize_metrics],
                           outputs=save_output)

        # ── Tab 2: Generate Resume ────────────────────────
        with gr.Tab("📄 Generate Resume"):
            gr.Markdown("### Generate a tailored resume")
            with gr.Row():
                company_dropdown = gr.Dropdown(choices=get_company_names(),
                                             label="Company",
                                             value=get_company_names()[0] if get_company_names() else "")
                role_input = gr.Textbox(label="Job Role", placeholder="Enter the role name (e.g. Quant Developer)")

            gen_btn = gr.Button("🚀 Generate Resume", variant="primary")
            with gr.Row():
                tex_display = gr.Textbox(label=".tex Source", lines=20, interactive=False)
                status_output = gr.Textbox(label="Status", interactive=False)

            pdf_file = gr.File(label="📥 Download PDF", visible=False)
            tex_file = gr.File(label="📥 Download .tex", visible=False)

            def gen_wrapper(company_disp, role):
                tex_content, pdf_path, status = generate_resume_wrapper(company_disp, role)
                outputs = [
                    gr.update(value=tex_content or "No output"),
                    gr.update(value=status),
                ]
                safe_company = slugify(company_disp)
                safe_role = slugify(role)
                tex_path = os.path.join(OUTPUT_DIR, f"resume_{safe_company}_{safe_role}.tex")

                if pdf_path and os.path.exists(pdf_path):
                    outputs.append(gr.update(value=pdf_path, visible=True))
                else:
                    outputs.append(gr.update(visible=False))

                if os.path.exists(tex_path):
                    outputs.append(gr.update(value=tex_path, visible=True))
                else:
                    outputs.append(gr.update(visible=False))

                return outputs

            gen_btn.click(fn=gen_wrapper,
                          inputs=[company_dropdown, role_input],
                          outputs=[tex_display, status_output, pdf_file, tex_file])

            refresh_btn = gr.Button("🔄 Refresh Company List")
            refresh_btn.click(fn=lambda: gr.update(choices=get_company_names()),
                              inputs=None, outputs=company_dropdown)

        # ── Tab 3: Analyze Resume ──────────────────────────
        with gr.Tab("🔍 Analyze Resume"):
            gr.Markdown("### Upload a PDF resume to analyze skill/keyword match against a company")
            with gr.Row():
                pdf_input = gr.File(label="📄 Upload PDF Resume", file_count="single", file_types=[".pdf"])
                with gr.Column():
                    analyze_company = gr.Dropdown(choices=get_company_names(),
                                                 label="Company",
                                                 value=get_company_names()[0] if get_company_names() else "")
                    analyze_role = gr.Textbox(label="Job Role", placeholder="e.g. Quant Developer")

            analyze_btn = gr.Button("📊 Run Analysis", variant="primary")
            analysis_output = gr.Textbox(label="Analysis Report", lines=30, interactive=False)
            chart_output = gr.Image(label="Skill Gap Chart", visible=False)

            def analyze_wrapper(pdf_file, company_disp, role):
                if pdf_file is None:
                    return gr.update(value="Please upload a PDF resume."), gr.update(visible=False)
                report, chart_path = analyze_resume_skills(pdf_file, company_disp, role)
                chart_update = gr.update(value=chart_path, visible=chart_path is not None) if chart_path else gr.update(visible=False)
                return gr.update(value=report), chart_update

            analyze_btn.click(fn=analyze_wrapper,
                              inputs=[pdf_input, analyze_company, analyze_role],
                              outputs=[analysis_output, chart_output])

            refresh_analyze_btn = gr.Button("🔄 Refresh Company List")
            refresh_analyze_btn.click(fn=lambda: gr.update(choices=get_company_names()),
                                      inputs=None, outputs=analyze_company)

        # ── Tab 4: Optimize Resume ────────────────────────
        with gr.Tab("⚡ Optimize Resume"):
            gr.Markdown("### Get suggestions to optimize your resume for a specific company")
            with gr.Row():
                opt_company = gr.Dropdown(choices=get_company_names(),
                                         label="Company",
                                         value=get_company_names()[0] if get_company_names() else "")
                opt_role = gr.Textbox(label="Job Role", placeholder="e.g. Quant Developer")

            opt_btn = gr.Button("💡 Get Suggestions", variant="primary")
            suggestions_output = gr.Textbox(label="Optimization Suggestions", lines=25, interactive=False)
            project_order_output = gr.Textbox(label="Recommended Project Order", interactive=False)

            def opt_wrapper(company_disp, role):
                suggestions, project_order = get_optimization_suggestions(company_disp, role)
                return gr.update(value=suggestions), gr.update(value=", ".join(project_order) if project_order else "No suggestions")

            opt_btn.click(fn=opt_wrapper,
                          inputs=[opt_company, opt_role],
                          outputs=[suggestions_output, project_order_output])

            refresh_opt_btn = gr.Button("🔄 Refresh Company List")
            refresh_opt_btn.click(fn=lambda: gr.update(choices=get_company_names()),
                                  inputs=None, outputs=opt_company)

        # ── Tab 5: Manage Companies ───────────────────────
        with gr.Tab("📋 Manage Companies"):
            gr.Markdown("### Saved Company Profiles")
            refresh_list_btn = gr.Button("🔄 Refresh List")
            company_list_display = gr.Textbox(label="Companies", value=list_all_companies(),
                                              lines=25, interactive=False)
            refresh_list_btn.click(fn=list_all_companies, inputs=None, outputs=company_list_display)

            with gr.Row():
                delete_input = gr.Textbox(label="Delete Company (by name)")
                delete_btn = gr.Button("🗑️ Delete Company", variant="danger")
                delete_status = gr.Textbox(label="Delete Status")
                delete_btn.click(fn=delete_company, inputs=delete_input, outputs=delete_status)


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
    )
