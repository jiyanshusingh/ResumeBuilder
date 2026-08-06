#!/usr/bin/env python3
"""
Company-Specific Resume Builder
Builds tailored LaTeX resumes for different companies and roles.
"""

import argparse
import json
import os
import re
import subprocess

from config import DATA_DIR, OUTPUT_DIR, TEMPLATE_DIR
from section_renderer import (
    render_achievements,
    render_certifications,
    render_coursework,
    render_education,
    render_internship,
    render_leadership,
    render_projects,
    render_skills,
)
from utils import latex_escape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def load_section_data(section_name, company_name=None):
    """Load section data from data/sections/<section_name>/.

    Tries company-specific file first, then falls back to default.json.
    Returns the parsed JSON dict or None.
    """
    section_dir = os.path.join(DATA_DIR, "sections", section_name)
    if not os.path.isdir(section_dir):
        return None

    candidates = []
    if company_name:
        candidates.append(
            f"{section_name}_{company_name.lower().replace(' ', '_')}.json"
        )
        candidates.append(f"{company_name.lower().replace(' ', '_')}.json")
    candidates.append("default.json")

    for fname in candidates:
        fpath = os.path.join(section_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "r") as f:
                return json.load(f)

    return None


def slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s.lower()).strip("_")


def load_company_profile(company_name):
    """Load a company profile, trying multiple naming conventions."""
    candidates = [
        company_name,
        company_name.replace(" ", "-").lower(),
        company_name.lower(),
    ]
    for candidate in candidates:
        path = os.path.join(DATA_DIR, "companies", f"{candidate}.json")
        if os.path.exists(path):
            return load_json(path)

    # Fallback: scan files and match by stored display name / slug.
    companies_dir = os.path.join(DATA_DIR, "companies")
    if os.path.isdir(companies_dir):
        normalized = company_name.strip().lower()
        norm_slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
        for fname in sorted(os.listdir(companies_dir)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(companies_dir, fname)
            try:
                data = load_json(fpath)
            except Exception:
                continue
            stored_name = str(data.get("name", ""))
            stored_slug = re.sub(r"[^a-z0-9]+", "_", stored_name.lower()).strip("_")
            if stored_name.lower() == normalized or stored_slug == norm_slug:
                return data
    raise FileNotFoundError(f"Company profile not found for: {company_name}")


def rank_projects(projects, keyword_weights):
    """Rank projects by relevance score based on keyword weights.

    When the offline embedding model is available, adds a semantic cosine
    component (role keywords vs project name + short description) on top of
    the keyword-based score.
    """
    scored = []
    query = " ".join(keyword_weights.keys())
    for proj in projects:
        score = 0
        for kw, weight in keyword_weights.items():
            if (
                kw.lower() in proj["short_description"].lower()
                or kw.lower() in " ".join(proj.get("tags", [])).lower()
            ):
                score += weight
            if kw.lower() in proj["name"].lower():
                score += weight * 0.5

        semantic = _semantic_project_score(query, proj)
        if semantic is not None:
            score += semantic * 5

        scored.append((score, proj))
    return [p for _, p in sorted(scored, key=lambda x: -x[0])]


def _semantic_project_score(query: str, proj: dict):
    """Cosine similarity of role-keyword query vs project name + description."""
    try:
        import embeddings
    except ImportError:
        return None
    if not embeddings.available() or not query.strip():
        return None
    desc = " ".join(
        str(proj.get("name", ""))
        + " "
        + str(proj.get("short_description", ""))
        + " "
        + " ".join(proj.get("tags", []))
    )
    return embeddings.similarity(query, desc)


def extract_bullets(proj_data, resume_type):
    """Extract relevant bullets for the resume type."""
    highlights = proj_data.get("highlights", [])
    metrics = proj_data.get("metrics", {}).get(resume_type, [])
    bullets = highlights + metrics
    return bullets[:4] if len(bullets) > 4 else bullets


_GENERIC_TAGS = {
    "analytics",
    "ml",
    "machine-learning",
    "software",
    "finance",
    "biotech",
    "freelance",
    "deployment",
    "research",
    "backend",
    "frontend",
    "full-stack",
    "data-science",
    "data",
}


_TECH_NAMES = {
    "python": "Python",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "scipy": "SciPy",
    "numpy": "NumPy",
    "pandas": "Pandas",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "scikit-learn": "scikit-learn",
    "scikitlearn": "scikit-learn",
    "docker": "Docker",
    "gcp": "GCP",
    "gcs": "GCS",
    "aws": "AWS",
    "terraform": "Terraform",
    "kubernetes": "Kubernetes",
    "fastapi": "FastAPI",
    "shap": "SHAP",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
}


def _project_tech(proj):
    tech = []
    for t in proj.get("tags", []):
        t = t.strip()
        if not t or t.lower() in _GENERIC_TAGS:
            continue
        tech.append(_TECH_NAMES.get(t.lower(), t.title()))
    return ", ".join(tech[:6])


def _project_link_label(url):
    if not url:
        return ""
    label = url.split("://", 1)[-1].lstrip("www.")
    return label.rstrip("/")


def build_experience_block(experiences, jake=False):
    blocks = []
    if jake:
        blocks.append("\\resumeSubHeadingListStart")
    for exp in experiences:
        if jake:
            block = "    \\resumeSubheading\n"
            block += (
                "      {"
                + latex_escape(exp["company"])
                + "}{"
                + latex_escape(exp["location"])
                + "}\n"
            )
            block += (
                "      {"
                + latex_escape(exp["title"])
                + "}{"
                + latex_escape(exp["duration"])
                + "}\n"
            )
            block += "      \\resumeItemListStart\n"
            for bullet in exp["bullets"]:
                block += "        \\resumeItem{" + latex_escape(bullet) + "}\n"
            block += "      \\resumeItemListEnd"
        else:
            block = "\\noindent\\textbf{" + latex_escape(exp["title"]) + "}"
            block += " \\hfill \\textit{" + latex_escape(exp["duration"]) + "}\n\n"
            block += "\\noindent\\textit{" + latex_escape(exp["company"]) + "}"
            block += " \\hfill " + latex_escape(exp["location"]) + "\n"
            block += "\\begin{itemize}\n"
            for bullet in exp["bullets"]:
                block += "    \\item " + latex_escape(bullet) + "\n"
            block += "\\end{itemize}"
        blocks.append(block)
    if jake:
        blocks.append("\\resumeSubHeadingListEnd")
    return "\n".join(blocks)


def build_projects_block(projects, resume_type, jake=False):
    blocks = []
    for proj in projects:
        bullets = extract_bullets(proj, resume_type)
        if jake:
            tech = _project_tech(proj)
            heading = "{\\textbf{" + latex_escape(proj["name"]) + "}"
            if tech:
                heading += " $|$ \\emph{" + latex_escape(tech) + "}"
            heading += "}"
            label = _project_link_label(proj.get("links", {}).get("live"))
            if not label:
                label = _project_link_label(proj.get("links", {}).get("code"))
            if label:
                link_url = (
                    proj["links"]["live"]
                    and proj["links"]["live"]
                    or proj["links"]["code"]
                )
                right = "{\\href{" + link_url + "}{" + latex_escape(label) + "}}"
            else:
                right = "{}"
            block = "    \\resumeProjectHeading\n"
            block += "        " + heading + " " + right + "\n"
            block += "        \\resumeItemListStart\n"
            for bullet in bullets:
                block += "          \\resumeItem{" + latex_escape(bullet) + "}\n"
            block += "        \\resumeItemListEnd"
        else:
            block = "\\noindent\\textbf{" + latex_escape(proj["name"]) + "}"
            links = []
            if proj["links"]["live"]:
                links.append("\\href{" + proj["links"]["live"] + "}{\\faGlobe}")
            links.append("\\href{" + proj["links"]["code"] + "}{\\faGithub}")
            block += " \\hfill " + " ".join(links)
            block += "\n\\begin{itemize}\n"
            for bullet in bullets:
                block += "    \\item " + latex_escape(bullet) + "\n"
            block += "\\end{itemize}"
        blocks.append(block)
    return "\n".join(blocks)


def build_skills_block(skills_dict, jake=False):
    lines = []
    for category, skills in skills_dict.items():
        escaped = [latex_escape(s) for s in skills]
        if jake:
            lines.append(
                "      \\item[]{\\hangindent=1.7em\\hangafter=1 "
                "\\textbf{"
                + latex_escape(category)
                + "}{: "
                + ", ".join(escaped)
                + "}}"
            )
        else:
            lines.append(
                "\\noindent\\textbf{"
                + latex_escape(category)
                + ": "
                + ", ".join(escaped)
                + "}"
            )
    return "\n".join(lines)


def build_coursework_block(courses):
    escaped = [latex_escape(c) for c in courses]
    return ", ".join(escaped)


def build_leadership_block(entries):
    if not entries:
        return "\\resumeSubHeadingListStart\n    \\resumeSubheading\n      {}{}\n      {}{}\n\\resumeSubHeadingListEnd"

    blocks = ["\\resumeSubHeadingListStart"]
    for e in entries:
        role = e.get("role", "")
        loc = e.get("location", "")
        desc = e.get("description", "")
        date = e.get("date", "")
        blocks.append(
            "    \\resumeSubheading\n"
            "      {" + latex_escape(role) + "}{" + latex_escape(loc) + "}\n"
            "      {" + latex_escape(desc) + "}{" + latex_escape(date) + "}"
        )
    blocks.append("\\resumeSubHeadingListEnd")
    return "\n".join(blocks)


def build_education_block(edu, jake=False):
    if not jake:
        return (
            "\\noindent\\textbf{" + latex_escape(edu["degree"]) + "}"
            " \\hfill \\textbf{" + latex_escape(edu["cgpa"]) + "}"
            "\n\n\\noindent "
            + latex_escape(edu["institution"])
            + " -- "
            + latex_escape(edu["duration"])
        )
    return (
        "\\resumeSubHeadingListStart\n"
        "    \\resumeSubheading\n"
        "      {" + latex_escape(edu["institution"]) + "}{}\n"
        "      {"
        + latex_escape(edu["degree"])
        + " -- "
        + latex_escape(edu["cgpa"])
        + "}{"
        + latex_escape(edu["duration"])
        + "}\n"
        "\\resumeSubHeadingListEnd"
    )


def build_certifications_block(certs):
    block = "\\begin{itemize}\n"
    for cert in certs:
        block += "    \\item " + latex_escape(cert["name"]) + ", "
        block += (
            latex_escape(cert["organization"])
            + " ("
            + latex_escape(str(cert["date"]))
            + ")\n"
        )
    block += "\\end{itemize}"
    return block


def build_achievements_block(achievements):
    if not achievements:
        return "\\begin{itemize}\n\n\\end{itemize}"

    block = "\\begin{itemize}\n"
    for ach in achievements:
        block += "    \\item " + latex_escape(ach) + "\n"
    block += "\\end{itemize}"
    return block


def get_template_path(template_type=None):
    """Get the path to a resume template file."""
    if template_type is None or template_type == "default":
        return TEMPLATE_DIR / "resume_template.tex.j2"
    template_name = f"resume_template_{template_type}.tex.j2"
    template_path = TEMPLATE_DIR / template_name
    if template_path.exists():
        return template_path
    return TEMPLATE_DIR / "resume_template.tex.j2"


def build_resume(company_name, job_role, output_dir=None, template_type=None):
    # Load data
    profile = load_json(os.path.join(DATA_DIR, "profile.json"))
    company = load_company_profile(company_name)

    if job_role not in company.get("job_roles", {}):
        available = list(company.get("job_roles", {}).keys())
        raise ValueError(f"Role '{job_role}' not found. Available: {available}")

    role_config = company["job_roles"][job_role]
    resume_type = role_config.get("resume_type", "analytics")

    # Load all projects
    projects_dir = os.path.join(DATA_DIR, "projects")
    projects = []
    for fname in os.listdir(projects_dir):
        if fname.endswith(".json"):
            projects.append(load_json(os.path.join(projects_dir, fname)))

    # Rank projects by role keywords
    keywords = role_config.get("keywords", [])
    keyword_weights = {kw: 5 for kw in keywords}
    ranked = rank_projects(projects, keyword_weights)

    # Take top 3-4 projects
    selected_projects = ranked[:4]

    # Select relevant certificates
    all_certs = profile["certificates"]
    relevant_certs = [
        c
        for c in all_certs
        if any(
            r.lower() in " ".join(c["relevance"]).lower()
            for r in role_config.get("keywords", [])
        )
    ]
    if len(relevant_certs) < 3:
        relevant_certs = all_certs[:4]

    # Build skills dict
    skills = profile["skills"]
    if resume_type == "analytics":
        ordered_skills = {
            "ML & Statistics": skills.get("ml_data_science", []),
            "Programming": skills.get("programming", []),
            "Backend": skills.get("backend", []),
            "DevOps": skills.get("devops", []),
        }
    elif resume_type == "biotech":
        ordered_skills = {
            "ML & Bioinformatics": skills.get("ml_data_science", [])
            + skills.get("biotech", []),
            "Programming": skills.get("programming", []),
            "Web & Deployment": skills.get("backend", []) + skills.get("devops", []),
            "Data Tools": skills.get("databases", []),
        }
    elif resume_type == "finance":
        ordered_skills = {
            "ML & Trading": skills.get("ml_data_science", []),
            "Cloud & DevOps": skills.get("devops", []) + skills.get("backend", []),
            "Programming": skills.get("programming", []),
            "Tools": skills.get("databases", []),
        }
    else:  # software / freelance
        ordered_skills = {
            "Backend": skills.get("backend", []),
            "Frontend": skills.get("frontend", []),
            "DevOps": skills.get("devops", []),
            "ML/AI": skills.get("ml_data_science", []),
            "Databases": skills.get("databases", []),
        }

    # Load template
    template_path = get_template_path(template_type)
    with open(template_path, "r") as f:
        template = f.read()

    github_handle = profile["github"].replace("https://github.com/", "")
    jake = template_type == "jake"

    sections_dir = os.path.join(DATA_DIR, "sections")
    coursework_data = load_section_data("coursework", company_name)
    internship_data = load_section_data("internship", company_name)

    experience_block = build_experience_block(profile["experience"], jake=jake)
    projects_block = render_projects(selected_projects, resume_type, jake=jake)
    skills_block = render_skills(ordered_skills, jake=jake)
    certs_block = render_certifications(relevant_certs, jake=jake)
    achievements_block = render_achievements(profile["achievements"], jake=jake)
    coursework_block = (
        render_coursework(coursework_data, jake=jake) if coursework_data else ""
    )
    internship_block = (
        render_internship(internship_data, jake=jake) if internship_data else ""
    )
    leadership_block = render_leadership(profile.get("leadership", []), jake=jake)
    education_block = render_education(profile["education"], jake=jake)

    section_order = role_config.get(
        "section_order",
        [
            "Education",
            "Relevant Coursework",
            "Internship Experience",
            "Projects",
            "Technical Skills",
            "Leadership / Extracurricular",
            "Certifications",
            "Key Achievements",
        ],
    )

    section_renderers = {
        "Education": education_block,
        "Relevant Coursework": coursework_block,
        "Internship Experience": internship_block,
        "Projects": projects_block,
        "Technical Skills": skills_block,
        "Leadership / Extracurricular": leadership_block,
        "Certifications": certs_block,
        "Key Achievements": achievements_block,
    }

    section_headers = {
        "Education": "\\section{Education}",
        "Relevant Coursework": "\\section{Relevant Coursework}",
        "Internship Experience": "\\section{Internship Experience}",
        "Projects": "\\section{Projects}",
        "Technical Skills": "\\section{Technical Skills}",
        "Leadership / Extracurricular": "\\section{Leadership / Extracurricular}",
        "Certifications": "\\section{Certifications}",
        "Key Achievements": "\\section{Key Achievements}",
    }

    sections_output = []
    for section_name in section_order:
        content = section_renderers.get(section_name, "")
        if content:
            if jake:
                sections_output.append(content)
            else:
                header = section_headers.get(section_name, "")
                sections_output.append(header + "\n" + content)

    replacements = {
        "(NAME)": latex_escape(profile["name"]),
        "(PHONE)": latex_escape(profile["phone"]),
        "(EMAIL)": latex_escape(profile["email"]),
        "(GITHUB_URL)": profile["github"],
        "(GITHUB_HANDLE)": github_handle,
        "(LINKEDIN_URL)": profile["linkedin"],
        "(LOCATION)": latex_escape(profile["location"]),
        "(HEADLINE)": latex_escape(
            profile["headlines"].get(resume_type, profile["headlines"]["analytics"])
        ),
        "(SUMMARY)": latex_escape(
            profile["summaries"].get(resume_type, profile["summaries"]["analytics"])
        ),
        "(EXPERIENCE_BLOCK)": experience_block,
        "(PROJECTS_BLOCK)": projects_block,
        "(SKILLS_BLOCK)": skills_block,
        "(Education_BLOCK)": education_block,
        "(CERTIFICATIONS_BLOCK)": certs_block,
        "(ACHIEVEMENTS_BLOCK)": achievements_block,
        "(COURSEWORK_BLOCK)": coursework_block,
        "(LEADERSHIP_BLOCK)": leadership_block,
        "(INTERNSHIP_BLOCK)": internship_block,
        "(SECTIONS)": "\n".join(sections_output),
    }

    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)

    # Save output
    if output_dir is None:
        output_dir = OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    tex_path = os.path.join(
        output_dir, f"resume_{slugify(company_name)}_{slugify(job_role)}.tex"
    )
    with open(tex_path, "w") as f:
        f.write(rendered)

    print(f"LaTeX source saved to: {tex_path}")

    # Compile to PDF
    pdf_name = f"resume_{slugify(company_name)}_{slugify(job_role)}.pdf"
    pdf_path = os.path.join(output_dir, pdf_name)
    try:
        result = subprocess.run(
            ["tectonic", "--outdir", output_dir, tex_path],
            capture_output=True,
            text=True,
            cwd=BASE_DIR,
        )
        if result.returncode == 0 and os.path.exists(pdf_path):
            print(f"PDF saved to: {pdf_path}")
        else:
            print(f"PDF compilation issue: {result.stderr[:500]}")
    except FileNotFoundError:
        print("tectonic not found. Install with: brew install tectonic")

    return tex_path


def propose_company_profile(name: str, role: str, extraction: dict) -> dict:
    """Build a company profile dict auto-proposed from a JD extraction.

    Wraps the imported required_skills/keywords/metrics/resume_type into the
    same company JSON shape used across the app (see web_ui.save_company).
    """
    name = (name or "").strip() or "New Company"
    role = (role or "").strip() or "Role"
    skills = list(dict.fromkeys(extraction.get("required_skills", [])))
    keywords = list(dict.fromkeys(extraction.get("keywords", [])))
    metrics = list(dict.fromkeys(extraction.get("emphasize_metrics", [])))
    resume_type = extraction.get("resume_type", "analytics")
    return {
        "name": name,
        "website": extraction.get("source_url", ""),
        "resume_type": resume_type,
        "job_roles": {
            role: {
                "resume_type": resume_type,
                "required_skills": skills,
                "keywords": keywords,
                "emphasize_metrics": metrics,
            }
        },
    }


def save_company_profile(profile: dict) -> str:
    """Write a company profile dict to data/companies/<slug>.json. Returns path.

    Merges into an existing file of the same name so multiple roles can be
    added to one company.
    """
    companies_dir = os.path.join(DATA_DIR, "companies")
    os.makedirs(companies_dir, exist_ok=True)
    name = profile.get("name", "Company")
    slug = slugify(name)
    path = os.path.join(companies_dir, f"{slug}.json")
    if os.path.exists(path):
        existing = load_json(path)
        existing.setdefault("job_roles", {}).update(profile.get("job_roles", {}))
        profile = existing
    with open(path, "w") as f:
        json.dump(profile, f, indent=2)
    return path


PLACEMENT_COMPANIES = {"Tesla", "GEP", "Tredence", "ZS"}


def get_placement_companies() -> List[str]:
    """Return the list of placement company names."""
    return sorted(PLACEMENT_COMPANIES)


def get_placement_projects() -> List[dict]:
    """Return all placement (non-user) projects from data/projects/."""
    projects_dir = os.path.join(DATA_DIR, "projects")
    projects = []
    for fname in os.listdir(projects_dir):
        if not fname.endswith(".json"):
            continue
        proj = load_json(os.path.join(projects_dir, fname))
        if not proj.get("is_user_project", False):
            projects.append(proj)
    return projects


def get_placement_projects_by_company(company_name: str) -> List[dict]:
    """Return placement projects filtered by company name."""
    return [p for p in get_placement_projects() if p.get("company") == company_name]


def list_companies():
    """List all available company profiles."""
    companies_dir = os.path.join(DATA_DIR, "companies")
    for fname in sorted(os.listdir(companies_dir)):
        company = load_json(os.path.join(companies_dir, fname))
        roles = list(company.get("job_roles", {}).keys())
        print(f"{company['name']}: {', '.join(roles)}")


def main():
    parser = argparse.ArgumentParser(description="Company-Specific Resume Builder")
    parser.add_argument("--company", "-c", help="Target company name")
    parser.add_argument("--role", "-r", help="Job role (use with --company)")
    parser.add_argument(
        "--list", "-l", action="store_true", help="List available companies"
    )
    parser.add_argument("--output-dir", "-o", default=None, help="Output directory")

    args = parser.parse_args()

    if args.list:
        list_companies()
        return

    if not args.company or not args.role:
        parser.error("--company and --role are required (or use --list)")

    build_resume(args.company, args.role, args.output_dir)


if __name__ == "__main__":
    main()
