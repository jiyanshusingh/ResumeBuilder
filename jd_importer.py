#!/usr/bin/env python3
"""
Job Description Importer Module
Extracts required skills, keywords, and metrics from job descriptions using NLP.

Supports:
1. Paste job description text directly
2. Fetch from URL (LinkedIn, Indeed, company career pages)
3. Auto-extract using spaCy NLP + keyword extraction

Usage:
    from jd_importer import extract_from_jd_text, extract_from_jd_url
    result = extract_from_jd_text("We're looking for a Python developer with FastAPI experience...")
    result = extract_from_jd_url("https://example.com/jobs/123")
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import spacy
    from rake_nltk import Rake

    HAS_SPACY = True
except ImportError:
    spacy = None
    Rake = None
    HAS_SPACY = False


# Common skill categories for classification
SKILL_CATEGORIES = {
    "programming": [
        "python",
        "java",
        "c++",
        "c#",
        "javascript",
        "typescript",
        "sql",
        "r",
        "scala",
        "go",
        "rust",
        "kotlin",
        "swift",
    ],
    "cloud": ["aws", "gcp", "azure", "google cloud", "amazon web services"],
    "ml": [
        "machine learning",
        "deep learning",
        "ml",
        "ai",
        "nlp",
        "computer vision",
        "tensorflow",
        "pytorch",
        "scikit-learn",
        "xgboost",
        "statistical modeling",
    ],
    "backend": ["fastapi", "flask", "django", "node.js", "rest api", "graphql"],
    "devops": ["docker", "kubernetes", "ci/cd", "terraform", "ansible", "jenkins"],
    "data": ["pandas", "numpy", "sql", "postgresql", "mysql", "mongodb", "bigquery"],
    "frontend": ["react", "angular", "vue", "html", "css", "javascript"],
    "tools": ["git", "docker", "kubernetes", "tableau", "power bi", "looker"],
    "analytics": [
        "a/b testing",
        "statistics",
        "data analysis",
        "statistical modeling",
        "bayesian",
        "hypothesis testing",
        "regression",
        "forecasting",
    ],
    "finance": [
        "trading",
        "quantitative",
        "risk management",
        "algorithmic trading",
        "financial modeling",
        "derivatives",
        "portfolio management",
    ],
    "biotech": [
        "biopython",
        "biotechnology",
        "bioinformatics",
        "genomics",
        "proteomics",
    ],
}

# Common action verbs found in job descriptions
ACTION_VERBS = [
    "develop",
    "build",
    "implement",
    "design",
    "create",
    "manage",
    "lead",
    "execute",
    "analyze",
    "optimize",
    "improve",
    "deploy",
    "collaborate",
    "coordinate",
    "mentor",
    "advise",
    "consult",
    "recommend",
    "evaluate",
    "research",
    "test",
    "validate",
    "automate",
    "streamline",
    "integrate",
    "configure",
    "maintain",
]

# Metrics patterns commonly found in job descriptions
METRIC_PATTERNS = [
    r"(\d+[\d,]*\s*%)",  # Percentages: 25%, 50%
    r"(₹\s*\d+[\d,]*\s*(?:k|K|lakh|crore)?)",  # Indian Rupees
    r"(\$\s*\d+[\d,]*\s*(?:k|K|m|M)?)",  # US Dollars
    r"(\d+[\d,]*\s*(?:users|trades|requests|transactions|records))",
    r"(\d+[\d,]*\s*(?:%+))",  # Multiple % signs
]


def fetch_url_content(url: str, timeout: int = 10) -> str:
    """
    Fetch HTML content from a URL and extract text.
    Handles common job boards.
    """
    if requests is None:
        raise ImportError("requests is required for URL fetch: pip install requests")
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 is required: pip install beautifulsoup4")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch URL: {e}")

    soup = BeautifulSoup(response.content, "html.parser")

    # Remove script, style, and navigation elements
    for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
        element.decompose()

    # Try to find main content area
    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_="job-description")
    )
    content = main_content if main_content else soup

    text = content.get_text(separator="\n", strip=True)
    return text


def preprocess_text(text: str) -> str:
    """Clean and normalize text for NLP processing."""
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_skills_semantic(text: str) -> List[str]:
    """Semantically detect skills/phrases in a JD via embeddings (optional).

    Catches paraphrased skills (e.g. "forecasting" for "time series") that
    exact matching misses. Returns [] when the offline model is unavailable.
    """
    try:
        import embeddings
    except ImportError:
        return []
    if not embeddings.available():
        return []

    text_lower = text.lower()
    vocab = [
        skill
        for skills in SKILL_CATEGORIES.values()
        for skill in skills
        if skill.lower() not in text_lower
    ]
    matched = []
    for skill in vocab:
        sim = embeddings.similarity(skill, text)
        if sim is not None and sim >= 0.5:
            matched.append(skill)
    return matched


def extract_skills_nlp(text: str) -> List[str]:
    """
    Extract skills from job description text using NLP + pattern matching.
    Falls back to keyword matching if spaCy is not available.
    """
    if HAS_SPACY:
        try:
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            print(
                "WARNING: spaCy model 'en_core_web_sm' not found. "
                "Install with: python -m spacy download en_core_web_sm"
            )
            HAS_SPACY_LOCAL = False
        else:
            HAS_SPACY_LOCAL = True
    else:
        HAS_SPACY_LOCAL = False

    text_lower = text.lower()

    # Extract skills using known skill database
    found_skills = []
    for category, skills in SKILL_CATEGORIES.items():
        for skill in skills:
            if skill in text_lower:
                found_skills.append(skill)

    # Deduplicate while preserving order
    seen = set()
    unique_skills = []
    for skill in found_skills:
        if skill not in seen:
            seen.add(skill)
            unique_skills.append(skill)

    # If spaCy is available, try to extract additional entities
    if HAS_SPACY_LOCAL:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ in ["ORG", "PRODUCT", "LANGUAGE", "PRODUCT"]:
                ent_text = ent.text.lower()
                if len(ent_text) > 2 and ent_text not in seen:
                    # Check if it looks like a skill
                    if any(char.isalpha() for char in ent_text):
                        unique_skills.append(ent.text)
                        seen.add(ent_text)

    # Semantic pass (embeddings): catch paraphrased skills
    for skill in extract_skills_semantic(text):
        if skill not in seen:
            unique_skills.append(skill)
            seen.add(skill.lower())

    return unique_skills


def extract_keywords(text: str) -> List[str]:
    """Extract important keywords using RAKE (Rapid Automatic Keyword Extraction)."""
    if not HAS_SPACY:
        # Fallback: simple keyword extraction
        return _extract_keywords_fallback(text)

    try:
        r = Rake()
        r.extract_keywords_from_text(text)
        ranked = r.get_ranked_phrases()

        # Filter to relevant keywords
        keywords = []
        for phrase in ranked[:20]:
            phrase_lower = phrase.lower()
            # Skip too short or too long phrases
            if 2 <= len(phrase.split()) <= 4:
                keywords.append(phrase)

        return keywords[:15]
    except Exception:
        return _extract_keywords_fallback(text)


def _extract_keywords_fallback(text: str) -> List[str]:
    """Simple keyword extraction fallback when spaCy is not available."""
    # Extract common technical terms and phrases
    text_lower = text.lower()

    # Technical terms and phrases
    tech_terms = []

    # Find multi-word technical phrases
    patterns = [
        r"(?:machine learning|deep learning|statistical model)",
        r"(?:data (?:analysis|science|engineering|pipeline|visualization))",
        r"(?:cloud (?:platform|infrastructure|computing|services))",
        r"(?:machine learning|ML) (?:engineering|model|pipeline|workflow)",
        r"(?:A/B|AB|experiment) (?:testing|analysis)",
        r"(?:full.?stack|backend|frontend) (?:developer|engineer)",
        r"(?:CI/CD|DevOps) (?:pipeline|workflow)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        tech_terms.extend(matches)

    # Extract single-word technical keywords
    common_keywords = [
        "python",
        "sql",
        "docker",
        "kubernetes",
        "aws",
        "gcp",
        "azure",
        "fastapi",
        "flask",
        "react",
        "angular",
        "tensorflow",
        "pytorch",
        "xgboost",
        "pandas",
        "numpy",
        "postgresql",
        "mongodb",
        "git",
        "linux",
        "scala",
        "java",
        "javascript",
        "typescript",
        "statistics",
        "analytics",
        "quantitative",
        "trading",
        "modeling",
        "deployment",
    ]

    for keyword in common_keywords:
        if keyword in text_lower:
            tech_terms.append(keyword.title())

    # Deduplicate
    seen = set()
    unique = []
    for term in tech_terms:
        if term.lower() not in seen:
            seen.add(term.lower())
            unique.append(term)

    return unique[:15]


def extract_metrics(text: str) -> List[str]:
    """Extract quantifiable metrics from job description text."""
    metrics = []
    for pattern in METRIC_PATTERNS:
        matches = re.findall(pattern, text)
        metrics.extend(matches)

    # Also extract numbers with context (e.g., "5 years", "3+ years")
    years_pattern = r"(\d+\+?\s*(?:year|years|Years|YEARs))"
    years_matches = re.findall(years_pattern, text)
    metrics.extend(years_matches)

    # Experience level extraction
    exp_patterns = [
        r"(entry.?level)",
        r"(mid.?level)",
        r"(senior)",
        r"(lead)",
        r"(principal)",
    ]
    for pattern in exp_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        metrics.extend(m.lower().title() for m in matches if m)

    # Deduplicate
    return list(set(metrics))[:15]


def classify_resume_type(skills: List[str]) -> str:
    """
    Determine the best resume type based on extracted skills.
    Returns one of: analytics, software, biotech, finance, freelance
    """
    text_lower = " ".join(skills).lower()

    # Count category matches
    category_scores = {}
    for category, items in SKILL_CATEGORIES.items():
        category_scores[category] = sum(1 for item in items if item in text_lower)

    # Map categories to resume types
    type_mapping = {
        "ml": "analytics",
        "analytics": "analytics",
        "data": "analytics",
        "backend": "software",
        "frontend": "software",
        "devops": "software",
        "cloud": "software",
        "tools": "software",
        "finance": "finance",
        "biotech": "biotech",
        "programming": "software",
    }

    # Find the best matching category
    best_category = max(category_scores, key=category_scores.get)
    if category_scores[best_category] > 0:
        return type_mapping.get(best_category, "freelance")

    return "freelance"


def extract_from_jd_text(text: str) -> Dict:
    """
    Extract structured job data from pasted job description text.

    Returns:
        dict with keys: required_skills, keywords, emphasize_metrics,
                        resume_type, action_verbs
    """
    text = preprocess_text(text)

    skills = extract_skills_nlp(text)
    keywords = extract_keywords(text)
    metrics = extract_metrics(text)
    resume_type = classify_resume_type(skills + keywords)

    # Extract action verbs mentioned or implied
    text_lower = text.lower()
    action_verbs = [verb for verb in ACTION_VERBS if verb in text_lower][:10]

    return {
        "required_skills": skills,
        "keywords": keywords,
        "emphasize_metrics": metrics,
        "resume_type": resume_type,
        "action_verbs": action_verbs,
        "extracted_from": "text",
    }


def extract_from_jd_url(url: str) -> Dict:
    """
    Extract structured job data from a job description URL.
    Fetches the page, extracts text, then runs NLP extraction.

    Returns:
        dict with keys: required_skills, keywords, emphasize_metrics,
                        resume_type, action_verbs
    """
    if BeautifulSoup is None:
        raise ImportError(
            "beautifulsoup4 and requests are required: "
            "pip install beautifulsoup4 requests"
        )

    text = fetch_url_content(url)
    result = extract_from_jd_text(text)
    result["extracted_from"] = "url"
    result["source_url"] = url
    return result


def extract_from_jd(file_path: str) -> Dict:
    """
    Extract structured job data from a file (PDF or text).

    Returns:
        dict with keys: required_skills, keywords, emphasize_metrics,
                        resume_type, action_verbs
    """
    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumber is required for PDF: pip install pdfplumber")

        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts)
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

    result = extract_from_jd_text(text)
    result["extracted_from"] = ext

    return result


def format_jd_result(result: Dict) -> str:
    """Format the extraction result for display."""
    lines = []
    lines.append(f"Resume Type: {result['resume_type']}")
    lines.append(f"Source: {result.get('extracted_from', 'text')}")
    if "source_url" in result:
        lines.append(f"URL: {result['source_url']}")

    lines.append(f"\nRequired Skills ({len(result['required_skills'])}):")
    for skill in result["required_skills"]:
        lines.append(f"  - {skill}")

    lines.append(f"\nKeywords ({len(result['keywords'])}):")
    for kw in result["keywords"]:
        lines.append(f"  - {kw}")

    lines.append(f"\nMetrics/Emphasis ({len(result['emphasize_metrics'])}):")
    for metric in result["emphasize_metrics"]:
        lines.append(f"  - {metric}")

    if result.get("action_verbs"):
        lines.append(f"\nAction Verbs ({len(result['action_verbs'])}):")
        for verb in result["action_verbs"]:
            lines.append(f"  - {verb}")

    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python jd_importer.py <text|url|file> <content>")
        sys.exit(1)

    mode = sys.argv[1]
    content = " ".join(sys.argv[2:])

    if mode == "text":
        result = extract_from_jd_text(content)
    elif mode == "url":
        result = extract_from_jd_url(content)
    elif mode == "file":
        result = extract_from_jd(content)
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)

    print(format_jd_result(result))
    print("\n" + "=" * 60)
    print("JSON output:")
    print(json.dumps(result, indent=2))
