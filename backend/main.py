from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Consularis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DomainSelection(BaseModel):
    domain: str
    company_name: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/select-domain")
def select_domain(selection: DomainSelection):
    return {
        "message": f"Great choice! We'll analyze {selection.company_name} in the {selection.domain} sector.",
        "domain": selection.domain,
        "company_name": selection.company_name,
        "next_step": "interview",
    }
