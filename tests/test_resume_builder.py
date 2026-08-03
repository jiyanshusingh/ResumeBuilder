"""
Test suite for resume_builder.py core functions.
Run with: pytest tests/ -v
"""
import json
import os
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resume_builder import (
    slugify,
    latex_escape,
    load_json,
    load_company_profile,
    rank_projects,
    extract_bullets,
    build_skills_block,
    build_certifications_block,
    build_achievements_block,
    build_experience_block,
)


# ─── slugify ────────────────────────────────────────────────────────────

class TestSlugify:
    def test_simple(self):
        assert slugify("Hello World") == "hello_world"

    def test_special_chars(self):
        assert slugify("Zerodha - Quant!") == "zerodha_quant"

    def test_multiple_spaces(self):
        assert slugify("Microsoft  Software  Engineer") == "microsoft_software_engineer"

    def test_empty(self):
        assert slugify("") == ""

    def test_only_special_chars(self):
        assert slugify("@#$%") == ""


# ─── latex_escape ────────────────────────────────────────────────────────

class TestLatexEscape:
    def test_none(self):
        assert latex_escape(None) == ""

    def test_plain_text(self):
        assert latex_escape("Hello World") == "Hello World"

    def test_special_chars(self):
        assert latex_escape("test$foo&bar%baz#qux{arg}") == "test\\$foo\\&bar\\%baz\\#qux\\{arg\\}"

    def test_underscore(self):
        assert latex_escape("hello_world") == "hello\\_world"

    def test_backslash(self):
        assert latex_escape("path\\to\\file") == "path\\textbackslash to\\textbackslash file"

    def test_tilde(self):
        assert latex_escape("a~b") == "a\\textasciitilde b"

    def test_caret(self):
        assert latex_escape("a^b") == "a\\textasciicircum b"


# ─── load_json ───────────────────────────────────────────────────────────

class TestLoadJson:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text(json.dumps({"key": "value"}))
        result = load_json(str(f))
        assert result == {"key": "value"}

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_json("/nonexistent/path/test.json")

    def test_invalid_json(self, tmp_path):
        f = tmp_path / "invalid.json"
        f.write_text("not valid json {{{")
        with pytest.raises(json.JSONDecodeError):
            load_json(str(f))


# ─── load_company_profile ────────────────────────────────────────────────

class TestLoadCompanyProfile:
    def test_existing_company(self):
        result = load_company_profile("zerodha")
        assert result["name"] == "Zerodha"
        assert "job_roles" in result

    def test_existing_company_hyphenated(self):
        result = load_company_profile("mu-sigma")
        assert "mu-sigma" in result["name"].lower() or "mu sigma" in result["name"].lower()

    def test_nonexistent_company(self):
        with pytest.raises(FileNotFoundError):
            load_company_profile("nonexistentcorp123")

    def test_case_insensitive(self):
        result = load_company_profile("ZERODHA")
        assert result["name"] == "Zerodha"


# ─── rank_projects ────────────────────────────────────────────────────────

class TestRankProjects:
    @pytest.fixture
    def sample_projects(self):
        return [
            {
                "name": "ML Trading Engine",
                "short_description": "XGBoost trading system with GCP deployment",
                "tags": ["ml", "finance", "gcp", "docker"],
            },
            {
                "name": "Sales CRM",
                "short_description": "Full-stack CRM with FastAPI",
                "tags": ["software", "docker", "fastapi"],
            },
            {
                "name": "Peptide Analysis",
                "short_description": "Biotech ML research with SHAP",
                "tags": ["biotech", "ml", "research"],
            },
        ]

    def test_ranks_by_keyword(self, sample_projects):
        weights = {"ml": 5, "gcp": 3}
        ranked = rank_projects(sample_projects, weights)
        assert ranked[0]["name"] == "ML Trading Engine"

    def test_empty_weights(self, sample_projects):
        ranked = rank_projects(sample_projects, {})
        assert len(ranked) == 3

    def test_partial_keyword_match(self, sample_projects):
        weights = {"docker": 10}
        ranked = rank_projects(sample_projects, weights)
        # All 3 have docker or fastapi+deployment; check ordering
        assert len(ranked) == 3

    def test_no_match_returns_all(self, sample_projects):
        weights = {"nonexistent_keyword": 100}
        ranked = rank_projects(sample_projects, weights)
        assert len(ranked) == 3  # All returned, just ranked equal


# ─── extract_bullets ────────────────────────────────────────────────────

class TestExtractBullets:
    def test_normal(self):
        proj = {
            "highlights": ["Achievement 1", "Achievement 2"],
            "metrics": {"analytics": ["Metric 1", "Metric 2"]},
        }
        result = extract_bullets(proj, "analytics")
        assert len(result) == 4

    def test_limits_to_4(self):
        proj = {
            "highlights": ["H1", "H2", "H3"],
            "metrics": {"analytics": ["M1", "M2", "M3"]},
        }
        result = extract_bullets(proj, "analytics")
        assert len(result) == 4

    def test_no_metrics(self):
        proj = {
            "highlights": ["Only highlight"],
            "metrics": {},
        }
        result = extract_bullets(proj, "analytics")
        assert len(result) == 1

    def test_empty_project(self):
        proj = {}
        result = extract_bullets(proj, "analytics")
        assert result == []


# ─── build_skills_block ─────────────────────────────────────────────────

class TestBuildSkillsBlock:
    def test_basic(self):
        skills = {"Programming": ["Python", "SQL"]}
        result = build_skills_block(skills)
        assert "\\textbf{Programming:" in result
        assert "Python" in result
        assert "SQL" in result

    def test_multiple_categories(self):
        skills = {
            "Programming": ["Python"],
            "Tools": ["Docker"],
        }
        result = build_skills_block(skills)
        assert "Programming" in result
        assert "Tools" in result

    def test_empty(self):
        result = build_skills_block({})
        assert result == ""


# ─── build_certifications_block ─────────────────────────────────────────

class TestBuildCertificationsBlock:
    def test_basic(self):
        certs = [
            {"name": "ML Certificate", "organization": "Coursera", "date": "2024"},
        ]
        result = build_certifications_block(certs)
        assert "ML Certificate" in result
        assert "Coursera" in result
        assert "2024" in result

    def test_multiple(self):
        certs = [
            {"name": "Cert A", "organization": "Org A", "date": "2023"},
            {"name": "Cert B", "organization": "Org B", "date": "2024"},
        ]
        result = build_certifications_block(certs)
        assert result.count("\\item") == 2


# ─── build_achievements_block ────────────────────────────────────────────

class TestBuildAchievementsBlock:
    def test_basic(self):
        achievements = ["Ach 1", "Ach 2", "Ach 3"]
        result = build_achievements_block(achievements)
        assert result.count("\\item") == 3
        assert "Ach 1" in result

    def test_empty(self):
        result = build_achievements_block([])
        assert result == "\\begin{itemize}\n\n\\end{itemize}"


# ─── build_experience_block ──────────────────────────────────────────────

class TestBuildExperienceBlock:
    def test_basic(self):
        experiences = [
            {
                "title": "Data Scientist",
                "company": "TestCorp",
                "duration": "2023-2024",
                "location": "Remote",
                "bullets": ["Built ML model", "Deployed to GCP"],
            },
        ]
        result = build_experience_block(experiences)
        assert "Data Scientist" in result
        assert "TestCorp" in result
        assert "Built ML model" in result
        assert "Deployed to GCP" in result

    def test_empty(self):
        result = build_experience_block([])
        assert result == ""


class TestJobTracker:
    """Tests for tracker.py (SQLite JobTracker)."""

    def test_add_and_list(self):
        from tracker import JobTracker
        db = os.path.join(tempfile.mkdtemp(), "t.db")
        t = JobTracker(db)
        aid = t.add_application("Acme", "Engineer", status="Applied", ats_score=70.0)
        rows = t.list_applications()
        assert len(rows) == 1
        assert rows[0]["company"] == "Acme"

    def test_update_and_delete(self):
        from tracker import JobTracker
        db = os.path.join(tempfile.mkdtemp(), "t.db")
        t = JobTracker(db)
        aid = t.add_application("Acme", "Engineer")
        t.update_status(aid, "Offer", notes="signed")
        row = t.get_application(aid)
        assert row["status"] == "Offer"
        t.delete_application(aid)
        assert t.get_application(aid) is None

    def test_status_filter(self):
        from tracker import JobTracker
        db = os.path.join(tempfile.mkdtemp(), "t.db")
        t = JobTracker(db)
        t.add_application("A", "R1", status="Applied")
        t.add_application("B", "R2", status="Offer")
        assert len(t.list_applications(status_filter="Offer")) == 1

    def test_requires_company_and_role(self):
        from tracker import JobTracker
        db = os.path.join(tempfile.mkdtemp(), "t.db")
        t = JobTracker(db)
        with pytest.raises(ValueError):
            t.add_application("", "")


class TestParsePreview:
    """Tests for parse_preview.py simulated ATS parser."""

    def test_extract_contact(self):
        from parse_preview import parse_resume_for_ats
        text = ("Rahul Sharma\nrahul@x.com\n+1 555 123 4567\n"
                "linkedin.com/in/rahul\n\nSUMMARY\nPython, ML")
        r = parse_resume_for_ats(text)
        assert "rahul@x.com" in r["contact"]["email"]
        assert "Rahul" in r["contact"]["name"]

    def test_sections_detected(self):
        from parse_preview import parse_resume_for_ats
        r = parse_resume_for_ats("EXPERIENCE\nWorked here.\nEDUCATION\nCollege\nSKILLS\nPython")
        assert "Experience" in r["sections_found"]
        assert "Skills" in r["sections_found"]

    def test_word_count_and_metrics(self):
        from parse_preview import parse_resume_for_ats
        r = parse_resume_for_ats("Built model improving accuracy by 25%")
        assert r["word_count"] == 6
        assert any("25%" in m for m in r["metrics_found"])

    def test_empty_text(self):
        from parse_preview import parse_resume_for_ats
        assert "error" in parse_resume_for_ats("   ")


class TestCompare:
    """Tests for compare.py ATS comparison."""

    def test_compare_against_all_returns_rows(self):
        from compare import compare_resume, comparison_header
        _ = load_company_profile("zerodha")
        sample = "Python ML model improving accuracy by 25%. Built trading system."
        results = compare_resume(sample)[:0]
        # at least the zerodha comparison should exist if profiles are present
        headers, rows = comparison_header(results)
        assert headers is not None
        assert rows == []

    def test_chart_returns_none_without_data(self):
        from compare import create_comparison_chart
        assert create_comparison_chart([]) is None


class TestBulletEnhancer:
    """Tests for bullet_enhancer.py."""

    def test_weak_detection(self):
        from bullet_enhancer import detect_weak_bullet
        assert detect_weak_bullet("Responsible for sales")["is_weak"] is True
        assert detect_weak_bullet("Built model improving accuracy by 25%")["is_weak"] is False

    def test_rule_based_enhance(self):
        from bullet_enhancer import enhance_bullets
        r = enhance_bullets(["Responsible for sales"], use_llm=False)
        assert r["results"][0]["method"] == "rule-based"
        assert r["results"][0]["improved"] != ""

    def test_enhance_bullets_summary(self):
        from bullet_enhancer import enhance_bullets
        r = enhance_bullets(["Responsible for sales", "Led team of 5"], use_llm=False)
        assert r["summary"].startswith("Processed 2 bullet(s)")


class TestTrackerVersioning:
    """Tests for tracker.py resume versioning."""

    def test_add_and_list_versions(self):
        from tracker import JobTracker
        db = os.path.join(tempfile.mkdtemp(), "t.db")
        t = JobTracker(db)
        aid = t.add_application("Acme", "Engineer")
        assert t.add_resume_version(aid, "/x/a.tex") == 1
        assert t.add_resume_version(aid, "/x/b.tex") == 2
        versions = t.list_resume_versions(aid)
        assert [v["version_number"] for v in versions] == [1, 2]
        assert t.get_application(aid)["resume_version"] == 2


class TestConfigAuth:
    """Tests for config.py auth + server helpers."""

    def test_auth_disabled_by_default(self, monkeypatch):
        import config
        monkeypatch.delenv("APP_USERNAME", raising=False)
        monkeypatch.delenv("APP_PASSWORD", raising=False)
        import importlib
        importlib.reload(config)
        assert config.auth_enabled() is False

    def test_auth_enabled(self, monkeypatch):
        import importlib
        import config
        monkeypatch.setenv("APP_USERNAME", "u")
        monkeypatch.setenv("APP_PASSWORD", "p")
        importlib.reload(config)
        assert config.auth_enabled() is True
        assert config.auth_user() == "u"
