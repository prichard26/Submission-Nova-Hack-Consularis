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
_default_baseline = _BACKEND_DIR / "data" / "pharmacy_circuit.bpmn"
_baseline_env = os.getenv("BASELINE_GRAPH_PATH", "")
BASELINE_GRAPH_PATH: Path = Path(_baseline_env) if _baseline_env else _default_baseline
if not BASELINE_GRAPH_PATH.is_absolute():
    BASELINE_GRAPH_PATH = _BACKEND_DIR / BASELINE_GRAPH_PATH

_graphs_dir_env = os.getenv("BASELINE_GRAPHS_DIR", "")
BASELINE_GRAPHS_DIR: Path = Path(_graphs_dir_env) if _graphs_dir_env else _BACKEND_DIR / "data" / "graphs"
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

# Storage: "memory" (default) or "file"
STORAGE: str = os.getenv("STORAGE", "memory").strip().lower()
_session_data_env = os.getenv("SESSION_DATA_DIR", "")
SESSION_DATA_DIR: Path = Path(_session_data_env) if _session_data_env else _BACKEND_DIR / "data" / "sessions"
if not SESSION_DATA_DIR.is_absolute():
    SESSION_DATA_DIR = _BACKEND_DIR / SESSION_DATA_DIR
