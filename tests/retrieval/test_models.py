"""Tests for retrieval models."""

import pytest

from nirite.retrieval.models import (
    Candidate,
    ProspectEntry,
    QueryResult,
    RetrievalOutput,
)


def test_prospect_entry_creation():
    entry = ProspectEntry(
        prospect_data={"company_name": "Acme", "source_file": "f.csv", "source_row": 1},
        prospect_type="company",
        score=0.95,
        rank=1,
    )
    assert entry.score == 0.95
    assert entry.rank == 1
    assert entry.prospect_type == "company"
    assert entry.prospect_data["company_name"] == "Acme"


def test_query_result_creation():
    entry = ProspectEntry(
        prospect_data={"company_name": "Acme", "source_file": "f.csv", "source_row": 1},
        prospect_type="company",
        score=0.9,
        rank=1,
    )
    result = QueryResult(
        query_id="q1",
        query="Australian SaaS companies",
        facet="industry",
        entries=[entry],
    )
    assert result.query_id == "q1"
    assert result.query == "Australian SaaS companies"
    assert result.facet == "industry"
    assert len(result.entries) == 1
    assert result.entries[0].score == 0.9


def test_query_result_default_entries():
    result = QueryResult(
        query_id="q1",
        query="test query",
        facet="other",
    )
    assert result.entries == []


def test_candidate_creation():
    candidate = Candidate(
        prospect_data={"company_name": "Acme", "source_file": "f.csv", "source_row": 1},
        prospect_type="company",
        final_score=0.85,
        rank=1,
        queries_found=["q1", "q2"],
        match_reasons=["matched industry", "matched location"],
    )
    assert candidate.final_score == 0.85
    assert candidate.rank == 1
    assert candidate.queries_found == ["q1", "q2"]
    assert candidate.match_reasons == ["matched industry", "matched location"]


def test_candidate_defaults():
    candidate = Candidate(
        prospect_data={"source_file": "f.csv", "source_row": 1},
        prospect_type="individual",
        final_score=0.5,
        rank=3,
    )
    assert candidate.queries_found == []
    assert candidate.match_reasons == []


def test_retrieval_output_creation():
    candidate = Candidate(
        prospect_data={"source_file": "f.csv", "source_row": 1},
        prospect_type="individual",
        final_score=0.9,
        rank=1,
    )
    output = RetrievalOutput(
        candidates=[candidate],
        total_scanned=1000,
        tier1_passed=500,
        queries_executed=3,
    )
    assert len(output.candidates) == 1
    assert output.total_scanned == 1000
    assert output.tier1_passed == 500
    assert output.queries_executed == 3


def test_retrieval_output_defaults():
    output = RetrievalOutput()
    assert output.candidates == []
    assert output.total_scanned == 0
    assert output.tier1_passed == 0
    assert output.queries_executed == 0
