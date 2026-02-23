"""GitHub repository ingestion: README, file map, stack signals, text extraction. Idempotent, rate-limit safe."""
import re
import time
from urllib.parse import urlparse
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import get_settings


def _normalize_repo_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://github.com/" + url.lstrip("/")
    return url.split("?")[0]


def _parse_github_url(url: str) -> tuple[str, str]:
    """Return (owner, repo). Strips .git from repo name."""
    norm = _normalize_repo_url(url)
    parsed = urlparse(norm)
    path = parsed.path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2:
        owner, repo = parts[0], parts[1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo
    raise ValueError(f"Invalid GitHub URL: {url}")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def _get(url: str, headers: dict) -> tuple[dict | None, int]:
    """Returns (json_data, status_code). Caller can raise with status for better errors."""
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url, headers=headers)
        if r.status_code == 403 and "rate limit" in r.text.lower():
            time.sleep(60)
            raise Exception("Rate limited")
        if r.status_code != 200:
            return None, r.status_code
        return r.json(), r.status_code


def _get_file_content(owner: str, repo: str, path: str, token: str) -> str | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {"Accept": "application/vnd.github.raw"}
    if token:
        headers["Authorization"] = f"token {token}"
    with httpx.Client(timeout=15.0) as client:
        r = client.get(url, headers=headers)
        if r.status_code != 200:
            return None
        return r.text


def _language_from_filename(path: str) -> str:
    ext = path.split(".")[-1].lower()
    lang = {
        "py": "Python", "js": "JavaScript", "ts": "TypeScript", "tsx": "TypeScript",
        "java": "Java", "kt": "Kotlin", "go": "Go", "rs": "Rust", "rb": "Ruby",
        "php": "PHP", "vue": "Vue", "css": "CSS", "html": "HTML", "md": "Markdown",
        "json": "JSON", "yaml": "YAML", "yml": "YAML", "sh": "Shell", "sql": "SQL",
    }
    return lang.get(ext, ext)


def ingest_github_repo(repo_url: str) -> dict[str, Any]:
    """
    Ingest a public GitHub repo: metadata, file map, stack signals, README and key files.
    Returns dict suitable for Repository model (metadata_, file_map, stack_signals, extracted_artifacts).
    """
    token = get_settings().github_token
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    owner, repo = _parse_github_url(repo_url)
    base = f"https://api.github.com/repos/{owner}/{repo}"

    # Repo metadata
    repo_data, status = _get(base, headers)
    if not repo_data:
        if status == 404:
            raise ValueError(
                f"Cannot access repository: {repo_url}. "
                "The repo may not exist or may be private. For private repos, set GITHUB_TOKEN in .env to a token with repo scope."
            )
        if status == 403:
            raise ValueError(
                f"Access forbidden (403) for {repo_url}. "
                "If the repo is private, set GITHUB_TOKEN in .env. Otherwise you may be rate-limited; try again later."
            )
        raise ValueError(f"Cannot access repository: {repo_url} (HTTP {status})")
    metadata_ = {
        "name": repo_data.get("name"),
        "full_name": repo_data.get("full_name"),
        "description": repo_data.get("description") or "",
        "language": repo_data.get("language"),
        "default_branch": repo_data.get("default_branch", "main"),
    }

    # Top-level contents (depth 1)
    default_branch = metadata_.get("default_branch", "main")
    contents, _ = _get(f"{base}/contents?ref={default_branch}", headers)
    file_map = {}
    stack_signals = []
    if isinstance(contents, list):
        for item in contents:
            name = item.get("name", "")
            type_ = item.get("type", "file")
            file_map[name] = type_
            if type_ == "file":
                lang = _language_from_filename(name)
                if lang and lang not in stack_signals:
                    stack_signals.append(lang)
            elif type_ == "dir" and name not in (".git", "node_modules", "__pycache__", ".venv", "venv"):
                file_map[name] = "dir"

    # README
    readme_names = ["README.md", "README.MD", "readme.md", "README.rst", "README.txt"]
    readme_text = ""
    for rn in readme_names:
        if rn in file_map:
            readme_text = _get_file_content(owner, repo, rn, token) or ""
            break
    if not readme_text and "README.md" not in file_map:
        try:
            readme_text = _get_file_content(owner, repo, "README.md", token) or ""
        except Exception:
            pass

    # Lightweight code extraction: a few key files for retrieval (bounded)
    extracted_artifacts = {}
    if readme_text:
        extracted_artifacts["README.md"] = readme_text[:15000]

    # Add top-level key files (requirements.txt, package.json, etc.)
    key_files = ["requirements.txt", "package.json", "pyproject.toml", "Dockerfile", "docker-compose.yml"]
    for kf in key_files:
        if kf in file_map:
            content = _get_file_content(owner, repo, kf, token)
            if content:
                extracted_artifacts[kf] = content[:8000]

    return {
        "metadata_": metadata_,
        "file_map": file_map,
        "stack_signals": stack_signals,
        "extracted_artifacts": extracted_artifacts,
    }
