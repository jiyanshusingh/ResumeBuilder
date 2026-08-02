#!/usr/bin/env python3
"""
Generate all 4 generic resume types (Analytics, Software, Biotech, Freelance).
Uses the resume_builder core engine.
"""
import json
import os
import subprocess
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "resume_template.tex.j2")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def slugify(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]+', '_', s.lower()).strip('_')


def latex_escape(s: str) -> str:
    """Escape special LaTeX characters."""
    if s is None:
        return ""
    s = str(s)
    s = s.replace('\\', '\\textbackslash ')
    s = s.replace('$', '\\$')
    s = s.replace('&', '\\&')
    s = s.replace('%', '\\%')
    s = s.replace('#', '\\#')
    s = s.replace('_', '\\_')
    s = s.replace('{', '\\{')
    s = s.replace('}', '\\}')
    s = s.replace('~', '\\textasciitilde ')
    s = s.replace('^', '\\textasciicircum ')
    return s


def get_relevant_projects(resume_type):
    """Get projects relevant to this resume type, ranked by relevance."""
    projects_dir = os.path.join(DATA_DIR, "projects")
    projects = []
    for fname in os.listdir(projects_dir):
        if fname.endswith(".json"):
            projects.append(load_json(os.path.join(projects_dir, fname)))

    # Tag-based filtering and ranking
    type_tags = {
        "analytics": ["analytics", "ml", "finance"],
        "software": ["software", "deployment", "backend", "devops"],
        "biotech": ["biotech", "ml", "research"],
        "finance": ["ml", "analytics", "finance", "backend"],
        "freelance": ["analytics", "ml", "biotech", "deployment", "software"],
    }

    relevant_tags = set(type_tags.get(resume_type, type_tags.get("analytics", [])))

    # Score projects
    scored = []
    for proj in projects:
        score = 0
        proj_tags = set(proj.get("tags", []))
        overlap = proj_tags & relevant_tags
        score += len(overlap) * 3
        # Bonus for headline projects
        if proj.get("is_headline", False):
            score += 5
        scored.append((score, proj))

    # Sort by score
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:4]]


def get_relevant_certs(resume_type):
    """Filter certificates by relevance to resume type."""
    profile = load_json(os.path.join(DATA_DIR, "profile.json"))
    all_certs = profile["certificates"]

    if resume_type == "biotech":
        return all_certs  # All certs are biotech-relevant
    elif resume_type == "software":
        return all_certs[:4]  # Top 4
    elif resume_type in ("analytics", "finance"):
        # Show data/analytics-related certs
        return [c for c in all_certs if any(t in " ".join(c.get("relevance", [])).lower() for t in ["ml", "analytics", "data", "healthcare", "biotech"])]
    else:  # freelance
        return all_certs[:4]


def build_skills_block(resume_type):
    profile = load_json(os.path.join(DATA_DIR, "profile.json"))
    skills = profile["skills"]

    if resume_type == "analytics":
        ordered = {
            "ML/AI": skills.get("ml_data_science", []),
            "Programming": skills.get("programming", []),
            "Backend": skills.get("backend", []),
            "DevOps & Cloud": skills.get("devops", []),
            "Database": skills.get("databases", []),
        }
    elif resume_type == "biotech":
        ordered = {
            "ML & Bioinformatics": skills.get("ml_data_science", []) + skills.get("biotech", []),
            "Programming": skills.get("programming", []),
            "Web & Deployment": skills.get("backend", []) + skills.get("devops", []),
            "Data Tools": skills.get("databases", []),
        }
    elif resume_type == "finance":
        ordered = {
            "ML & Trading": skills.get("ml_data_science", []),
            "Cloud & DevOps": skills.get("devops", []) + skills.get("backend", []),
            "Programming": skills.get("programming", []),
            "Data & Tools": skills.get("databases", []),
        }
    else:  # software / freelance
        ordered = {
            "Backend": skills.get("backend", []),
            "Frontend": skills.get("frontend", []),
            "DevOps": skills.get("devops", []),
            "ML/AI": skills.get("ml_data_science", []),
            "Database": skills.get("databases", []),
        }

    lines = []
    for category, skill_list in ordered.items():
        escaped = [latex_escape(s) for s in skill_list]
        lines.append("\\noindent\\textbf{" + latex_escape(category) + ": " + ", ".join(escaped) + "}")
    return "\n\n".join(lines)


def build_experience_block(experiences, resume_type):
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
        # Try highlights first, fall back to metrics
        bullets = proj.get("highlights", [])
        if not bullets:
            bullets = proj.get("metrics", {}).get(resume_type, [])[:4]

        block = "\\noindent\\textbf{" + latex_escape(proj["name"]) + "}"
        links = []
        if proj.get("links", {}).get("live"):
            links.append("\\href{" + proj["links"]["live"] + "}{\\faGlobe}")
        if proj.get("links", {}).get("code"):
            links.append("\\href{" + proj["links"]["code"] + "}{\\faGithub}")
        if links:
            block += " \\hfill " + " ".join(links)
        block += "\n\\begin{itemize}\n"
        for bullet in bullets:
            block += "    \\item " + latex_escape(bullet) + "\n"
        block += "\\end{itemize}"
        blocks.append(block)
    return "\n\n".join(blocks)


def build_achievements_block(achievements):
    block = "\\begin{itemize}\n"
    for ach in achievements:
        block += "    \\item " + latex_escape(ach) + "\n"
    block += "\\end{itemize}"
    return block


def build_certifications_block(certs):
    if not certs:
        return ""
    block = "\\begin{itemize}\n"
    for cert in certs:
        block += "    \\item " + latex_escape(cert["name"]) + ", "
        block += latex_escape(cert["organization"]) + " (" + latex_escape(str(cert["date"])) + ")\n"
    block += "\\end{itemize}"
    return block


def build_education_block(education):
    degree = education.get("degree", "B.Tech")
    cgpa = education.get("cgpa", "")
    institution = education.get("institution", "")
    duration = education.get("duration", "")
    return (
        "\\noindent\\textbf{" + latex_escape(degree) + "}"
        " \\hfill \\textbf{" + latex_escape(cgpa) + "}"
        "\n\n\\noindent " + latex_escape(institution)
        + " -- " + latex_escape(duration)
    )


def generate_resume(resume_type, output_dir=None):
    """Generate a resume of a specific type (analytics/software/biotech/finance/freelance)."""
    profile = load_json(os.path.join(DATA_DIR, "profile.json"))

    # Select relevant projects
    selected_projects = get_relevant_projects(resume_type)

    # Select relevant certificates
    relevant_certs = get_relevant_certs(resume_type)

    # Build skills block
    skills_block = build_skills_block(resume_type)

    # Build experience block
    experience_block = build_experience_block(profile["experience"], resume_type)

    # Build projects block
    projects_block = build_projects_block(selected_projects, resume_type)

    # Build other blocks
    achievements_block = build_achievements_block(profile["achievements"])
    certs_block = build_certifications_block(relevant_certs)
    education_block = build_education_block(profile["education"])

    # Load template
    with open(TEMPLATE_PATH, "r") as f:
        template = f.read()

    github_handle = profile["github"].replace("https://github.com/", "")

    # Replace placeholders
    replacements = {
        "(NAME)": latex_escape(profile["name"]),
        "(PHONE)": latex_escape(profile["phone"]),
        "(EMAIL)": latex_escape(profile["email"]),
        "(GITHUB_URL)": profile["github"],
        "(GITHUB_HANDLE)": github_handle,
        "(LINKEDIN_URL)": profile["linkedin"],
        "(LOCATION)": latex_escape(profile["location"]),
        "(HEADLINE)": latex_escape(profile["headlines"].get(resume_type, profile["headlines"]["analytics"])),
        "(SUMMARY)": latex_escape(profile["summaries"].get(resume_type, profile["summaries"]["analytics"])),
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

    # Remove empty sections
    rendered = re.sub(r'\\section\*\{Certifications\}\n\\begin\{itemize\}\n\\end\{itemize\}', '', rendered)

    # Save output
    if output_dir is None:
        output_dir = os.path.join(BASE_DIR, "output")
    os.makedirs(output_dir, exist_ok=True)

    tex_filename = f"resume_{resume_type}.tex"
    tex_path = os.path.join(output_dir, tex_filename)
    with open(tex_path, "w") as f:
        f.write(rendered)

    print(f"LaTeX source saved to: {tex_path}")

    # Compile to PDF
    pdf_filename = f"resume_{resume_type}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)
    try:
        result = subprocess.run(
            ["tectonic", "--outdir", output_dir, tex_path],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        if result.returncode == 0 and os.path.exists(pdf_path):
            print(f"PDF saved to: {pdf_path}")
        else:
            print(f"PDF compilation issue: {result.stderr[:500]}")
    except FileNotFoundError:
        print("tectonic not found. Install with: brew install tectonic")

    return tex_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Resume Generator (generic types)")
    parser.add_argument("--type", "-t", choices=["analytics", "software", "biotech", "finance", "freelance"],
                       help="Resume type to generate")
    parser.add_argument("--all", action="store_true", help="Generate all resume types")
    parser.add_argument("--output-dir", "-o", default=None, help="Output directory")

    args = parser.parse_args()

    if args.all:
        for rtype in ["analytics", "software", "biotech", "finance", "freelance"]:
            print(f"\n--- Generating {rtype} resume ---")
            generate_resume(rtype, args.output_dir)
    elif args.type:
        generate_resume(args.type, args.output_dir)
    else:
        parser.error("Specify --type <type> or --all")


if __name__ == "__main__":
    main()
