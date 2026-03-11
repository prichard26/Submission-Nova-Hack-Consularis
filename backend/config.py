"""
Centralized config: env and constants. AWS Bedrock (Nova), paths, and limits.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(_BACKEND_DIR / ".env")

# API — AWS Bedrock
AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
NOVA_MODEL_ID: str = os.getenv("NOVA_MODEL_ID", "us.amazon.nova-pro-v1:0")
NOVA_CHEAP_MODEL_ID: str = os.getenv("NOVA_CHEAP_MODEL_ID", NOVA_MODEL_ID)
# Set NOVA_MODEL_ID to a Claude model on Bedrock (e.g. us.anthropic.claude-sonnet-4-6-v1:0)
# to use the optimized Claude prompt variant automatically.

# Paths
_default_graphs_dir = _BACKEND_DIR / "data" / "graphs"
_graphs_dir_env = os.getenv("BASELINE_GRAPHS_DIR", "")
BASELINE_GRAPHS_DIR: Path = Path(_graphs_dir_env) if _graphs_dir_env else _default_graphs_dir
if not BASELINE_GRAPHS_DIR.is_absolute():
    BASELINE_GRAPHS_DIR = _BACKEND_DIR / BASELINE_GRAPHS_DIR
BASELINE_WORKSPACE_PATH: Path = BASELINE_GRAPHS_DIR.parent / "workspace.json"

DEFAULT_PROCESS_ID: str = os.getenv("DEFAULT_PROCESS_ID", "global")

# Agent
MAX_TOOL_ROUNDS: int = int(os.getenv("MAX_TOOL_ROUNDS", "10"))
BEDROCK_TIMEOUT: int = int(os.getenv("BEDROCK_TIMEOUT", "120"))
BEDROCK_MAX_RETRIES: int = int(os.getenv("BEDROCK_MAX_RETRIES", "2"))
MAX_RECENT_MESSAGES: int = int(os.getenv("MAX_RECENT_MESSAGES", "20"))
SUMMARY_MODEL_MAX_TOKENS: int = int(os.getenv("SUMMARY_MODEL_MAX_TOKENS", "512"))

# CORS (comma-separated or default)
_cors = os.getenv("ALLOWED_CORS_ORIGINS", "http://localhost:5173,http://localhost:5174")
ALLOWED_CORS_ORIGINS: list[str] = [o.strip() for o in _cors.split(",") if o.strip()]

# Session validation
SESSION_ID_MAX_LEN: int = 256

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# Bedrock model registry — curated models for the planner/reasoning role.
# The frontend model picker uses this list. Users can switch models per request.
# If BEDROCK_MODELS_JSON is set in .env, it is used; otherwise the default below applies.
# JSON format: [{"id":"model-id","label":"Display name","family":"nova|claude|llama|mistral","tier":"pro|lite","description":"Optional"}]
# ---------------------------------------------------------------------------
_DEFAULT_BEDROCK_MODELS: dict[str, dict] = {
    "us.amazon.nova-pro-v1:0": {"label": "Nova Pro", "family": "nova", "tier": "pro", "description": "Best Nova for reasoning and tool calling"},
    "us.amazon.nova-lite-v1:0": {"label": "Nova Lite", "family": "nova", "tier": "lite", "description": "Faster, cheaper Nova"},
    "us.amazon.nova-2-lite-v1:0": {"label": "Nova 2 Lite", "family": "nova", "tier": "lite", "description": "Latest Nova Lite"},
    "us.anthropic.claude-sonnet-4-6-v1:0": {"label": "Claude Sonnet 4", "family": "claude", "tier": "pro", "description": "Top-tier tool calling, higher cost"},
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": {"label": "Claude 3.5 Haiku", "family": "claude", "tier": "lite", "description": "Fast and cheap Claude"},
    "us.meta.llama3-3-70b-instruct-v1:0": {"label": "Llama 3.3 70B", "family": "llama", "tier": "pro", "description": "Strong open-source reasoning"},
    "mistral.mistral-large-2407-v1:0": {"label": "Mistral Large", "family": "mistral", "tier": "pro", "description": "Good general-purpose model"},
}

def _load_bedrock_models() -> dict[str, dict]:
    raw = os.getenv("BEDROCK_MODELS_JSON", "").strip()
    if not raw:
        return _DEFAULT_BEDROCK_MODELS
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            return _DEFAULT_BEDROCK_MODELS
        out: dict[str, dict] = {}
        for entry in items:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            mid = str(entry["id"]).strip()
            out[mid] = {
                "label": str(entry.get("label") or mid),
                "family": str(entry.get("family") or "nova").strip().lower(),
                "tier": str(entry.get("tier") or "pro").strip().lower(),
                "description": str(entry.get("description") or "").strip(),
            }
        return out if out else _DEFAULT_BEDROCK_MODELS
    except (json.JSONDecodeError, TypeError):
        return _DEFAULT_BEDROCK_MODELS

BEDROCK_MODELS: dict[str, dict] = _load_bedrock_models()
