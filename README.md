# Company-Specific Resume Builder

A tool that generates LaTeX resumes tailored to specific companies and job roles, using your project portfolio, certificates, and achievements.

## Quick Start

```bash
# List available company profiles
python3 resume_builder.py --list

# Build a resume for a specific company + role
python3 resume_builder.py --company Zerodha --role "Quant Developer"

# Build for Microsoft software role
python3 resume_builder.py --company Microsoft --role "Software Engineer"

# Build for a biotech company
python3 resume_builder.py --company Biocon --role "Associate Data Scientist - Biotech"
```

## Output

Generated resumes are saved to `./output/` as both `.tex` (editable source) and `.pdf` (final resume).

## Adding New Companies

Add `data/companies/<company-name>.json`:

```json
{
  "name": "Company Name",
  "website": "https://company.com",
  "job_roles": {
    "Job Title": {
      "resume_type": "analytics|software|biotech|finance|freelance",
      "required_skills": ["skill1", "skill2"],
      "keywords": ["keyword1", "keyword2"],
      "emphasize_metrics": ["metric 1", "metric 2"]
    }
  }
}
```

Supported `resume_type` values:
- `analytics` - Emphasizes statistical methods, A/B testing
- `software` - Focuses on deployment, system design, full-stack
- `biotech` - Highlights domain expertise, research, modeling
- `finance` - Stresses trading systems, ROI, risk modeling
- `freelance` - Generalist summary for client work

## How It Works

1. **Profile data** (`data/profile.json`): Your static info (experience, skills, certs, projects)
2. **Company profiles** (`data/companies/`): Job-specific keyword maps and resume types
3. **Template engine** (`templates/resume_template.tex.j2`): LaTeX template with placeholder replacement

The builder:
- Ranks your projects by relevance to the job keywords
- Filters certificates to those most relevant
- Reorders skills by category based on resume type
- Generates a tailored summary based on the role
- Outputs both `.tex` source (for manual edits) and compiled `.pdf`

## Requirements

- Python 3.x (`--break-system-packages` may be needed for pip)
- [Tectonic](https://tectonic.info/) (`brew install tectonic`) for LaTeX compilation
- `jinja2` Python package

## Project Data

Projects are defined in `data/projects/` as individual JSON files with:
- `name`, `github`, `tags` - identification + categorization  
- `short_description`, `detailed_description` - copy for different resume types
- `metrics` - per-resume-type metric mappings
- `highlights` - always-shown bullet points
- `technologies` - tech stack
- `links` - code + live URLs
