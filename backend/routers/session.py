"""Session lifecycle: init from template vs blank."""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import db
from graph.store import invalidate_session_cache
from routers.validation import validate_session_id

logger = logging.getLogger("consularis")

router = APIRouter(prefix="/api", tags=["session"])

VALID_TEMPLATE_IDS = frozenset({
    "pharmacy", "logistics", "manufacturing",
    "retail", "restaurant", "electrician", "plumber", "cleaning",
    "blank",
})


class SessionInitRequest(BaseModel):
    session_id: str
    from_blank: bool = False
    template_id: str | None = None

    @field_validator("session_id")
    @classmethod
    def session_id_valid(cls, v: str) -> str:
        return validate_session_id(v)

    @field_validator("template_id")
    @classmethod
    def template_id_valid(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if v not in VALID_TEMPLATE_IDS:
            raise ValueError(f"template_id must be one of {sorted(VALID_TEMPLATE_IDS)}")
        return v


class SessionInitResponse(BaseModel):
    ok: bool = True


@router.post("/session/init", response_model=SessionInitResponse)
def api_session_init(req: SessionInitRequest):
    """Initialize a new session. If from_blank or template_id=blank: empty graph. If template_id=pharmacy: clone baseline. If template_id=logistics|manufacturing: clone that template. Otherwise no-op."""
    tid = req.template_id
    if req.from_blank or tid == "blank":
        try:
            db.init_empty_session(req.session_id)
            invalidate_session_cache(req.session_id)
        except Exception as e:
            logger.exception("session init session_id=%s error: %s", req.session_id, e)
            raise HTTPException(status_code=500, detail="Failed to create blank session.")
        return SessionInitResponse(ok=True)
    if tid == "pharmacy":
        try:
            db.force_clone_baseline_to_session(req.session_id)
            invalidate_session_cache(req.session_id)
        except Exception as e:
            logger.exception("session init pharmacy session_id=%s error: %s", req.session_id, e)
            raise HTTPException(status_code=500, detail="Failed to load pharmacy template.")
        return SessionInitResponse(ok=True)
    if tid in ("logistics", "manufacturing", "retail", "restaurant", "electrician", "plumber", "cleaning"):
        try:
            db.clone_template_to_session(req.session_id, tid)
            invalidate_session_cache(req.session_id)
        except (ValueError, FileNotFoundError) as e:
            logger.exception("session init template_id=%s session_id=%s error: %s", tid, req.session_id, e)
            raise HTTPException(status_code=500, detail=f"Failed to load template: {tid}")
        except Exception as e:
            logger.exception("session init template_id=%s session_id=%s error: %s", tid, req.session_id, e)
            raise HTTPException(status_code=500, detail=f"Failed to load template: {tid}")
        return SessionInitResponse(ok=True)
    return SessionInitResponse(ok=True)
