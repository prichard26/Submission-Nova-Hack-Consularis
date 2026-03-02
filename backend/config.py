"""
Centralized config: env and constants. Single place for GROQ_KEY, paths, and limits.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(_BACKEND_DIR / ".env")

# API
GROQ_KEY: str = os.getenv("GROQ_KEY", "")
if not GROQ_KEY or GROQ_KEY.startswith("your_"):
    GROQ_KEY = "missing"

# Paths
_default_graphs_dir = _BACKEND_DIR / "data" / "graphs"
_graphs_dir_env = os.getenv("BASELINE_GRAPHS_DIR", "")
BASELINE_GRAPHS_DIR: Path = Path(_graphs_dir_env) if _graphs_dir_env else _default_graphs_dir
if not BASELINE_GRAPHS_DIR.is_absolute():
    BASELINE_GRAPHS_DIR = _BACKEND_DIR / BASELINE_GRAPHS_DIR
BASELINE_GRAPH_REGISTRY_PATH: Path = BASELINE_GRAPHS_DIR / "registry.json"

DEFAULT_PROCESS_ID: str = os.getenv("DEFAULT_PROCESS_ID", "Process_Global")

# Agent
MAX_TOOL_ROUNDS: int = int(os.getenv("MAX_TOOL_ROUNDS", "10"))
GROQ_TIMEOUT: float = float(os.getenv("GROQ_TIMEOUT", "60"))
GROQ_MAX_RETRIES: int = int(os.getenv("GROQ_MAX_RETRIES", "2"))

# CORS (comma-separated or default)
_cors = os.getenv("ALLOWED_CORS_ORIGINS", "http://localhost:5173,http://localhost:5174")
ALLOWED_CORS_ORIGINS: list[str] = [o.strip() for o in _cors.split(",") if o.strip()]

# Session validation
SESSION_ID_MAX_LEN: int = 256
