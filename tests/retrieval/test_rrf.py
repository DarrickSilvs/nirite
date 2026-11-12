"""Tests for RRF merge and dedup."""

import pytest

from nirite.retrieval.models import Candidate, ProspectEntry, QueryResult
from nirite.retrieval.rrf import rrf_merge


def _entry(prospect_data, prospect_type, score, rank):
    return ProspectEntry(
        prospect_data=prospect_data,
        prospect_type=prospect_type,
        score=score,
        rank=rank,
    )


def _query_result(query_id, entries):
    return QueryResult(
        query_id=query_id,
        query=f"query {query_id}",
        facet="industry",
        entries=entries,
    )


def _prospect_data(name, source_file="f.csv", source_row=1):
    return {"name": name, "source_file": source_file, "source_row": source_row}


def test_rrf_merge_basic_ranking():
    q1 = _query_result(
        "q1",
        [
            _entry(_prospect_data("A", source_row=1), "individual", 0.9, 2),
            _entry(_prospect_data("B", source_row=2), "individual", 0.8, 1),
            _entry(_prospect_data("C", source_row=3), "individual", 0.7, 3),
        ],
    )
    q2 = _query_result(
        "q2",
        [
            _entry(_prospect_data("B", source_row=2), "individual", 0.85, 1),
            _entry(_prospect_data("A", source_row=1), "individual", 0.75, 2),
            _entry(_prospect_data("D", source_row=4), "individual", 0.65, 3),
        ],
    )
    output = rrf_merge([q1, q2], top_n=10)
    assert len(output.candidates) == 4  # A, B, C, D
    # B ranks first in both queries -> highest RRF score, clear winner
    assert output.candidates[0].prospect_data["name"] == "B"
    assert output.candidates[0].queries_found == ["q1", "q2"]


def test_rrf_merge_cross_query_bonus():
    # A appears in both queries, C appears in only one
    q1 = _query_result(
        "q1",
        [
            _entry(_prospect_data("A", source_row=1), "individual", 0.9, 1),
            _entry(_prospect_data("C", source_row=2), "individual", 0.8, 2),
        ],
    )
    q2 = _query_result(
        "q2",
        [
            _entry(_prospect_data("A", source_row=1), "individual", 0.85, 1),
            _entry(_prospect_data("D", source_row=3), "individual", 0.7, 2),
        ],
    )
    output = rrf_merge([q1, q2], top_n=10)
    assert output.candidates[0].prospect_data["name"] == "A"
    assert output.candidates[0].queries_found == ["q1", "q2"]


def test_rrf_merge_single_query():
    q1 = _query_result(
        "q1",
        [
            _entry(_prospect_data("A", source_row=1), "individual", 0.9, 1),
            _entry(_prospect_data("B", source_row=2), "individual", 0.8, 2),
        ],
    )
    output = rrf_merge([q1], top_n=10)
    assert len(output.candidates) == 2
    assert output.candidates[0].prospect_data["name"] == "A"
    assert output.candidates[0].queries_found == ["q1"]


def test_rrf_merge_top_n_limit():
    q1 = _query_result(
        "q1",
        [
            _entry(_prospect_data("A", source_row=1), "individual", 0.9, 1),
            _entry(_prospect_data("B", source_row=2), "individual", 0.8, 2),
            _entry(_prospect_data("C", source_row=3), "individual", 0.7, 3),
        ],
    )
    output = rrf_merge([q1], top_n=2)
    assert len(output.candidates) == 2


def test_rrf_merge_empty_queries():
    output = rrf_merge([], top_n=10)
    assert output.candidates == []
    assert output.queries_executed == 0


def test_rrf_merge_queries_executed_count():
    q1 = _query_result("q1", [_entry(_prospect_data("A", source_row=1), "individual", 0.9, 1)])
    q2 = _query_result("q2", [_entry(_prospect_data("B", source_row=2), "individual", 0.8, 1)])
    output = rrf_merge([q1, q2], top_n=10)
    assert output.queries_executed == 2


def test_rrf_merge_deduplicates_same_prospect():
    # Same prospect (same source_file + source_row) appears in multiple queries
    pdata = _prospect_data("A", "f.csv", 42)
    q1 = _query_result("q1", [_entry(pdata, "individual", 0.9, 1)])
    q2 = _query_result("q2", [_entry(pdata, "individual", 0.85, 2)])
    output = rrf_merge([q1, q2], top_n=10)
    assert len(output.candidates) == 1
    assert output.candidates[0].queries_found == ["q1", "q2"]


def test_rrf_merge_ranks_are_sequential():
    q1 = _query_result(
        "q1",
        [
            _entry(_prospect_data("A", source_row=1), "individual", 0.9, 1),
            _entry(_prospect_data("B", source_row=2), "individual", 0.8, 2),
        ],
    )
    output = rrf_merge([q1], top_n=10)
    assert [c.rank for c in output.candidates] == [1, 2]


def test_rrf_merge_no_cross_query_duplicate():
    q1 = _query_result("q1", [_entry(_prospect_data("A", source_row=1), "individual", 0.9, 1)])
    q2 = _query_result("q2", [_entry(_prospect_data("B", source_row=2), "individual", 0.8, 1)])
    output = rrf_merge([q1, q2], top_n=10)
    assert output.candidates[0].queries_found == ["q1"]
    assert output.candidates[1].queries_found == ["q2"]


def test_rrf_merge_excludes_zero_score_entries():
    # Ticket E: zero-score prospects never accumulate RRF score.
    q1 = _query_result(
        "q1",
        [
            _entry(_prospect_data("A", source_row=1), "individual", 0.9, 1),
            _entry(_prospect_data("B", source_row=2), "individual", 0.0, 2),
        ],
    )
    output = rrf_merge([q1], top_n=10)
    assert len(output.candidates) == 1
    assert output.candidates[0].prospect_data["name"] == "A"
    assert output.candidates[0].queries_found == ["q1"]
