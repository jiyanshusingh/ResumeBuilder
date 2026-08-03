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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "resume_template.tex.j2")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s.lower()).strip("_")


def latex_escape(s: str) -> str:
    """Escape special LaTeX characters."""
    if s is None:
        return ""
    s = str(s)
    # Replace special chars - order matters
    s = s.replace("\\", "\\textbackslash ")
    s = s.replace("$", "\\$")
    s = s.replace("&", "\\&")
    s = s.replace("%", "\\%")
    s = s.replace("#", "\\#")
    s = s.replace("_", "\\_")
    s = s.replace("{", "\\{")
    s = s.replace("}", "\\}")
    s = s.replace("~", "\\textasciitilde ")
    s = s.replace("^", "\\textasciicircum ")
    # Replace ₹ with INR if not using unicode
    # s = s.replace('₹', 'Rs.~')
    return s


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
    raise FileNotFoundError(f"Company profile not found for: {company_name}")


def rank_projects(projects, keyword_weights):
    """Rank projects by relevance score based on keyword weights."""
    scored = []
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
        scored.append((score, proj))
    return [p for _, p in sorted(scored, key=lambda x: -x[0])]


def extract_bullets(proj_data, resume_type):
    """Extract relevant bullets for the resume type."""
    highlights = proj_data.get("highlights", [])
    metrics = proj_data.get("metrics", {}).get(resume_type, [])
    bullets = highlights + metrics
    return bullets[:4] if len(bullets) > 4 else bullets


def build_experience_block(experiences):
    blocks = []
    for exp in experiences:
        block = "\\noindent\\textbf{" + latex_escape(exp["title"]) + "}"
        block += " \\hfill \\textit{" + latex_escape(exp["duration"]) + "}\n\n"
        block += "\\noindent\\textit{" + latex_escape(exp["company"]) + "}"
        block += " \\hfill " + latex_escape(exp["location"]) + "\n"
        block += "\\begin{itemize}\n"
        for bullet in exp["bullets"]:
            block += "    \\item " + latex_escape(bullet) + "\n"
        block += "\\end{itemize}"
        blocks.append(block)
    return "\n\n".join(blocks)


def build_projects_block(projects, resume_type):
    blocks = []
    for proj in projects:
        bullets = extract_bullets(proj, resume_type)
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
    return "\n\n".join(blocks)


def build_skills_block(skills_dict):
    lines = []
    for category, skills in skills_dict.items():
        escaped = [latex_escape(s) for s in skills]
        lines.append(
            "\\noindent\\textbf{"
            + latex_escape(category)
            + ": "
            + ", ".join(escaped)
            + "}"
        )
    return "\n\n".join(lines)


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
    resume_type = role_config["resume_type"]

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

    # Build blocks
    experience_block = build_experience_block(profile["experience"])
    projects_block = build_projects_block(selected_projects, resume_type)
    skills_block = build_skills_block(ordered_skills)
    certs_block = build_certifications_block(relevant_certs)
    achievements_block = build_achievements_block(profile["achievements"])

    education_block = (
        "\\noindent\\textbf{" + latex_escape(profile["education"]["degree"]) + "}"
        " \\hfill \\textbf{" + latex_escape(profile["education"]["cgpa"]) + "}"
        "\n\n\\noindent "
        + latex_escape(profile["education"]["institution"])
        + " -- "
        + latex_escape(profile["education"]["duration"])
    )

    # Replace placeholders
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
