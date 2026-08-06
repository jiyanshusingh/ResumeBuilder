import json
import os

from utils import latex_escape

SECTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sections")


def load_section_data(section_name, company_name=None):
    """Load section data from data/sections/<section_name>/.

    Tries company-specific file first, then falls back to default.json.
    Returns the parsed JSON dict.
    """
    section_dir = os.path.join(SECTIONS_DIR, section_name)
    if not os.path.isdir(section_dir):
        return None

    candidates = []
    if company_name:
        candidates.append(f"{section_name}_{company_name.lower().replace(' ', '_')}.json")
        candidates.append(f"{company_name.lower().replace(' ', '_')}.json")
    candidates.append("default.json")

    for fname in candidates:
        fpath = os.path.join(section_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "r") as f:
                return json.load(f)

    return None


def render_coursework(coursework_data, jake=False):
    """Render the Relevant Coursework section as LaTeX."""
    if not coursework_data:
        return ""

    items = coursework_data.get("items", [])
    if not items:
        return ""

    if jake:
        rows = []
        for i in range(0, len(items), 3):
            row = items[i:i + 3]
            rows.append(
                " & ".join(
                    "\\small \\textbullet\\ " + latex_escape(item) for item in row
                )
            )
        block = "\\begin{tabular*}{\\textwidth}{@{\\extracolsep{\\fill}} l l l}\n"
        block += "  " + " \\\\\n  ".join(rows) + "\n"
        block += "\\end{tabular*}\n"
        block += "\\vspace{-8pt}"
        return block

    block = "\\begin{itemize}[leftmargin=0.15in, label={}]\n"
    for item in items:
        block += "    \\item " + latex_escape(item) + "\n"
    block += "  \\end{itemize}\n"
    block += "\\vspace{-8pt}"
    return block


def render_internship(internship_data, jake=False):
    """Render the Internship Experience section as LaTeX."""
    if not internship_data:
        return ""

    items = internship_data.get("items", [])
    if not items:
        return ""

    if jake:
        block = "  \\resumeSubHeadingListStart\n"
        for exp in items:
            block += "    \\resumeSubheading\n"
            block += "      {" + latex_escape(exp.get("company", "")) + "}"
            block += "{" + latex_escape(exp.get("location", "")) + "}\n"
            block += "      {" + latex_escape(exp.get("title", "")) + "}"
            block += "{" + latex_escape(exp.get("duration", "")) + "}\n"
            block += "      \\resumeItemListStart\n"
            for bullet in exp.get("bullets", []):
                block += "        \\resumeItem{" + latex_escape(bullet) + "}\n"
            block += "      \\resumeItemListEnd\n"
        block += "  \\resumeSubHeadingListEnd\n"
        block += "\\vspace{-5pt}"
        return block

    block = ""
    for exp in items:
        block += "\\noindent\\textit{" + latex_escape(exp.get("title", "")) + "}"
        block += " \\hfill \\textit{" + latex_escape(exp.get("duration", "")) + "}\n\n"
        block += "\\noindent\\textit{" + latex_escape(exp.get("company", ""))
        block += "}" + " \\hfill " + latex_escape(exp.get("location", "")) + "\n"
        block += "\\begin{itemize}\n"
        for bullet in exp.get("bullets", []):
            block += "    \\item " + latex_escape(bullet) + "\n"
        block += "\\end{itemize}\n"
    block += "\\vspace{-5pt}"
    return block


def render_projects(projects, resume_type, jake=False):
    """Render the Projects section as LaTeX."""
    if not projects:
        return ""

    if jake:
        block = ""
        for proj in projects:
            tech = _project_tech_jake(proj)
            heading = "{\\textbf{" + latex_escape(proj.get("name", "")) + "}"
            if tech:
                heading += " $|$ \\emph{" + latex_escape(tech) + "}"
            heading += "}"
            label = _project_link_label(proj.get("links", {}).get("live"))
            if not label:
                label = _project_link_label(proj.get("links", {}).get("code"))
            if label:
                link_url = (
                    proj.get("links", {}).get("live")
                    and proj.get("links", {}).get("live")
                    or proj.get("links", {}).get("code")
                )
                right = "{\\href{" + link_url + "}{" + latex_escape(label) + "}}"
            else:
                right = "{}"
            block += "    \\resumeProjectHeading\n"
            block += "        " + heading + " " + right + "\n"
            block += "        \\resumeItemListStart\n"
            bullets = _extract_bullets_jake(proj, resume_type)
            for bullet in bullets:
                block += "          \\resumeItem{" + latex_escape(bullet) + "}\n"
            block += "        \\resumeItemListEnd\n"
        block += "\\vspace{-5pt}"
        return block

    block = "\\noindent\\textbf{Projects}\n"
    for proj in projects:
        bullets = _extract_bullets_jake(proj, resume_type)
        block += "\\noindent\\textbf{" + latex_escape(proj.get("name", "")) + "}"
        links = []
        if proj.get("links", {}).get("live"):
            links.append("\\href{" + proj["links"]["live"] + "}{\\faGlobe}")
        if proj.get("links", {}).get("code"):
            links.append("\\href{" + proj["links"]["code"] + "}{\\faGithub}")
        block += " \\hfill " + " ".join(links) + "\n"
        block += "\\begin{itemize}\n"
        for bullet in bullets:
            block += "    \\item " + latex_escape(bullet) + "\n"
        block += "\\end{itemize}\n"
    block += "\\vspace{-5pt}"
    return block


def render_skills(skills_dict, jake=False):
    """Render the Technical Skills section as LaTeX."""
    if not skills_dict:
        return ""

    if jake:
        block = "  \\begin{itemize}[leftmargin=0.15in, label={}]\n"
        block += "    \\small{\n"
        for category, skills in skills_dict.items():
            escaped = [latex_escape(s) for s in skills]
            block += (
                "      \\item[]{\\hangindent=1.7em\\hangafter=1 "
                "\\textbf{" + latex_escape(category) + "}{: "
                + ", ".join(escaped) + "}}\n"
            )
        block += "    }\n"
        block += "  \\end{itemize}\n"
        block += "\\vspace{-5pt}"
        return block

    block = ""
    for category, skills in skills_dict.items():
        block += "\\noindent\\textbf{" + latex_escape(category) + ": "
        block += ", ".join(latex_escape(s) for s in skills) + "}\n"
    block += "\\vspace{-5pt}"
    return block


def render_education(edu, jake=False):
    """Render the Education section as LaTeX."""
    if not edu:
        return ""

    if jake:
        block = "  \\resumeSubHeadingListStart\n"
        block += "    \\resumeSubheading\n"
        block += "      {" + latex_escape(edu.get("institution", "")) + "}{}\n"
        block += "      {"
        block += latex_escape(edu.get("degree", ""))
        block += " -- "
        block += latex_escape(edu.get("cgpa", ""))
        block += "}{"
        block += latex_escape(edu.get("duration", ""))
        block += "}\n"
        block += "  \\resumeSubHeadingListEnd\n"
        block += "\\vspace{-5pt}"
        return block

    block = "\\noindent\\textbf{" + latex_escape(edu.get("degree", "")) + "}"
    block += " \\hfill \\textbf{" + latex_escape(edu.get("cgpa", "")) + "}\n\n"
    block += "\\noindent "
    block += latex_escape(edu.get("institution", ""))
    block += " -- "
    block += latex_escape(edu.get("duration", ""))
    block += "\n\\vspace{-5pt}"
    return block


def render_leadership(entries, jake=False):
    """Render the Leadership / Extracurricular section as LaTeX."""
    if not entries:
        return ""

    if jake:
        block = "  \\resumeSubHeadingListStart\n"
        for e in entries:
            block += "    \\resumeSubheading\n"
            block += "      {" + latex_escape(e.get("role", "")) + "}"
            block += "{" + latex_escape(e.get("location", "")) + "}\n"
            block += "      {" + latex_escape(e.get("description", "")) + "}"
            block += "{" + latex_escape(e.get("date", "")) + "}\n"
        block += "  \\resumeSubHeadingListEnd\n"
        block += "\\vspace{-5pt}"
        return block

    block = ""
    for e in entries:
        block += "\\noindent\\textbf{" + latex_escape(e.get("role", "")) + "}"
        block += " \\hfill \\textit{" + latex_escape(e.get("date", "")) + "}\n\n"
        block += "\\noindent\\textit{" + latex_escape(e.get("description", "")) + "}"
        block += " \\hfill " + latex_escape(e.get("location", "")) + "\n\n"
    block += "\\vspace{-5pt}"
    return block


def render_certifications(certs, jake=False):
    """Render the Certifications section as LaTeX."""
    if not certs:
        return ""

    if jake:
        block = "  \\begin{itemize}[leftmargin=0.15in, label={}]\n"
        for cert in certs:
            block += "    \\item " + latex_escape(cert.get("name", "")) + ", "
            block += (
                latex_escape(cert.get("organization", ""))
                + " ("
                + latex_escape(str(cert.get("date", "")))
                + ")\n"
            )
        block += "  \\end{itemize}\n"
        block += "\\vspace{-5pt}"
        return block

    block = "\\begin{itemize}\n"
    for cert in certs:
        block += "    \\item " + latex_escape(cert.get("name", "")) + ", "
        block += (
            latex_escape(cert.get("organization", ""))
            + " ("
            + latex_escape(str(cert.get("date", "")))
            + ")\n"
        )
    block += "\\end{itemize}\n"
    block += "\\vspace{-5pt}"
    return block


def render_achievements(achievements, jake=False):
    """Render the Key Achievements section as LaTeX."""
    if not achievements:
        return ""

    if jake:
        block = "  \\begin{itemize}[leftmargin=0.15in, label={}]\n"
        for ach in achievements:
            block += "    \\item " + latex_escape(ach) + "\n"
        block += "  \\end{itemize}\n"
        block += "\\vspace{-5pt}"
        return block

    block = "\\begin{itemize}\n"
    for ach in achievements:
        block += "    \\item " + latex_escape(ach) + "\n"
    block += "\\end{itemize}\n"
    block += "\\vspace{-5pt}"
    return block


def _project_tech_jake(proj):
    """Extract tech stack for Jake-style project heading."""
    tech = proj.get("technologies", [])
    if not tech:
        tech = proj.get("tags", [])
    generic = {
        "analytics", "ml", "machine-learning", "software", "finance",
        "biotech", "freelance", "deployment", "research", "backend",
        "frontend", "full-stack", "data-science", "data",
    }
    tech_names = {
        "python": "Python", "sql": "SQL", "postgresql": "PostgreSQL",
        "mysql": "MySQL", "mongodb": "MongoDB", "fastapi": "FastAPI",
        "flask": "Flask", "django": "Django", "scipy": "SciPy",
        "numpy": "NumPy", "pandas": "Pandas", "xgboost": "XGBoost",
        "lightgbm": "LightGBM", "scikit-learn": "scikit-learn",
        "scikitlearn": "scikit-learn", "docker": "Docker",
        "gcp": "GCP", "gcs": "GCS", "aws": "AWS", "terraform": "Terraform",
        "kubernetes": "Kubernetes", "shap": "SHAP", "tensorflow": "TensorFlow",
        "pytorch": "PyTorch", "react": "React", "plotly": "Plotly",
        "plotly.js": "Plotly.js", "javascript": "JavaScript",
        "node.js": "Node.js", "c#": "C#", "c++": "C++", "c": "C",
        "linux": "Linux", "postgresql": "PostgreSQL", "sqlite": "SQLite",
        "redis": "Redis", "kafka": "Kafka", "pubsub": "Pub/Sub",
        "airflow": "Airflow", "great expectations": "Great Expectations",
        "langchain": "LangChain", "openai": "OpenAI", "reportlab": "ReportLab",
        "scikit-learn": "scikit-learn", "scikitlearn": "scikit-learn",
        "bootstrap 5": "Bootstrap 5", "bootstrap": "Bootstrap",
    }
    result = []
    for t in tech:
        t = t.strip()
        if not t or t.lower() in generic:
            continue
        result.append(tech_names.get(t.lower(), t.title()))
    return ", ".join(result[:6])


def _project_link_label(url):
    if not url:
        return ""
    label = url.split("://", 1)[-1].lstrip("www.")
    return label.rstrip("/")


def _extract_bullets_jake(proj, resume_type):
    """Extract bullets for Jake-style project rendering."""
    highlights = proj.get("highlights", [])
    metrics = proj.get("metrics", {}).get(resume_type, [])
    bullets = highlights + metrics
    return bullets[:4] if len(bullets) > 4 else bullets