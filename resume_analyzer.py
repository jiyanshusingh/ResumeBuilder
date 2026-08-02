#!/usr/bin/env python3
"""
Resume Analyzer Module
Handles PDF parsing, skill/keyword extraction, ATS scoring, and gap chart generation.
Used by web_ui.py for the Analyze Resume tab.
"""
import os
import re
import json
import tempfile
from typing import List, Dict, Tuple, Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from resume_builder import load_company_profile, DATA_DIR, OUTPUT_DIR


class ResumeAnalyzer:
    """Analyzes a PDF resume against a company/job-role profile."""

    def __init__(self, resume_pdf_path: str):
        self.pdf_path = resume_pdf_path
        self.text: str = ""
        self.word_count: int = 0
        self.sections_found: Dict[str, bool] = {}
        self._load_text()

    def _load_text(self):
        """Extract and cache text from the PDF."""
        if pdfplumber is None:
            raise ImportError("pdfplumber is required: pip install pdfplumber")
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF not found: {self.pdf_path}")

        parts = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                parts.append(t)
        self.text = "\n".join(parts)
        self.word_count = len(self.text.split())
        self._detect_sections()

    def _detect_sections(self):
        """Detect presence of standard resume sections."""
        lower = self.text.lower()
        sections = ["experience", "education", "skills", "projects", "summary",
                     "certifications", "leadership", "awards", "publications"]
        for sec in sections:
            self.sections_found[sec] = bool(re.search(rf'\b{sec}\b', lower))

    def analyze(self, company: str, role: str) -> Dict:
        """
        Full analysis of resume against company/role.
        Returns structured dict with scores, matched/missing lists, and recommendations.
        """
        company_data = load_company_profile(company)
        if role not in company_data.get("job_roles", {}):
            raise ValueError(f"Role '{role}' not found in company '{company}'.")

        role_cfg = company_data["job_roles"][role]
        required_skills = role_cfg.get("required_skills", [])
        keywords = role_cfg.get("keywords", [])

        # Lowercase resume text for matching
        resume_lower = self.text.lower()

        matched_skills = [s for s in required_skills if s.lower() in resume_lower]
        missing_skills = [s for s in required_skills if s.lower() not in resume_lower]

        present_kw = [k for k in keywords if k.lower() in resume_lower]
        missing_kw = [k for k in keywords if k.lower() not in resume_lower]

        # ATS Score: 60% skills, 40% keywords
        skill_ratio = len(matched_skills) / max(len(required_skills), 1)
        kw_ratio = len(present_kw) / max(len(keywords), 1)
        ats_score = round((skill_ratio * 0.6 + kw_ratio * 0.4) * 100, 1)

        # Build recommendations
        recommendations: List[str] = []
        if missing_skills:
            recommendations.append(
                f"Add missing skills to your skills section: {', '.join(missing_skills)}"
            )
        if missing_kw:
            top_missing = missing_kw[:5]
            recommendations.append(
                f"Incorporate these keywords naturally: {', '.join(top_missing)}"
            )

        if ats_score < 50:
            recommendations.append("Low ATS score — major revision needed.")
        elif ats_score < 80:
            recommendations.append("Moderate ATS score — optimize targeted keywords.")
        else:
            recommendations.append("Strong ATS alignment — minimal changes needed.")

        # Length feedback
        if self.word_count < 200:
            recommendations.append("Resume may be too short (aim for 300-500 words).")
        elif self.word_count > 700:
            recommendations.append("Resume may be too long (aim for 300-500 words).")

        # Section feedback
        missing_sections = [s.title() for s, found in self.sections_found.items() if not found]
        if missing_sections:
            recommendations.append(
                f"Consider adding sections: {', '.join(missing_sections[:4])}"
            )

        return {
            "company": company_data["name"],
            "role": role,
            "resume_type": role_cfg["resume_type"],
            "ats_score": ats_score,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "present_keywords": present_kw,
            "missing_keywords": missing_kw,
            "word_count": self.word_count,
            "sections_found": self.sections_found,
            "recommendations": recommendations,
        }


def format_analysis_report(result: Dict) -> str:
    """Format the analysis dict into a human-readable report string."""
    lines = []
    lines.append("=" * 60)
    lines.append("RESUME ANALYSIS REPORT")
    lines.append("=" * 60)
    lines.append(f"\nCompany: {result['company']}")
    lines.append(f"Role: {result['role']}")
    lines.append(f"Resume Type: {result['resume_type']}")

    lines.append("\n" + "-" * 60)
    lines.append("SKILLS MATCH")
    lines.append("-" * 60)
    total_skills = len(result["matched_skills"]) + len(result["missing_skills"])
    lines.append(f"Matched: {len(result['matched_skills'])}/{total_skills} — {', '.join(result['matched_skills']) if result['matched_skills'] else 'None'}")
    lines.append(f"Missing: {len(result['missing_skills'])} — {', '.join(result['missing_skills']) if result['missing_skills'] else 'None'}")

    lines.append("\n" + "-" * 60)
    lines.append("KEYWORD MATCH")
    lines.append("-" * 60)
    total_kw = len(result["present_keywords"]) + len(result["missing_keywords"])
    lines.append(f"Present: {len(result['present_keywords'])}/{total_kw} — {', '.join(result['present_keywords']) if result['present_keywords'] else 'None'}")
    lines.append(f"Missing: {len(result['missing_keywords'])} — {', '.join(result['missing_keywords']) if result['missing_keywords'] else 'None'}")

    lines.append("\n" + "-" * 60)
    lines.append("ATS SCORE")
    lines.append("-" * 60)
    lines.append(f"Overall: {result['ats_score']}%")

    lines.append("\n" + "-" * 60)
    lines.append("RECOMMENDATIONS")
    lines.append("-" * 60)
    for i, rec in enumerate(result["recommendations"], 1):
        lines.append(f"{i}. {rec}")

    lines.append("\n" + "-" * 60)
    lines.append("SECTION PRESENCE")
    lines.append("-" * 60)
    for sec, found in result["sections_found"].items():
        mark = "✅" if found else "⚠️"
        lines.append(f"  {mark} {sec.title()}")

    return "\n".join(lines)


def create_skill_gap_chart(matched_skills: List[str], missing_skills: List[str],
                           present_kw: List[str], missing_kw: List[str]) -> Optional[str]:
    """
    Generate a horizontal bar chart comparing matched vs missing skills and keywords.
    Returns the path to the saved PNG, or None on failure.
    """
    if not HAS_MATPLOTLIB:
        return None

    try:
        fig, axes = plt.subplots(1, 2, figsize=(12, max(6, len(matched_skills + missing_skills) * 0.4)))

        # --- Skills Chart ---
        all_skills = matched_skills + missing_skills
        if all_skills:
            colors = ['#4CAF50'] * len(matched_skills) + ['#F44336'] * len(missing_skills)
            axes[0].barh(range(len(all_skills)), [1] * len(all_skills),
                         color=colors, height=0.6)
            axes[0].set_yticks(range(len(all_skills)))
            axes[0].set_yticklabels(all_skills, fontsize=8)
            axes[0].invert_yaxis()
            axes[0].set_title('Skills', fontweight='bold', fontsize=11)
            axes[0].set_xlabel('Present')
        else:
            axes[0].text(0.5, 0.5, 'No skills data', ha='center', va='center', transform=axes[0].transAxes)
            axes[0].set_title('Skills', fontweight='bold')

        # --- Keywords Chart ---
        all_kw = present_kw + missing_kw
        if all_kw:
            colors_kw = ['#2196F3'] * len(present_kw) + ['#FF9800'] * len(missing_kw)
            axes[1].barh(range(len(all_kw)), [1] * len(all_kw),
                         color=colors_kw, height=0.6)
            axes[1].set_yticks(range(len(all_kw)))
            axes[1].set_yticklabels(all_kw, fontsize=8)
            axes[1].invert_yaxis()
            axes[1].set_title('Keywords', fontweight='bold', fontsize=11)
            axes[1].set_xlabel('Present')
        else:
            axes[1].text(0.5, 0.5, 'No keyword data', ha='center', va='center', transform=axes[1].transAxes)
            axes[1].set_title('Keywords', fontweight='bold')

        # Legend for both
        for ax in axes:
            legend_elements = [
                Patch(facecolor='#4CAF50', label='Matched'),
                Patch(facecolor='#F44336', label='Missing'),
            ] if ax == axes[0] else [
                Patch(facecolor='#2196F3', label='Present'),
                Patch(facecolor='#FF9800', label='Missing'),
            ]
            ax.legend(handles=legend_elements, loc='lower right', fontsize=8)

        plt.tight_layout()
        chart_path = os.path.join(OUTPUT_DIR, "skill_gap_chart.png")
        plt.savefig(chart_path, dpi=150, bbox_inches='tight')
        plt.close()
        return chart_path
    except Exception as e:
        print(f"[resume_analyzer] Chart error: {e}")
        plt.close()
        return None


def analyze_pdf_resume(pdf_file, company: str, role: str) -> Tuple[str, Optional[str]]:
    """
    Convenience function used by web_ui.py.
    Accepts a Gradio file object (or path), extracts text, runs analysis, returns
    (report_string, chart_path).
    """
    # Resolve the PDF file path
    if hasattr(pdf_file, 'name'):
        pdf_path = pdf_file.name
    elif isinstance(pdf_file, str):
        pdf_path = pdf_file
    elif hasattr(pdf_file, 'read'):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_file.read())
            pdf_path = tmp.name
    else:
        return "Error: Could not resolve PDF file.", None

    try:
        analyzer = ResumeAnalyzer(pdf_path)
        result = analyzer.analyze(company, role)
        report = format_analysis_report(result)
        chart_path = create_skill_gap_chart(
            result["matched_skills"],
            result["missing_skills"],
            result["present_keywords"],
            result["missing_keywords"]
        )
        return report, chart_path
    except Exception as e:
        return f"Analysis error: {str(e)}", None
    finally:
        if not hasattr(pdf_file, 'name') and isinstance(pdf_file, str) is False:
            try:
                os.unlink(pdf_path)
            except Exception:
                pass
