"""Fixture builders for constructing campaign/retrieval model objects in tests.

Builders use sensible defaults so tests only override what matters. All
builders return Pydantic model instances (never dicts), matching how the
production code consumes them.
"""

from __future__ import annotations

from nirite.campaign.llm.providers import LLMProvider
from nirite.models.campaign import (
    CampaignDefinition,
    CampaignSpec,
    Criterion,
    CriterionKind,
    EvaluationMode,
    FieldPredicate,
    PredicateField,
    PredicateOperator,
    QueryPlan,
    SearchFacet,
    SearchQuery,
    TargetType,
)
from nirite.models.campaign_analysis import (
    AnalysisCriterion,
    CampaignAmbiguity,
    CampaignAnalysis,
)
from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect


def build_prospect(
    *,
    source_file: str = "prospects.csv",
    source_row: int = 1,
    full_name: str = "Jane Doe",
    job_title: str = "Engineering Manager",
    company_name: str = "Acme Corp",
    country: str = "Australia",
    **extra: str,
) -> Prospect:
    """Build a ``Prospect`` with optional overrides and extra fields."""
    return Prospect(
        full_name=full_name,
        job_title=job_title,
        company_name=company_name,
        country=country,
        extra_fields=extra,
        source_file=source_file,
        source_row=source_row,
    )


def build_company_prospect(
    *,
    source_file: str = "companies.csv",
    source_row: int = 1,
    company_name: str = "Acme Corp",
    industry: str = "SaaS",
    company_size: str = "51-200",
    country: str = "Australia",
    description: str | None = None,
    **extra: str,
) -> CompanyProspect:
    """Build a ``CompanyProspect`` with optional overrides and extra fields."""
    return CompanyProspect(
        company_name=company_name,
        industry=industry,
        company_size=company_size,
        country=country,
        description=description,
        extra_fields=extra,
        source_file=source_file,
        source_row=source_row,
    )


def build_criterion(
    *,
    id: str = "c1",
    description: str = "Must be based in Australia",
    kind: CriterionKind = CriterionKind.REQUIREMENT,
    evaluation_mode: EvaluationMode = EvaluationMode.STRUCTURED,
    predicate_field: PredicateField | None = PredicateField.COUNTRY,
    predicate_operator: PredicateOperator | None = PredicateOperator.EQ,
    predicate_value: str | None = "Australia",
    weight: float | None = None,
    evidence_hints: list[str] | None = None,
) -> Criterion:
    """Build a ``Criterion`` with optional overrides."""
    predicate = None
    if predicate_field is not None:
        predicate = FieldPredicate(
            field=predicate_field,
            operator=predicate_operator,
            value=predicate_value,
        )
    return Criterion(
        id=id,
        description=description,
        kind=kind,
        evaluation_mode=evaluation_mode,
        predicate=predicate,
        weight=weight,
        evidence_hints=evidence_hints or [],
    )


def build_analysis(
    *,
    target_type: TargetType = TargetType.COMPANY,
    objective: str = "Find suitable companies",
    target_description: str = "Australian SaaS companies",
    criteria: list[AnalysisCriterion] | None = None,
    ambiguities: list[CampaignAmbiguity] | None = None,
) -> CampaignAnalysis:
    """Build a ``CampaignAnalysis`` with optional overrides."""
    if criteria is None:
        criteria = [
            AnalysisCriterion(
                id="c1",
                description="Must be based in Australia",
                kind=CriterionKind.REQUIREMENT,
                source_phrase="Australian companies",
            )
        ]
    return CampaignAnalysis(
        target_type=target_type,
        objective=objective,
        target_description=target_description,
        explicit_criteria=criteria,
        ambiguities=ambiguities or [],
    )


def build_definition(
    *,
    original_prompt: str = "Find Australian SaaS companies",
    target_type: TargetType = TargetType.COMPANY,
    objective: str = "Find suitable companies",
    target_description: str = "Australian SaaS companies",
    criteria: list[Criterion] | None = None,
    queries: list[SearchQuery] | None = None,
) -> CampaignDefinition:
    """Build a ``CampaignDefinition`` with optional overrides."""
    if criteria is None:
        criteria = [
            build_criterion(
                id="c1",
                description="Must be based in Australia",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
            )
        ]
    if queries is None:
        queries = [
            SearchQuery(
                id="q1",
                query="SaaS companies Australia",
                facet=SearchFacet.INDUSTRY,
                rationale="Find SaaS companies in Australia",
            )
        ]
    return CampaignDefinition(
        original_prompt=original_prompt,
        spec=CampaignSpec(
            target_type=target_type,
            objective=objective,
            target_description=target_description,
            criteria=criteria,
        ),
        query_plan=QueryPlan(queries=queries),
    )


def build_search_query(
    *,
    id: str = "q1",
    query: str = "SaaS companies Australia",
    facet: SearchFacet = SearchFacet.INDUSTRY,
    rationale: str = "Find SaaS companies in Australia",
) -> SearchQuery:
    """Build a ``SearchQuery`` with optional overrides."""
    return SearchQuery(id=id, query=query, facet=facet, rationale=rationale)


def build_analysis_criterion(
    *,
    id: str = "c1",
    description: str = "Must be based in Australia",
    kind: CriterionKind = CriterionKind.REQUIREMENT,
    source_phrase: str = "Australian companies",
) -> AnalysisCriterion:
    """Build an ``AnalysisCriterion`` with optional overrides."""
    return AnalysisCriterion(
        id=id,
        description=description,
        kind=kind,
        source_phrase=source_phrase,
    )


def build_campaign_ambiguity(
    *,
    id: str = "a1",
    topic: str = "Company size",
    original_term: str = "mid-sized",
    question: str = "How do you define mid-sized?",
    affected_criterion_ids: list[str] | None = None,
) -> CampaignAmbiguity:
    """Build a ``CampaignAmbiguity`` with optional overrides."""
    return CampaignAmbiguity(
        id=id,
        topic=topic,
        original_term=original_term,
        question=question,
        affected_criterion_ids=affected_criterion_ids or [],
    )


class FakeProvider(LLMProvider):
    """Minimal ``LLMProvider`` double for tests that need a provider instance.

    Unlike ``FakeLLMProvider`` in ``fakes.py``, this is a Protocol-compatible
    class usable wherever ``LLMProvider`` is type-checked.
    """

    def __init__(self, response: str = '{"ok": true}') -> None:
        self._response = response
        self.call_log: list[tuple[str, str, dict]] = []
        self.call_count = 0

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
    ) -> str:
        self.call_log.append((system_prompt, user_prompt, schema))
        self.call_count += 1
        return self._response
