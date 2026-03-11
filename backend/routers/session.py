"""Session lifecycle: init from template vs blank."""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import db
from graph.store import invalidate_session_cache
from routers.validation import validate_session_id

logger = logging.getLogger("consularis")

router = APIRouter(prefix="/api", tags=["session"])


class SessionInitRequest(BaseModel):
    session_id: str
    from_blank: bool = False

    @field_validator("session_id")
    @classmethod
    def session_id_valid(cls, v: str) -> str:
        return validate_session_id(v)


class SessionInitResponse(BaseModel):
    ok: bool = True


@router.post("/session/init", response_model=SessionInitResponse)
def api_session_init(req: SessionInitRequest):
    """Initialize a new session. If from_blank is true, create an empty graph (start + end only). Otherwise no-op (session will be created from template on first graph access)."""
    if req.from_blank:
        try:
            db.init_empty_session(req.session_id)
            invalidate_session_cache(req.session_id)
        except Exception as e:
            logger.exception("session init session_id=%s error: %s", req.session_id, e)
            raise HTTPException(status_code=500, detail="Failed to create blank session.")
    return SessionInitResponse(ok=True)
