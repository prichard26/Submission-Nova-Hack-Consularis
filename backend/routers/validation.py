"""Shared validators for router request models."""
from fastapi import HTTPException
from config import SESSION_ID_MAX_LEN


def validate_session_id(v: str) -> str:
    """Pydantic field_validator for session_id: strip, check empty, check max length."""
    v = (v or "").strip()
    if not v:
        raise ValueError("session_id is required")
    if len(v) > SESSION_ID_MAX_LEN:
        raise ValueError(f"session_id must be at most {SESSION_ID_MAX_LEN} characters")
    return v


def validate_session_id_or_400(session_id: str) -> None:
    """Raise HTTPException 400 if session_id is invalid (for non-Pydantic endpoints)."""
    if not session_id or not str(session_id).strip():
        raise HTTPException(status_code=400, detail="session_id is required")
    if len(session_id) > SESSION_ID_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"session_id must be at most {SESSION_ID_MAX_LEN} characters")
