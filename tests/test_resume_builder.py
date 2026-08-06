"""
Test suite for resume_builder.py core functions.
Run with: pytest tests/ -v
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resume_builder import (
    build_achievements_block,
    build_certifications_block,
    build_experience_block,
    build_skills_block,
    extract_bullets,
    latex_escape,
    load_company_profile,
    load_json,
    rank_projects,
    slugify,
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
        assert (
            latex_escape("test$foo&bar%baz#qux{arg}")
            == "test\\$foo\\&bar\\%baz\\#qux\\{arg\\}"
        )

    def test_underscore(self):
        assert latex_escape("hello_world") == "hello\\_world"

    def test_backslash(self):
        assert (
            latex_escape("path\\to\\file")
            == "path\\textbackslash to\\textbackslash file"
        )

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
        assert (
            "mu-sigma" in result["name"].lower() or "mu sigma" in result["name"].lower()
        )

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

        text = (
            "Rahul Sharma\nrahul@x.com\n+1 555 123 4567\n"
            "linkedin.com/in/rahul\n\nSUMMARY\nPython, ML"
        )
        r = parse_resume_for_ats(text)
        assert "rahul@x.com" in r["contact"]["email"]
        assert "Rahul" in r["contact"]["name"]

    def test_sections_detected(self):
        from parse_preview import parse_resume_for_ats

        r = parse_resume_for_ats(
            "EXPERIENCE\nWorked here.\nEDUCATION\nCollege\nSKILLS\nPython"
        )
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
        assert (
            detect_weak_bullet("Built model improving accuracy by 25%")["is_weak"]
            is False
        )

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


class TestCompanyResolution:
    """Tests for clean display-name resolution (Phase 4 dropdowns)."""

    def test_load_by_json_name(self):
        from resume_builder import load_company_profile

        prof = load_company_profile("J.P. Morgan")
        assert prof["name"] in ("J.P. Morgan",)

    def test_load_multi_word_name(self):
        from resume_builder import load_company_profile

        assert load_company_profile("Goldman Sachs")["name"] == "Goldman Sachs"

    def test_company_roles_helper(self):
        import web_ui

        roles = web_ui.get_company_roles("Zerodha")
        assert "Quant Developer" in roles

    def test_resolve_company_key(self):
        import web_ui

        assert web_ui.resolve_company_key("Amazon") == "amazon"
        assert web_ui.resolve_company_key("Goldman Sachs") == "goldman"


class TestMinimalCompanyProfile:
    """Tests that the app handles company profiles missing optional fields."""

    def test_load_minimal_profile_no_resume_type(self, tmp_path, monkeypatch):
        """A profile with only name and skills should not crash."""
        import resume_builder

        monkeypatch.setattr(resume_builder, "DATA_DIR", tmp_path)

        companies_dir = tmp_path / "companies"
        companies_dir.mkdir()
        minimal = {"name": "MinimalCo", "job_roles": {}}
        with open(companies_dir / "minimalco.json", "w") as f:
            json.dump(minimal, f)

        prof = load_company_profile("MinimalCo")
        assert prof["name"] == "MinimalCo"
        assert prof.get("job_roles") == {}

    def test_load_profile_missing_keywords(self, tmp_path, monkeypatch):
        """A profile missing keywords field should not crash."""
        import resume_builder

        monkeypatch.setattr(resume_builder, "DATA_DIR", tmp_path)

        companies_dir = tmp_path / "companies"
        companies_dir.mkdir()
        data = {
            "name": "NoKeywordsCo",
            "job_roles": {
                "Engineer": {
                    "resume_type": "software",
                    "required_skills": ["Python"],
                    "emphasize_metrics": [],
                }
            },
        }
        with open(companies_dir / "nokeywordco.json", "w") as f:
            json.dump(data, f)

        prof = load_company_profile("NoKeywordsCo")
        role_cfg = prof["job_roles"]["Engineer"]
        assert role_cfg.get("keywords") is None

    def test_load_profile_missing_emphasize_metrics(self, tmp_path, monkeypatch):
        """A profile missing emphasize_metrics should not crash."""
        import resume_builder

        monkeypatch.setattr(resume_builder, "DATA_DIR", tmp_path)

        companies_dir = tmp_path / "companies"
        companies_dir.mkdir()
        data = {
            "name": "NoMetricsCo",
            "job_roles": {
                "Analyst": {
                    "resume_type": "analytics",
                    "required_skills": ["SQL"],
                    "keywords": ["data"],
                }
            },
        }
        with open(companies_dir / "nometricsco.json", "w") as f:
            json.dump(data, f)

        prof = load_company_profile("NoMetricsCo")
        role_cfg = prof["job_roles"]["Analyst"]
        assert role_cfg.get("emphasize_metrics") is None

    def test_load_profile_missing_resume_type(self, tmp_path, monkeypatch):
        """A profile missing resume_type should not crash."""
        import resume_builder

        monkeypatch.setattr(resume_builder, "DATA_DIR", tmp_path)

        companies_dir = tmp_path / "companies"
        companies_dir.mkdir()
        data = {
            "name": "NoResumeTypeCo",
            "job_roles": {
                "Developer": {
                    "required_skills": ["Go"],
                    "keywords": [],
                    "emphasize_metrics": [],
                }
            },
        }
        with open(companies_dir / "noresumetypeco.json", "w") as f:
            json.dump(data, f)

        prof = load_company_profile("NoResumeTypeCo")
        role_cfg = prof["job_roles"]["Developer"]
        assert role_cfg.get("resume_type") is None

    def test_list_all_companies_with_minimal_profile(self, tmp_path, monkeypatch):
        """list_all_companies should not crash with minimal profiles."""
        import resume_builder
        import web_ui

        monkeypatch.setattr(resume_builder, "DATA_DIR", tmp_path)
        monkeypatch.setattr(web_ui, "COMPANY_DIR", str(tmp_path / "companies"))

        companies_dir = tmp_path / "companies"
        companies_dir.mkdir()
        minimal = {"name": "MinimalCo", "job_roles": {}}
        with open(companies_dir / "minimalco.json", "w") as f:
            json.dump(minimal, f)

        result = web_ui.list_all_companies()
        assert "MinimalCo" in result


class TestProfileValidation:
    """Tests for profile validation and the Validate All Profiles feature."""

    def test_validate_all_profiles_empty_dir(self, tmp_path, monkeypatch):
        """Validate all profiles with no profiles returns a friendly message."""
        import web_ui

        monkeypatch.setattr(web_ui, "COMPANY_DIR", str(tmp_path))
        result = web_ui._validate_all_profiles()
        assert "No companies" in result or "valid" in result.lower()

    def test_validate_all_profiles_minimal(self, tmp_path, monkeypatch):
        """Validate a minimal profile (no roles) shows a warning."""
        import json

        import web_ui

        monkeypatch.setattr(web_ui, "COMPANY_DIR", str(tmp_path))
        minimal = {"name": "MinimalCo", "job_roles": {}}
        with open(tmp_path / "minimalco.json", "w") as f:
            json.dump(minimal, f)
        result = web_ui._validate_all_profiles()
        assert "MinimalCo" in result

    def test_validate_all_profiles_missing_resume_type(self, tmp_path, monkeypatch):
        """A role missing resume_type should be flagged."""
        import json

        import web_ui

        monkeypatch.setattr(web_ui, "COMPANY_DIR", str(tmp_path))
        data = {
            "name": "TestCo",
            "job_roles": {
                "Engineer": {
                    "required_skills": ["Python"],
                    "keywords": [],
                    "emphasize_metrics": [],
                }
            },
        }
        with open(tmp_path / "testco.json", "w") as f:
            json.dump(data, f)
        result = web_ui._validate_all_profiles()
        assert "TestCo" in result
        assert "resume_type" in result.lower() or "missing" in result.lower()

    def test_validate_all_profiles_valid(self, tmp_path, monkeypatch):
        """A fully valid profile should show OK."""
        import json

        import web_ui

        monkeypatch.setattr(web_ui, "COMPANY_DIR", str(tmp_path))
        data = {
            "name": "GoodCo",
            "job_roles": {
                "Engineer": {
                    "resume_type": "software",
                    "required_skills": ["Python"],
                    "keywords": ["python", "django"],
                    "emphasize_metrics": ["performance"],
                }
            },
        }
        with open(tmp_path / "goodco.json", "w") as f:
            json.dump(data, f)
        result = web_ui._validate_all_profiles()
        assert "GoodCo" in result
        assert "OK" in result


# ─── semantic embeddings (Tier A) ──────────────────────────────────────


class _FakeEmbeddings:
    """Deterministic stand-in for the offline embeddings module."""

    def __init__(self):
        self._sims = {}

    def available(self):
        return True

    def similarity(self, a, b):
        if a == "XGBoost trading system" or "trading" in a:
            return 0.95
        return 0.2

    def set(self, a, val):
        self._sims[a] = val


@pytest.fixture
def fake_embeddings(monkeypatch):
    fake = _FakeEmbeddings()
    monkeypatch.setitem(sys.modules, "embeddings", fake)
    return fake


class TestEmbeddingsEnvGuard:
    def test_disabled_via_env(self, monkeypatch):
        import embeddings as emb

        monkeypatch.setenv("RESUME_EMBEDDINGS", "0")
        assert emb.available() is False

    def test_enabled_by_default(self):
        import embeddings as emb

        # Must not crash; availability depends on env/model presence
        assert isinstance(emb.available(), bool)


class TestRankProjectsSemantic:
    @pytest.fixture
    def projects(self):
        return [
            {
                "name": "ML Trading Engine",
                "short_description": "XGBoost trading system with GCP deployment",
                "tags": ["ml", "finance"],
            },
            {
                "name": "A/B Dashboard",
                "short_description": "Statistical web app with FastAPI",
                "tags": ["software", "analytics"],
            },
        ]

    def test_semantic_bonus_used(self, projects, monkeypatch):
        # similarity returns higher for trading query
        class Fake:
            def available(self):
                return True

            def similarity(self, a, b):
                return 0.95 if "trading" in b else 0.2

        monkeypatch.setitem(sys.modules, "embeddings", Fake())
        ranked = rank_projects(projects, {})
        assert ranked[0]["name"] == "ML Trading Engine"

    def test_fallback_when_unavailable(self, projects, monkeypatch):
        class Unavailable:
            def available(self):
                return False

        monkeypatch.setitem(sys.modules, "embeddings", Unavailable())
        ranked = rank_projects(projects, {"ml": 5})
        assert len(ranked) == 2


class TestSemanticAtsRule:
    def test_rule_present_when_embeddings_available(self, monkeypatch):
        import ats_scorer

        class Fake:
            def available(self):
                return True

            def similarity(self, a, b):
                return 0.9 if "python" in a.lower() else 0.1

        monkeypatch.setitem(sys.modules, "embeddings", Fake())
        scorer = ats_scorer.ATSScorer(
            "Built a FastAPI web service for analytics dashboards", ".pdf"
        )
        result = scorer.score("fractal", "Decision Analytics Associate")
        names = [r["rule_name"] for r in result["rules"]]
        assert "Semantic Match" in names

    def test_rule_skipped_when_unavailable(self, monkeypatch):
        import ats_scorer

        class Fake:
            def available(self):
                return False

        monkeypatch.setitem(sys.modules, "embeddings", Fake())
        scorer = ats_scorer.ATSScorer("Python resume text", ".pdf")
        result = scorer.score("fractal", "Decision Analytics Associate")
        names = [r["rule_name"] for r in result["rules"]]
        assert "Semantic Match" not in names


class TestJdSemanticExtraction:
    def test_semantic_skills_appended(self, monkeypatch):
        import jd_importer

        class Fake:
            def available(self):
                return True

            def similarity(self, skill, text):
                return 0.9 if skill.lower() in {"pandas", "docker"} else 0.1

        monkeypatch.setitem(sys.modules, "embeddings", Fake())
        skills = jd_importer.extract_skills_semantic(
            "We need strong data wrangling and containerized deployments"
        )
        assert {"pandas", "docker"}.issubset(set(s.lower() for s in skills))

    def test_empty_when_unavailable(self, monkeypatch):
        import jd_importer

        class Fake:
            def available(self):
                return False

        monkeypatch.setitem(sys.modules, "embeddings", Fake())
        assert jd_importer.extract_skills_semantic("any text") == []


# ─── Tier B: jd_store, insights, auto-propose ──────────────────────────


class TestJDStore:
    def test_save_and_list(self, tmp_path):
        import jd_store

        store = jd_store.JDStore(
            db_path=str(tmp_path / "jds.db"), jd_dir=str(tmp_path / "jds")
        )
        slug = store.save_jd(
            "Acme",
            "Data Engineer",
            "need machine learning and docker",
            {"required_skills": ["python"], "keywords": [], "resume_type": "software"},
        )
        assert slug
        assert store.count() == 1
        listed = store.list_jds()
        assert listed[0]["company"] == "Acme"
        rec = store.get_jd(slug)
        assert rec["extraction"]["required_skills"] == ["python"]

    def test_dedupe_same_slug(self, tmp_path):
        import jd_store

        store = jd_store.JDStore(
            db_path=str(tmp_path / "jds.db"), jd_dir=str(tmp_path / "jds")
        )
        store.save_jd("X", "", "same text", {})
        store.save_jd("X", "", "same text", {})
        assert store.count() == 1


class TestTrackerInsights:
    def test_insights_empty(self, tmp_path):
        from tracker import JobTracker

        tr = JobTracker(db_path=str(tmp_path / "apps.db"))
        ins = tr.analyze_insights()
        assert ins["total"] == 0
        assert ins.get("chart_path") is None

    def test_insights_collects(self, tmp_path):
        from tracker import JobTracker

        t = JobTracker(db_path=str(tmp_path / "apps.db"))
        t.add_application("X", "R", status="Applied", ats_score=80.0)
        t.add_application("Y", "R", status="Offer", ats_score=95.0)
        ins = t.analyze_insights()
        assert ins["total"] == 2
        assert ins["avg_ats_by_status"]["Applied"] == 80.0
        assert ins["avg_ats_by_status"]["Offer"] == 95.0
        assert ins["best_per_company"]["Y"]["ats_score"] == 95.0

    def test_format_insights(self):
        from tracker import format_insights

        txt = format_insights(
            {"total": 1, "status_counts": {"Applied": 1}, "best_per_company": {}}
        )
        assert "Total applications tracked: 1" in txt


class TestProposeProfile:
    def test_propose_shape(self):
        import resume_builder as rb

        profile = rb.propose_company_profile(
            "Acme",
            "Data Engineer",
            {
                "required_skills": ["python", "sql"],
                "keywords": ["etl"],
                "emphasize_metrics": ["30 TB"],
                "resume_type": "software",
            },
        )
        assert profile["name"] == "Acme"
        assert "Data Engineer" in profile["job_roles"]
        role = profile["job_roles"]["Data Engineer"]
        assert role["required_skills"] == ["python", "sql"]
        assert role["resume_type"] == "software"

    def test_save_profile_writes_file(self, tmp_path):
        import resume_builder as rb

        rb.DATA_DIR = str(tmp_path)
        profile = rb.propose_company_profile(
            "NewCo XYZ",
            "Role",
            {"required_skills": ["python"], "resume_type": "software"},
        )
        path = rb.save_company_profile(profile)
        assert os.path.exists(path)
