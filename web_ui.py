#!/usr/bin/env python3
"""
Web UI for Company-Specific Resume Builder
Uses Gradio for a simple interface to:
1. Add/edit company details via form
2. Generate tailored resumes with PDF output
3. Download .tex source and .pdf resume
"""
import gradio as gr
import json
import os
import re
import subprocess
from resume_builder import (
    build_resume, load_company_profile, list_companies,
    DATA_DIR, OUTPUT_DIR
)
from resume_builder import latex_escape, rank_projects, extract_bullets, build_experience_block

# Reuse the builder core, but with Gradio I/O

COMPANY_DIR = os.path.join(DATA_DIR, "companies")
os.makedirs(COMPANY_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

RESUME_TYPES = ["analytics", "software", "biotech", "finance", "freelance"]


def slugify(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]+', '_', s.lower()).strip('_')


def get_company_names():
    files = [f for f in os.listdir(COMPANY_DIR) if f.endswith(".json")]
    return [f.replace(".json", "").replace("_", " ").title() for f in files]


def load_profile():
    path = os.path.join(DATA_DIR, "profile.json")
    with open(path) as f:
        return json.load(f)


def save_company(name, website, role_name, resume_type, required_skills, keywords, emphasize_metrics):
    """Save a new company profile."""
    if not name or not role_name:
        return "Error: Company name and role name are required."

    slug = slugify(name)
    role_key = role_name.strip()
    path = os.path.join(COMPANY_DIR, f"{slug}.json")

    # Load existing or create new
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    else:
        data = {"name": name.title(), "website": website, "job_roles": {}}

    # Parse skills and keywords
    skills = [s.strip() for s in required_skills.split(",") if s.strip()]
    kws = [k.strip() for k in keywords.split(",") if k.strip()]
    metrics = [m.strip() for m in emphasize_metrics.split(",") if m.strip()]

    data["job_roles"][role_key] = {
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


def generate_resume_ui(company_display, role):
    """Generate a resume for a company + role."""
    # Try loading by slugified name first, then original
    slug = slugify(company_display)
    try:
        company = load_company_profile(company_display)
    except FileNotFoundError:
        try:
            company = load_company_profile(slug)
        except FileNotFoundError:
            # Try matching by display name
            safe_slug = slug
            for fname in os.listdir(COMPANY_DIR):
                if fname.replace(".json", "") == safe_slug or \
                   fname.replace(".json", "").replace("_", " ") == company_display.lower():
                    company = load_company_profile(fname.replace(".json", ""))
                    break
            else:
                return None, None, f"Company not found: {company_display}"

    if role not in company.get("job_roles", {}):
        available = list(company.get("job_roles", {}).keys())
        return None, None, f"Role not found. Available roles: {available}"

    # Generate resume into output
    safe_company = slugify(company_display)
    safe_role = slugify(role)
    tex_path = os.path.join(OUTPUT_DIR, f"resume_{safe_company}_{safe_role}.tex")
    pdf_path = os.path.join(OUTPUT_DIR, f"resume_{safe_company}_{safe_role}.pdf")

    try:
        build_resume(company_display, role)
    except Exception as e:
        return None, None, f"Build error: {str(e)}"

    if not os.path.exists(tex_path):
        return None, None, "Failed to generate .tex file."

    with open(tex_path) as f:
        tex_content = f.read()

    pdf_available = os.path.exists(pdf_path)
    return tex_content, pdf_path if pdf_available else None, f"Generated: {tex_path}"


def name_from_display(display_name):
    """Convert a display name back to the slug filename."""
    # Try common variations
    slug = slugify(display_name)
    return slug


def refresh_company_dropdown():
    """Refresh the company dropdown options."""
    names = get_company_names()
    return gr.update(choices=names, value=names[0] if names else "")


def list_all_companies():
    """List all companies and roles in a text area."""
    companies_dir = os.path.join(DATA_DIR, "companies")
    result = []
    for fname in sorted(os.listdir(companies_dir)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(companies_dir, fname)) as f:
            data = json.load(f)
        result.append(f"**{data['name']}** ({data.get('website', 'N/A')})")
        for role, cfg in data.get("job_roles", {}).items():
            result.append(f"  - {role} [{cfg['resume_type']}]")
        result.append("")
    return "\n".join(result) if result else "No companies saved yet."


# Gradio Interface
with gr.Blocks(title="Resume Builder") as demo:
    gr.Markdown("# Company-Specific Resume Builder")
    gr.Markdown("*Generate tailored LaTeX resumes for any company + role combination.*")

    with gr.Tabs():
        # Tab 1: Add Company
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

            save_btn.click(
                fn=save_company,
                inputs=[company_name, company_website, role_name, resume_type,
                        required_skills, keywords, emphasize_metrics],
                outputs=save_output,
            )

        # Tab 2: Generate Resume
        with gr.Tab("📄 Generate Resume"):
            gr.Markdown("### Generate a tailored resume")
            with gr.Row():
                company_dropdown = gr.Dropdown(choices=get_company_names(), label="Company", value=get_company_names()[0] if get_company_names() else "")
                role_dropdown = gr.Textbox(label="Job Role", placeholder="Enter the role name (e.g. Quant Developer)")

            gen_btn = gr.Button("🚀 Generate Resume", variant="primary")
            with gr.Row():
                tex_display = gr.Textbox(label=".tex Source", lines=20, interactive=False)
                status_output = gr.Textbox(label="Status", interactive=False)

            pdf_file = gr.File(label="📥 Download PDF", visible=False)
            tex_file = gr.File(label="📥 Download .tex", visible=False)

            def generate_wrapper(company_display, role):
                tex_content, pdf_path, status = generate_resume_ui(company_display, role)
                visible_tex = pdf_visible = tex_visible = False

                outputs = [
                    gr.update(value=tex_content or "No output"),
                    gr.update(value=status),
                ]

                # Prepare file downloads
                safe_company = slugify(company_display)
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

            gen_btn.click(
                fn=generate_wrapper,
                inputs=[company_dropdown, role_dropdown],
                outputs=[tex_display, status_output, pdf_file, tex_file],
            )

            refresh_btn = gr.Button("🔄 Refresh Company List")
            refresh_btn.click(
                fn=lambda: gr.update(choices=get_company_names()),
                inputs=None,
                outputs=company_dropdown,
            )

        # Tab 3: Manage Companies
        with gr.Tab("📋 Manage Companies"):
            gr.Markdown("### Saved Company Profiles")
            refresh_list_btn = gr.Button("🔄 Refresh List")
            company_list_display = gr.Textbox(label="Companies", value=list_all_companies(), lines=25, interactive=False)

            refresh_list_btn.click(fn=list_all_companies, inputs=None, outputs=company_list_display)

            with gr.Row():
                delete_company = gr.Textbox(label="Delete Company (by name)")
                delete_btn = gr.Button("🗑️ Delete Company", variant="danger")

                def delete_company_fn(name):
                    slug = slugify(name)
                    path = os.path.join(COMPANY_DIR, f"{slug}.json")
                    if os.path.exists(path):
                        os.remove(path)
                        return f"Deleted: {name}"
                    return f"Not found: {name}"

                delete_btn.click(fn=delete_company_fn, inputs=delete_company, outputs=gr.Textbox(label="Delete Status"))


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
    )
