"""CV parsing from PDF/DOCX - contact, skills, experience, projects, education."""
import re
from pathlib import Path
from typing import Any

import pdfplumber
from docx import Document as DocxDocument


def _extract_email(text: str) -> str:
    m = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    return m.group(0) if m else ""


def _extract_phone(text: str) -> str:
    m = re.search(r"[\+]?[(]?[0-9]{1,4}[)]?[-\s\./0-9]{8,}", text)
    return m.group(0).strip() if m else ""


def _extract_text_pdf(path: str) -> str:
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)


def _extract_text_docx(path: str) -> str:
    doc = DocxDocument(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _parse_experience_heuristic(text: str) -> list[dict[str, Any]]:
    """Heuristic: look for role/company/date patterns."""
    entries = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # Common: "Role at Company (dates)" or "Company - Role (dates)"
    date_pattern = re.compile(
        r"(\d{4})\s*[-–—]\s*(\d{4}|present|current|now)",
        re.I
    )
    for i, line in enumerate(lines):
        if re.search(r"(experience|employment|work\s+history)", line, re.I) and len(line) < 50:
            continue
        m = date_pattern.search(line)
        if m or any(kw in line.lower() for kw in ["engineer", "developer", "manager", "analyst", "lead", "director", "at ", " - "]):
            role = line
            company = ""
            dates = ""
            if m:
                dates = m.group(0)
                role = line[: m.start()].strip().rstrip(",- ")
            entries.append({"role": role, "company": company, "dates": dates})
    return entries[:15]


def _parse_education_heuristic(text: str) -> list[dict[str, Any]]:
    entries = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines:
        if re.search(r"(university|college|institute|b\.?s\.?|m\.?s\.?|b\.?a\.?|m\.?a\.?|phd|degree)", line, re.I):
            entries.append({"institution": line, "degree": "", "year": ""})
    return entries[:10]


def _extract_skills_heuristic(text: str) -> list[str]:
    """Simple keyword extraction - look for skills section and comma/bullet lists."""
    skills = set()
    lower = text.lower()
    # Common tech skills
    tech = [
        "python", "java", "javascript", "typescript", "react", "node", "sql", "aws",
        "docker", "kubernetes", "fastapi", "django", "flask", "postgresql", "mongodb",
        "git", "ci/cd", "rest", "api", "machine learning", "tensorflow", "pytorch",
        "langchain", "langgraph", "openai", "llm",
    ]
    for s in tech:
        if s in lower:
            skills.add(s)
    # Section after "skills" or "technical skills"
    m = re.search(r"skills?[:\s]+([^\n]+(?:\n[^\n]+){0,5})", text, re.I | re.DOTALL)
    if m:
        block = m.group(1)
        for part in re.split(r"[,;\|\n•\-]", block):
            part = part.strip()
            if 2 <= len(part) <= 50 and not part.endswith(":"):
                skills.add(part.strip())
    return list(skills)[:50]


def _extract_projects_heuristic(text: str) -> list[dict[str, Any]]:
    projects = []
    in_projects = False
    for line in text.split("\n"):
        line = line.strip()
        if re.search(r"projects?|key\s+projects?", line, re.I) and len(line) < 40:
            in_projects = True
            continue
        if in_projects and line and not line.startswith("•") and len(line) > 10:
            projects.append({"name": line[:200], "description": ""})
        if in_projects and len(projects) >= 10:
            break
    return projects


def parse_cv_file(file_path: str) -> dict[str, Any]:
    """
    Parse PDF or DOCX resume. Returns structured profile and raw text.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        raw_text = _extract_text_pdf(str(path))
    elif suffix in (".docx", ".doc"):
        raw_text = _extract_text_docx(str(path))
    else:
        raise ValueError("Only PDF and DOCX are supported")

    raw_text = raw_text or ""
    contact_info = {
        "email": _extract_email(raw_text),
        "phone": _extract_phone(raw_text),
    }
    skills = _extract_skills_heuristic(raw_text)
    experience = _parse_experience_heuristic(raw_text)
    education = _parse_education_heuristic(raw_text)
    projects = _extract_projects_heuristic(raw_text)

    return {
        "contact_info": contact_info,
        "skills": skills,
        "experience": experience,
        "education": education,
        "projects": projects,
        "raw_text": raw_text,
    }
