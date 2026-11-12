"""Retrieval pipeline — orchestrates Tier 1 filter → Tier 2 agents → RRF → top-N.

Input:  prospect list (Layer 0 output) + CampaignDefinition (Layer 1 output).
Output: RetrievalOutput with ranked, deduplicated Candidate objects.
"""

from nirite.models.campaign import CampaignDefinition
from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect

from nirite.retrieval.agents import ListRetrievalAgent, SemanticRetrievalAgent
from nirite.retrieval.models import ProspectEntry, QueryResult, RetrievalOutput
from nirite.retrieval.rrf import dedup_key, rrf_merge
from nirite.retrieval.tier1_filter import tier1_filter


def run(
    prospects: list[Prospect | CompanyProspect],
    campaign: CampaignDefinition,
    top_n: int = 20,
) -> RetrievalOutput:
    """Run the full Layer 2 retrieval pipeline.

    1. Tier 1 — deterministic requirements/exclusions filter.
    2. Tier 2 — ListRetrievalAgent + SemanticRetrievalAgent per query.
    3. RRF merge + dedup → ranked candidates.
    4. Return top-N.

    Does not mutate ``prospects``.
    """

    spec = campaign.spec
    query_plan = campaign.query_plan

    # Step 1: Tier 1 deterministic filter.
    tier1_passed = tier1_filter(prospects, spec)
    total_scanned = len(prospects)

    # Step 2: Tier 2 — retrieval agents per query.
    list_agent = ListRetrievalAgent()
    semantic_agent = SemanticRetrievalAgent()

    query_results: list[QueryResult] = []
    for query in query_plan.queries:
        list_entries = list_agent.retrieve(tier1_passed, query.query, query.id)
        semantic_entries = semantic_agent.retrieve(tier1_passed, query.query, query.id)

        # Merge per-query results: union of both agents, best rank wins.
        merged: dict[str, ProspectEntry] = {}
        for entry in list_entries + semantic_entries:
            key = dedup_key(entry.prospect_data)
            if key not in merged or entry.rank < merged[key].rank:
                merged[key] = entry

        query_results.append(
            QueryResult(
                query_id=query.id,
                query=query.query,
                facet=query.facet.value,
                entries=list(merged.values()),
            )
        )

    # Step 3: RRF merge + dedup.
    output = rrf_merge(
        query_results,
        top_n=top_n,
        tier1_passed=len(tier1_passed),
    )
    output.total_scanned = total_scanned

    return output
