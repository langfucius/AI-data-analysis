"""Project configuration. Values are read from environment variables at runtime."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "sample_sales.db"


def get_db_path() -> Path:
    raw = os.getenv("DATABASE_PATH", "").strip()
    if not raw:
        return DEFAULT_DB_PATH
    path = Path(raw).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def get_openai_api_key() -> str:
    return os.getenv("OPENAI_API_KEY", "").strip()


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()


def get_max_rows() -> int:
    try:
        value = int(os.getenv("MAX_ROWS", "1000"))
        return max(1, min(value, 10000))
    except ValueError:
        return 1000


def is_llm_enabled() -> bool:
    return bool(get_openai_api_key())
