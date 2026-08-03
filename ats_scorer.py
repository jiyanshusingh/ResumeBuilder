#!/usr/bin/env python3
"""
ATS (Applicant Tracking System) Scoring Module
Provides comprehensive resume scoring with 15+ rules.

Used by resume_analyzer.py and web_ui.py for the Analyze Resume and Optimize tabs.
"""
import re
import os
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, field

from resume_builder import load_company_profile
from config import OUTPUT_DIR


@dataclass
class ATSRuleResult:
    """Result of a single ATS rule evaluation."""
    rule_name: str
    passed: bool
    score: float  # 0-100
    weight: float  # 0-1
    feedback: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class ATSScorer:
    """
    Comprehensive ATS scoring engine with 15+ rules.
    
    Each rule evaluates a specific aspect of ATS-friendliness:
    1. Skills match (required skills present)
    2. Keyword density (target keywords found)
    3. Document format (PDF/TXT preferred over DOCX)
    4. Section headers (standard resume sections present)
    5. Section completeness (all key sections have content)
    6. Action verbs (strong action verbs used in bullets)
    7. Metrics presence (quantifiable achievements)
    8. Resume length (optimal word count)
    9. Company name match (exact company name in resume)
    10. Role title match (exact role title in resume)
    11. Education relevance (relevant degree field)
    12. Certification match (relevant certifications)
    13. Industry keyword match (industry-specific terms)
    14. Soft skills detection (communication, leadership, etc.)
    15. ATS-friendly formatting (no tables, images, headers/footers)
    16. Contact info completeness (email, phone, LinkedIn, GitHub)
    """

    # Common action verbs that strengthen resumes
    ACTION_VERBS = [
        "managed", "led", "built", "created", "developed", "designed",
        "implemented", "deployed", "optimized", "improved", "increased",
        "reduced", "launched", "engineered", "analyzed", "designed",
        "established", "generated", "initiated", "coordinated", "executed",
        "produced", "supervised", "trained", "transformed", "converted",
    ]

    # Soft skills keywords
    SOFT_SKILLS = [
        "communication", "leadership", "teamwork", "collaboration",
        "problem-solving", "critical thinking", "adaptability",
        "time management", "organization", "attention to detail",
        "creativity", "critical thinking", "strategic", "analytical",
    ]

    # ATS-unfriendly patterns (complex formatting that breaks ATS parsing)
    ATS_UNFRIENDLY_PATTERNS = [
        r"\\begin\{tabular\}",  # Tables
        r"\\begin\{longtable\}",  # Long tables
        r"\\includegraphics",  # Images
        r"\\pagestyle\{header\}",  # Headers
        r"\\pagestyle\{footer\}",  # Footers
        r"<table",  # HTML tables
        r"<img",  # HTML images
    ]

    def __init__(self, resume_text: str, file_extension: str = ".pdf"):
        self.text = resume_text
        self.text_lower = resume_text.lower()
        self.word_count = len(resume_text.split())
        self.file_ext = file_extension.lower()
        self.rules: List[ATSRuleResult] = []

    def _check_section(self, section: str) -> bool:
        """Check if a section header is present in the resume."""
        patterns = [
            rf"\\b{section}\\b",
            rf"\\b{section}s\\b",
            rf"\\b{section.title()}\\b",
            rf"\\b{section.title()}s\\b",
            rf"\\b{section.capitalize()}\\b",
        ]
        return any(re.search(p, self.text_lower) for p in patterns)

    def _check_action_verb_usage(self) -> Tuple[int, int]:
        """Count action verbs used in the resume text."""
        # Split into bullet-like lines
        lines = self.text_lower.split('\n')
        verb_count = 0
        total_bullet_lines = 0

        for line in lines:
            line = line.strip().lstrip('•*-').strip()
            if len(line) < 10:
                continue
            total_bullet_lines = max(total_bullet_lines, 1)
            first_word = line.split()[0] if line.split() else ""
            if any(verb in first_word for verb in self.ACTION_VERBS):
                verb_count += 1

        return verb_count, total_bullet_lines

    def _check_metrics(self) -> int:
        """Count quantifiable metrics in the resume (numbers with units)."""
        patterns = [
            r"\d+%",  # Percentages
            r"\\₹\d+[,\d]*",  # Indian rupees
            r"\$ \d+[,\d]*",  # US dollars
            r"\d+\+?",  # Plain numbers
        ]
        count = 0
        for pattern in patterns:
            count += len(re.findall(pattern, self.text))
        return count

    def _extract_skills_from_text(self) -> List[str]:
        """Extract potential skills from the resume text using pattern matching."""
        # Common skill keywords
        skill_keywords = [
            "python", "sql", "java", "c++", "javascript", "typescript",
            "react", "angular", "vue", "node.js", "django", "flask",
            "fastapi", "docker", "kubernetes", "aws", "gcp", "azure",
            "machine learning", "deep learning", "nlp", "computer vision",
            "statistics", "pandas", "numpy", "scikit-learn", "tensorflow",
            "pytorch", "xgboost", "postgresql", "mysql", "mongodb",
            "git", "ci/cd", "agile", "scrum", "tableau", "power bi",
            "excel", "r", "scala", "go", "rust", "kotlin", "swift",
            "linux", "bash", "terraform", "ansible", "spark", "hadoop",
        ]
        found = []
        for skill in skill_keywords:
            if skill in self.text_lower:
                found.append(skill)
        return found

    def score(self, company: str, role: str) -> Dict[str, Any]:
        """
        Run all ATS rules and return comprehensive scoring results.
        """
        company_data = load_company_profile(company)
        role_cfg = company_data["job_roles"][role]
        required_skills = role_cfg.get("required_skills", [])
        keywords = role_cfg.get("keywords", [])

        self.rules = []

        # Rule 1: Skills match
        self._rule_skills_match(required_skills)

        # Rule 2: Keyword density
        self._rule_keyword_density(keywords)

        # Rule 3: Document format
        self._rule_document_format()

        # Rule 4: Section headers
        self._rule_section_headers()

        # Rule 5: Section completeness
        self._rule_section_completeness()

        # Rule 6: Action verbs
        self._rule_action_verbs()

        # Rule 7: Metrics presence
        self._rule_metrics()

        # Rule 8: Resume length
        self._rule_resume_length()

        # Rule 9: Company name match
        self._rule_company_name_match(company_data["name"])

        # Rule 10: Role title match
        self._rule_role_match(role)

        # Rule 11: Education relevance
        self._rule_education_relevance(company)

        # Rule 12: Certification match
        self._rule_certification_match(keywords)

        # Rule 13: Industry keyword match
        self._rule_industry_keywords(keywords)

        # Rule 14: Soft skills
        self._rule_soft_skills()

        # Rule 15: ATS-friendly formatting
        self._rule_ats_friendly_format()

        # Rule 16: Contact info completeness
        self._rule_contact_info()

        return self._compile_results()

    def _rule_skills_match(self, required_skills: List[str]):
        """Rule 1: Check if required skills are present in resume."""
        matched = [s for s in required_skills if s.lower() in self.text_lower]
        missing = [s for s in required_skills if s.lower() not in self.text_lower]
        ratio = len(matched) / max(len(required_skills), 1)
        score = ratio * 100
        passed = ratio >= 0.5
        feedback = f"Matched {len(matched)}/{len(required_skills)} required skills"
        if missing:
            feedback += f". Missing: {', '.join(missing[:5])}"
        self.rules.append(ATSRuleResult(
            rule_name="Skills Match",
            passed=passed,
            score=score,
            weight=0.15,
            feedback=feedback,
            details={"matched": matched, "missing": missing}
        ))

    def _rule_keyword_density(self, keywords: List[str]):
        """Rule 2: Check keyword density (not just presence, but frequency)."""
        present = []
        missing = []
        total_occurrences = 0
        for kw in keywords:
            count = self.text_lower.count(kw.lower())
            if count > 0:
                present.append(kw)
                total_occurrences += count
            else:
                missing.append(kw)

        ratio = len(present) / max(len(keywords), 1)
        # Bonus for high density (more than 2 occurrences per keyword)
        density_bonus = min(total_occurrences / max(len(keywords), 1) / 2, 1.0)
        score = min(ratio * 100 + density_bonus * 20, 100)
        passed = ratio >= 0.5
        feedback = f"Found {len(present)}/{len(keywords)} keywords ({total_occurrences} total occurrences)"
        if missing:
            feedback += f". Missing: {', '.join(missing[:5])}"
        self.rules.append(ATSRuleResult(
            rule_name="Keyword Density",
            passed=passed,
            score=score,
            weight=0.15,
            feedback=feedback,
            details={"present": present, "missing": missing, "total_occurrences": total_occurrences}
        ))

    def _rule_document_format(self):
        """Rule 3: Check document format (PDF preferred)."""
        score = 100
        feedback = "Format: PDF"
        if self.file_ext == ".pdf":
            score = 100
            passed = True
        elif self.file_ext in [".txt", ".rtf"]:
            score = 80
            passed = True
            feedback = f"Format: {self.file_ext} (acceptable, PDF preferred)"
        else:
            score = 40
            passed = False
            feedback = f"Format: {self.file_ext} (ATS may have trouble parsing this format)"
        self.rules.append(ATSRuleResult(
            rule_name="Document Format",
            passed=passed,
            score=score,
            weight=0.05,
            feedback=feedback
        ))

    def _rule_section_headers(self):
        """Rule 4: Check for standard resume section headers."""
        standard_sections = ["experience", "education", "skills", "projects"]
        found_sections = [s for s in standard_sections if self._check_section(s)]
        missing_sections = [s for s in standard_sections if not self._check_section(s)]
        ratio = len(found_sections) / len(standard_sections)
        score = ratio * 100
        passed = ratio >= 0.75
        feedback = f"Found {len(found_sections)}/{len(standard_sections)} key sections"
        if missing_sections:
            feedback += f". Missing: {', '.join(missing_sections)}"
        self.rules.append(ATSRuleResult(
            rule_name="Section Headers",
            passed=passed,
            score=score,
            weight=0.05,
            feedback=feedback,
            details={"found": found_sections, "missing": missing_sections}
        ))

    def _rule_section_completeness(self):
        """Rule 5: Check that each section has adequate content."""
        sections = ["experience", "education", "skills"]
        issues = []
        for section in sections:
            if self._check_section(section):
                # Find the section text
                patterns = [
                    rf"\\b{section}\\b[\\s\\S]*?(?=(?:\\n\\s*\\n)?(?:experience|education|skills|projects|certifications|achievements|summary)[a-z]*\\b)",
                    rf"\\b{section.title()}\\b[\\s\\S]*?(?=(?:\\n\\s*\\n)?(?:Experience|Education|Skills|Projects|Certifications|Key Achievements|Summary)[a-z]*\\b)",
                ]
                section_text = ""
                for pattern in patterns:
                    match = re.search(pattern, self.text_lower)
                    if match:
                        section_text = match.group(0)
                        break
                word_count = len(section_text.split())
                if word_count < 20:
                    issues.append(f"{section.title()} section is short ({word_count} words)")
            else:
                issues.append(f"{section.title()} section missing")

        score = 100 if not issues else max(100 - len(issues) * 25, 0)
        passed = score >= 75
        feedback = f"{len(issues)} section issues"
        if issues:
            feedback += f": {'; '.join(issues)}"
        self.rules.append(ATSRuleResult(
            rule_name="Section Completeness",
            passed=passed,
            score=score,
            weight=0.05,
            feedback=feedback
        ))

    def _rule_action_verbs(self):
        """Rule 6: Check for action verbs in bullet points."""
        verb_count, bullet_count = self._check_action_verb_usage()
        if bullet_count == 0:
            score = 0
            passed = False
            feedback = "No bullet points with action verbs found"
        else:
            ratio = verb_count / bullet_count
            score = ratio * 100
            passed = ratio >= 0.5
            feedback = f"Found {verb_count} action verbs in {bullet_count} bullet-like lines"

        self.rules.append(ATSRuleResult(
            rule_name="Action Verbs",
            passed=passed,
            score=score,
            weight=0.05,
            feedback=feedback,
            details={"verb_count": verb_count, "bullet_count": bullet_count}
        ))

    def _rule_metrics(self):
        """Rule 7: Check for quantifiable metrics in resume."""
        metric_count = self._check_metrics()
        score = min(metric_count * 20, 100)
        passed = metric_count >= 3
        feedback = f"Found {metric_count} quantifiable metrics"
        if metric_count < 3:
            feedback += " (aim for 5+ for optimal impact)"
        self.rules.append(ATSRuleResult(
            rule_name="Metrics Presence",
            passed=passed,
            score=score,
            weight=0.08,
            feedback=feedback
        ))

    def _rule_resume_length(self):
        """Rule 8: Check resume length (200-700 words optimal)."""
        if self.word_count < 150:
            score = 20
            passed = False
            feedback = f"Resume too short ({self.word_count} words, aim for 300-500)"
        elif self.word_count > 800:
            score = 30
            passed = False
            feedback = f"Resume too long ({self.word_count} words, aim for 300-500)"
        else:
            score = 100
            passed = True
            feedback = f"Optimal length ({self.word_count} words)"

        self.rules.append(ATSRuleResult(
            rule_name="Resume Length",
            passed=passed,
            score=score,
            weight=0.05,
            feedback=feedback
        ))

    def _rule_company_name_match(self, company_name: str):
        """Rule 9: Check if company name appears in resume (relevant for cover letter context)."""
        if company_name.lower() in self.text_lower:
            score = 100
            passed = True
            feedback = f"Company name '{company_name}' found in resume"
        else:
            score = 0
            passed = False
            feedback = f"Company name '{company_name}' not mentioned in resume"
        self.rules.append(ATSRuleResult(
            rule_name="Company Name Match",
            passed=passed,
            score=score,
            weight=0.03,
            feedback=feedback
        ))

    def _rule_role_match(self, role: str):
        """Rule 10: Check if role title or similar appears in resume."""
        # Check for role or common variations
        role_variations = [role.lower()]
        # Handle multi-word roles (check for partial matches)
        role_words = role.lower().split()
        role_variations.extend(role_words)

        # Common role mappings
        role_mapping = {
            "software engineer": ["developer", "sde", "programmer"],
            "data scientist": ["data analyst", "ml engineer", "analytics"],
            "quant developer": ["quant", "trading", "financial engineer"],
        }
        for key, aliases in role_mapping.items():
            if key in role.lower():
                role_variations.extend(aliases)

        found_roles = []
        for variation in role_variations:
            if variation in self.text_lower:
                found_roles.append(variation)

        score = 100 if found_roles else 0
        passed = bool(found_roles)
        feedback = f"Role-related terms found: {', '.join(found_roles)}" if found_roles else "No role-specific terms found"
        self.rules.append(ATSRuleResult(
            rule_name="Role Title Match",
            passed=passed,
            score=score,
            weight=0.05,
            feedback=feedback,
            details={"found_roles": found_roles}
        ))

    def _rule_education_relevance(self, company: str):
        """Rule 11: Check for relevant education keywords (e.g., CS, Statistics, Biotech)."""
        company_data = load_company_profile(company)
        role_cfg = company_data.get("job_roles", {}).get(company, {})
        resume_type = role_cfg.get("resume_type", "analytics")

        education_keywords = {
            "analytics": ["statistics", "mathematics", "computer science", "data science", "ml"],
            "software": ["computer science", "software engineering", "information technology"],
            "biotech": ["biotechnology", "bioinformatics", "computational biology", "biology"],
            "finance": ["finance", "economics", "quantitative", "financial engineering"],
            "freelance": ["computer science", "data science", "business"],
        }

        relevant_keywords = education_keywords.get(resume_type, [])
        found = [kw for kw in relevant_keywords if kw in self.text_lower]
        score = (len(found) / max(len(relevant_keywords), 1)) * 100
        passed = len(found) >= 1
        feedback = f"Found {len(found)}/{len(relevant_keywords)} relevant education keywords"
        if found:
            feedback += f": {', '.join(found)}"
        self.rules.append(ATSRuleResult(
            rule_name="Education Relevance",
            passed=passed,
            score=score,
            weight=0.03,
            feedback=feedback,
            details={"found": found, "resume_type": resume_type}
        ))

    def _rule_certification_match(self, keywords: List[str]):
        """Rule 12: Check for certifications related to job keywords."""
        cert_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            if any(term in kw_lower for term in ["ml", "cloud", "aws", "gcp", "data", "analytics"]):
                cert_keywords.append(kw_lower)

        # Also check for common tech certs
        common_certs = ["aws", "gcp", "azure", "google cloud", "amazon web services",
                        "tensorflow", "pytorch", "kubernetes", "docker", "coursera", "udemy"]

        all_cert_terms = cert_keywords + common_certs
        found_certs = [term for term in all_cert_terms if term in self.text_lower]

        score = (len(found_certs) / max(len(all_cert_terms), 1)) * 100
        score = min(score, 100)
        passed = len(found_certs) >= 1
        feedback = f"Found {len(found_certs)} certification-related terms"
        if found_certs:
            feedback += f": {', '.join(found_certs[:5])}"
        self.rules.append(ATSRuleResult(
            rule_name="Certification Match",
            passed=passed,
            score=score,
            weight=0.03,
            feedback=feedback
        ))

    def _rule_industry_keywords(self, keywords: List[str]):
        """Rule 13: Check for industry-specific keywords."""
        industry_maps = {
            "tech": ["software", "engineering", "development", "tech", "coding", "full-stack"],
            "finance": ["trading", "quantitative", "financial", "investment", "risk"],
            "analytics": ["analytics", "statistical", "modeling", "predictive", "data-driven"],
            "biotech": ["biotech", "biotechnology", "research", "scientific", "bioinformatics"],
        }

        found_industries = []
        for industry, terms in industry_maps.items():
            if any(term in self.text_lower for term in terms):
                found_industries.append(industry)

        # Also check if keywords from the job match
        kw_matches = [kw for kw in keywords if kw.lower() in self.text_lower]

        score = (len(found_industries) / max(len(industry_maps), 1)) * 100
        passed = len(found_industries) >= 1
        feedback = f"Found {len(found_industries)} industry keyword categories: {', '.join(found_industries)}"
        if kw_matches:
            feedback += f" ({len(kw_matches)} job keywords matched)"
        self.rules.append(ATSRuleResult(
            rule_name="Industry Keywords",
            passed=passed,
            score=score,
            weight=0.03,
            feedback=feedback,
            details={"industries": found_industries, "keyword_matches": kw_matches}
        ))

    def _rule_soft_skills(self):
        """Rule 14: Check for soft skills keywords."""
        found_skills = [skill for skill in self.SOFT_SKILLS if skill in self.text_lower]
        score = (len(found_skills) / max(len(self.SOFT_SKILLS), 1)) * 100
        passed = len(found_skills) >= 2
        feedback = f"Found {len(found_skills)} soft skills: {', '.join(found_skills[:5])}" if found_skills else "Few or no soft skills mentioned"
        self.rules.append(ATSRuleResult(
            rule_name="Soft Skills",
            passed=passed,
            score=score,
            weight=0.03,
            feedback=feedback,
            details={"found_skills": found_skills}
        ))

    def _rule_ats_friendly_format(self):
        """Rule 15: Check for ATS-friendly formatting (no tables, images, headers/footers)."""
        found_unfriendly = []
        for pattern in self.ATS_UNFRIENDLY_PATTERNS:
            matches = re.findall(pattern, self.text)
            if matches:
                found_unfriendly.append(pattern)

        score = 100 if not found_unfriendly else 100 - len(found_unfriendly) * 15
        passed = not found_unfriendly
        feedback = "ATS-friendly formatting" if passed else f"ATS-unfriendly elements found: {', '.join(found_unfriendly[:3])}"
        self.rules.append(ATSRuleResult(
            rule_name="ATS-Friendly Format",
            passed=passed,
            score=score,
            weight=0.05,
            feedback=feedback,
            details={"unfriendly_elements": found_unfriendly}
        ))

    def _rule_contact_info(self):
        """Rule 16: Check for complete contact information."""
        checks = {
            "email": bool(re.search(r'\b[\w.-]+@[\w.-]+\.\w+\b', self.text)),
            "phone": bool(re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', self.text)),
            "linkedin": "linkedin" in self.text_lower,
            "github": "github" in self.text_lower or "git" in self.text_lower,
            "location": bool(re.search(r'\b\w+\s*,?\s*(?:India|USA|UK|Remote)\b', self.text)),
        }

        found = [k for k, v in checks.items() if v]
        score = (len(found) / len(checks)) * 100
        passed = len(found) >= 3
        feedback = f"Found {len(found)}/5 contact info items: {', '.join(found)}" if found else "Missing contact information"
        self.rules.append(ATSRuleResult(
            rule_name="Contact Info",
            passed=passed,
            score=score,
            weight=0.03,
            feedback=feedback,
            details=checks
        ))

    def _compile_results(self) -> Dict[str, Any]:
        """Compile all rule results into a comprehensive score."""
        total_weight = sum(r.weight for r in self.rules)
        weighted_score = sum(r.score * r.weight for r in self.rules)
        overall_score = round(weighted_score / total_weight, 1) if total_weight > 0 else 0

        # Count passed/failed rules
        passed_count = sum(1 for r in self.rules if r.passed)
        failed_count = len(self.rules) - passed_count

        # Compile suggestions
        suggestions = []
        for rule in self.rules:
            if not rule.passed:
                suggestions.append(f"{rule.rule_name}: {rule.feedback}")

        return {
            "overall_score": overall_score,
            "total_rules": len(self.rules),
            "passed_rules": passed_count,
            "failed_rules": failed_count,
            "rules": [
                {
                    "rule_name": r.rule_name,
                    "passed": r.passed,
                    "score": r.score,
                    "weight": r.weight,
                    "feedback": r.feedback,
                    "details": r.details,
                }
                for r in self.rules
            ],
            "suggestions": suggestions,
        }
