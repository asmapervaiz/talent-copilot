"""Application configuration."""
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# Project root: backend/app/config.py -> parent.parent = backend, parent.parent.parent = project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

# Load .env into os.environ so LangChain and other libs find OPENAI_API_KEY etc.
try:
    from dotenv import load_dotenv
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE)
except Exception:
    pass


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/talentcopilot"
    openai_api_key: str = ""
    github_token: str = ""
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Memory: recent N messages in context
    memory_window_size: int = 10
    # HITL confirmation timeout (seconds) - optional
    confirmation_timeout_seconds: int = 3600

    class Config:
        env_file = str(_ENV_FILE) if _ENV_FILE.exists() else ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
