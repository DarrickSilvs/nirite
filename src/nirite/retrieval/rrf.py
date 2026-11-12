"""Reciprocal Rank Fusion (RRF) merge + dedup.

Combines per-query ranked results into a single ranked candidate list using
RRF:  score = sum(1 / (k + rank_in_query))  with k = 60.

Cross-query appearance is naturally rewarded by RRF (each query a prospect
appears in adds another term to the sum).  An additional cross-query bonus
multiplier is applied based on how many distinct queries surfaced the prospect.
"""

from nirite.retrieval.models import Candidate, ProspectEntry, QueryResult, RetrievalOutput

RRF_K = 60


def dedup_key(prospect_data: dict) -> str:
    """Build a stable dedup key from a prospect's source tracking fields."""
    return f"{prospect_data.get('source_file', '')}:{prospect_data.get('source_row', '')}"


def rrf_merge(
    query_results: list[QueryResult],
    top_n: int = 20,
    k: int = RRF_K,
    tier1_passed: int = 0,
) -> RetrievalOutput:
    """Merge and rank QueryResults using Reciprocal Rank Fusion.

    Returns a new RetrievalOutput; inputs are never mutated.

    Args:
        query_results: Per-query ranked results from retrieval agents.
        top_n: Maximum number of candidates to return.
        k: RRF ranking constant (default 60).
        tier1_passed: Number of prospects that passed Tier 1 filtering.
    """
    if not query_results:
        return RetrievalOutput(
            queries_executed=0,
            tier1_passed=tier1_passed,
        )

    # Accumulate RRF scores and metadata per prospect.
    scores: dict[str, float] = {}
    query_buckets: dict[str, list[str]] = {}
    reasons: dict[str, list[str]] = {}
    prospect_by_key: dict[str, dict] = {}
    prospect_type_by_key: dict[str, str] = {}

    for result in query_results:
        for entry in result.entries:
            if entry.score <= 0:
                # Belt-and-suspenders on agent-level cutoffs (Ticket D):
                # zero-score prospects never accumulate RRF score.
                continue
            key = dedup_key(entry.prospect_data)
            prospect_by_key[key] = entry.prospect_data
            prospect_type_by_key[key] = entry.prospect_type

            scores[key] = scores.get(key, 0.0) + 1.0 / (k + entry.rank)
            if result.query_id not in query_buckets.get(key, []):
                query_buckets.setdefault(key, []).append(result.query_id)
            reasons.setdefault(key, []).append(
                f"matched '{result.query}' (rank {entry.rank})"
            )

    # Compute final scores with cross-query bonus, then sort and assign ranks.
    # Sort by descending score, then by descending number of queries found
    # (cross-query bonus already applied, but more queries = stronger signal),
    # then by key for deterministic ordering on exact ties.
    scored: list[tuple[str, float, int]] = []
    for key, base_score in scores.items():
        num_queries = len(query_buckets.get(key, []))
        # Cross-query bonus: 1 + 0.25 * (additional queries beyond the first).
        bonus = 1.0 + 0.25 * max(0, num_queries - 1)
        final_score = base_score * bonus
        scored.append((key, final_score, num_queries))

    scored.sort(key=lambda item: (-item[1], -item[2], item[0]))

    candidates: list[Candidate] = []
    for rank, (key, final_score, _) in enumerate(scored, start=1):
        candidates.append(
            Candidate(
                prospect_data=prospect_by_key[key],
                prospect_type=prospect_type_by_key[key],
                final_score=round(final_score, 6),
                rank=rank,
                queries_found=sorted(query_buckets.get(key, [])),
                match_reasons=reasons.get(key, []),
            )
        )

    top = candidates[:top_n]

    return RetrievalOutput(
        candidates=top,
        total_scanned=sum(len(r.entries) for r in query_results),
        tier1_passed=tier1_passed,
        queries_executed=len(query_results),
    )
