"""Tests for applypilot.scoring.pdf: resume parsing, HTML generation, PDF conversion."""

from __future__ import annotations

from applypilot.scoring.pdf import build_html, parse_entries, parse_resume, parse_skills


# ── parse_resume ────────────────────────────────────────────────────────

class TestParseResume:
    def test_parses_header_and_sections(self) -> None:
        text = """\
John Doe
Software Engineer
Toronto, ON
john@example.com | 555-123-4567

SUMMARY
Experienced engineer building APIs.

TECHNICAL SKILLS
Languages: Python, Java
Frameworks: Django, Spring

EXPERIENCE
Software Engineer at Acme Corp
Python | 2020-2024
- Built REST APIs serving 10K requests/day

PROJECTS
MyBot - Automated workflow tool
Python | 2023
- Automated repetitive tasks

EDUCATION
University of Waterloo | BSc Computer Science
"""
        result = parse_resume(text)
        assert result["name"] == "John Doe"
        assert result["title"] == "Software Engineer"
        assert result["location"] == "Toronto, ON"
        assert result["contact"] == "john@example.com | 555-123-4567"
        assert "SUMMARY" in result["sections"]
        assert "TECHNICAL SKILLS" in result["sections"]
        assert "EXPERIENCE" in result["sections"]
        assert "PROJECTS" in result["sections"]
        assert "EDUCATION" in result["sections"]

    def test_handles_missing_location_line(self) -> None:
        text = """\
Jane Smith
Full Stack Developer
jane@example.com | 555-987-6543

SUMMARY
Building web apps.

TECHNICAL SKILLS
Languages: JavaScript, TypeScript
"""
        result = parse_resume(text)
        assert result["name"] == "Jane Smith"
        assert result["title"] == "Full Stack Developer"
        assert result["location"] == ""
        assert result["contact"] == "jane@example.com | 555-987-6543"

    def test_handles_empty_text(self) -> None:
        result = parse_resume("")
        assert result["name"] == ""
        assert result["title"] == ""
        assert result["sections"] == {}

    def test_ignores_bullet_lines_as_sections(self) -> None:
        text = """\
Alex Lee
Engineer
alex@example.com

SUMMARY
-Building things that work

TECHNICAL SKILLS
Languages: Python
"""
        result = parse_resume(text)
        assert "SUMMARY" in result["sections"]
        assert "-Building" in result["sections"]["SUMMARY"]


# ── parse_skills ────────────────────────────────────────────────────────

class TestParseSkills:
    def test_parses_categories(self) -> None:
        text = """\
Languages: Python, Java, Bash
Frameworks: FastAPI, Django
Databases: PostgreSQL, Redis
"""
        skills = parse_skills(text)
        assert len(skills) == 3
        assert skills[0] == ("Languages", "Python, Java, Bash")
        assert skills[1] == ("Frameworks", "FastAPI, Django")
        assert skills[2] == ("Databases", "PostgreSQL, Redis")

    def test_ignores_lines_without_colon(self) -> None:
        text = """\
Languages: Python, Bash
Docker, Kubernetes
"""
        skills = parse_skills(text)
        assert len(skills) == 1
        assert skills[0] == ("Languages", "Python, Bash")

    def test_handles_empty_text(self) -> None:
        skills = parse_skills("")
        assert skills == []


# ── parse_entries ───────────────────────────────────────────────────────

class TestParseEntries:
    def test_parses_job_entries(self) -> None:
        text = """\
Software Engineer at Acme Corp
Python | 2020-2024
- Built REST APIs serving 10K requests/day
- Reduced latency by 40%

Dev at StartupXYZ
JavaScript | 2018-2020
- Shipped MVP for early adopters
"""
        entries = parse_entries(text)
        assert len(entries) == 2
        assert entries[0]["title"] == "Software Engineer at Acme Corp"
        assert entries[0]["subtitle"] == "Python | 2020-2024"
        assert len(entries[0]["bullets"]) == 2
        assert entries[1]["title"] == "Dev at StartupXYZ"
        assert entries[1]["subtitle"] == "JavaScript | 2018-2020"

    def test_handles_unicode_bullets(self) -> None:
        text = """\
Engineer at Google
Go | 2022-2024
• Led migration to Go microservices
• Reduced build time by 60%
"""
        entries = parse_entries(text)
        assert len(entries) == 1
        assert len(entries[0]["bullets"]) == 2

    def test_handles_empty_text(self) -> None:
        entries = parse_entries("")
        assert entries == []


# ── build_html ─────────────────────────────────────────────────────────

class TestBuildHtml:
    def test_generates_valid_html(self) -> None:
        resume = {
            "name": "John Doe",
            "title": "Software Engineer",
            "location": "Toronto, ON",
            "contact": "john@example.com | 555-123-4567",
            "sections": {
                "SUMMARY": "Experienced engineer.",
                "TECHNICAL SKILLS": "Languages: Python, Java",
                "EXPERIENCE": "Software Engineer at Acme\n- Built APIs",
                "EDUCATION": "UW | BSc",
            },
        }
        html = build_html(resume)
        assert "<!DOCTYPE html>" in html
        assert "John Doe" in html
        assert "Software Engineer" in html
        assert "Toronto, ON" in html
        assert "Experienced engineer" in html
        # Skills are rendered as <span class="skill-cat">Languages:</span> Python, Java
        assert "Languages:" in html
        assert "Python, Java" in html
        assert "UW | BSc" in html

    def test_escapes_html_entities(self) -> None:
        resume = {
            "name": "O'Brien & Sons",
            "title": "Senior <Engineer>",
            "location": "Toronto",
            "contact": "test@example.com",
            "sections": {"SUMMARY": "Built APIs & microservices"},
        }
        html = build_html(resume)
        assert "O'Brien" in html
        assert "&lt;Engineer&gt;" in html
        assert "&amp;" in html

    def test_handles_empty_sections(self) -> None:
        resume = {
            "name": "Jane",
            "title": "Developer",
            "location": "",
            "contact": "",
            "sections": {"SUMMARY": "New dev."},
        }
        html = build_html(resume)
        assert "<!DOCTYPE html>" in html
        assert "New dev" in html
