"""Domain selection endpoint."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["domain"])


class DomainSelection(BaseModel):
    domain: str
    company_name: str


@router.post("/select-domain")
def select_domain(selection: DomainSelection):
    return {
        "message": f"Great choice! We'll analyze {selection.company_name} in the {selection.domain} sector.",
        "domain": selection.domain,
        "company_name": selection.company_name,
        "next_step": "interview",
    }
