"""Retrieval data models.

Captures per-query results, merged candidates, and final retrieval output.
Prospect data is stored as a plain dict (plus a type tag) to avoid Pydantic
union ambiguity between ``Prospect`` and ``CompanyProspect`` while keeping the
models serialisable and dependency-free.
"""

from pydantic import BaseModel, Field


class ProspectEntry(BaseModel):
    """A prospect with its per-query rank and score from a single retrieval agent."""

    prospect_data: dict
    prospect_type: str  # "individual" or "company"
    score: float = Field(ge=0.0)
    rank: int = Field(ge=1)


class QueryResult(BaseModel):
    """Results from one retrieval agent for one search query."""

    query_id: str
    query: str
    facet: str
    entries: list[ProspectEntry] = Field(default_factory=list)


class Candidate(BaseModel):
    """A deduplicated prospect with final RRF score and retrieval metadata."""

    prospect_data: dict
    prospect_type: str
    final_score: float = Field(ge=0.0)
    rank: int = Field(ge=1)
    queries_found: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)


class RetrievalOutput(BaseModel):
    """Final output of the retrieval pipeline."""

    candidates: list[Candidate] = Field(default_factory=list)
    total_scanned: int = Field(ge=0, default=0)
    tier1_passed: int = Field(ge=0, default=0)
    queries_executed: int = Field(ge=0, default=0)
