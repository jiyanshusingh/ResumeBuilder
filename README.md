# Resume Builder Pro

A company-specific resume builder: generate tailored LaTeX resumes, analyze them
against job descriptions, get ATS scores, and track your job applications — all
from a single web app.

## Features

**Phase 1 — Foundation**
- Core LaTeX resume builder with 5 resume types (analytics, software, biotech, finance, freelance)
- Company profile system with role-specific keywords & metrics
- CI/CD (GitHub Actions), containerization (Docker), Render deployment config

**Phase 2 — Core Features**
- 4 LaTeX templates: `default`, `modern`, `minimalist`, `academic`
- ⚖️ Import a Job Description (text or URL) to auto-extract skills, keywords & metrics
- 📄 On-page `.tex` editor with compile-to-PDF (Tectonic)
- 🔍 16-rule ATS scoring engine (skills, keywords, action verbs, metrics, format…)

**Phase 3 — Intelligence**
- ✨ Bullet enhancement: rewrites weak bullets into strong, quantified ones (local Ollama LLM, with a rule-based fallback)
- 🔍 Simulated ATS parse preview — see exactly what a parser extracts
- ⚖️ Compare the same resume across all saved companies (table + chart)
- 📌 Job application tracker (SQLite) with status funnel, ATS scores, and resume versioning

**Phase 4 — Market Readiness**
- Production server (`app.py`): FastAPI wrapper with a `/health` endpoint, structured logging
- Optional basic auth via `APP_USERNAME` / `APP_PASSWORD` env vars
- Local development with Docker Compose

## Quick Start (local)

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm   # optional, enables spaCy skills extraction
python web_ui.py                          # local Gradio (no auth)
# http://127.0.0.1:7860
```

To enable basic auth locally:

```bash
APP_USERNAME=admin APP_PASSWORD=secret python web_ui.py
```

## Quick Start (production)

Serves the Gradio UI behind FastAPI with `/health` and optional auth:

```bash
APP_USERNAME=admin APP_PASSWORD=secret python app.py
```

Health check: `GET /health` → `{"status":"ok",...}` (always public).

### Docker

```bash
docker compose up --build      # build + run
# or
docker build -t resume-builder .
docker run -p 7860:7860 resume-builder
```

## Building a resume (CLI)

```bash
python resume_builder.py --list                                   # companies
python resume_builder.py --company Zerodha --role "Quant Developer"
```

Outputs `.tex` + `.pdf` to `./output/`.

## Requirements

- Python 3.10+
- [Tectonic](https://tectonic.info/) (`brew install tectonic`) for PDF compilation
- Optional: a local [Ollama](https://ollama.com/library/gemma2) install for LLM bullet enhancement

## Project Structure

```
app.py          # production server (FastAPI + /health + auth)
web_ui.py       # Gradio UI (all tabs)
resume_builder.py   # core template builder
resume_analyzer.py  # PDF parsing + analysis
ats_scorer.py       # 16-rule ATS scoring
jd_importer.py      # JD skill/keyword extraction
parse_preview.py    # simulated ATS parse
compare.py          # cross-company ATS comparison + charts
bullet_enhancer.py  # LLM + rule-based bullet rewriting
tracker.py          # SQLite job application tracker + versioning
config.py           # env-driven settings
data/companies/     # company profiles (JSON)
data/projects/      # project portfolio (JSON)
templates/          # LaTeX templates (Jinja2)
tests/              # pytest suite
```

## Running tests & lint

```bash
pytest tests/ -q
black --check <modules>
isort --check <modules>
```

## Data persistence

SQLite (`data/job_applications.db`) is ephemeral on the Render free tier and is
re-seeded at startup by `tracker.py`. For persistent storage, mount a volume or
swap to a managed DB.