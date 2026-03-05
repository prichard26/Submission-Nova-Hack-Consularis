"""Session lifecycle: init from template vs blank."""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import db
from config import SESSION_ID_MAX_LEN

logger = logging.getLogger("consularis")

router = APIRouter(prefix="/api", tags=["session"])


class SessionInitRequest(BaseModel):
    session_id: str
    from_blank: bool = False

    @field_validator("session_id")
    @classmethod
    def session_id_valid(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("session_id is required")
        if len(v) > SESSION_ID_MAX_LEN:
            raise ValueError(f"session_id must be at most {SESSION_ID_MAX_LEN} characters")
        return v


class SessionInitResponse(BaseModel):
    ok: bool = True


@router.post("/session/init", response_model=SessionInitResponse)
def api_session_init(req: SessionInitRequest):
    """Initialize a new session. If from_blank is true, create an empty graph (start + end only). Otherwise no-op (session will be created from template on first graph access)."""
    if req.from_blank:
        try:
            db.init_empty_session(req.session_id)
        except Exception as e:
            logger.exception("session init session_id=%s error: %s", req.session_id, e)
            raise HTTPException(status_code=500, detail="Failed to create blank session.")
    return SessionInitResponse(ok=True)
