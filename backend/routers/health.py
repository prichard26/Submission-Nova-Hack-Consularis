"""Health check endpoint: GET /health for liveness probes."""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """Return 200 with status ok when the API is up."""
    return {"status": "ok"}
