from pydantic import Field

from nirite.models.campaign import (
    CampaignModel,
    CriterionKind,
    TargetType,
)

class AnalysisCriterion(CampaignModel):
    id: str
    description: str
    kind: CriterionKind
    source_phrase: str

class CampaignAmbiguity(CampaignModel):
    id: str
    topic: str
    original_term: str
    question: str
    affected_criterion_ids: list[str] = Field(default_factory=list)

class CampaignAnalysis(CampaignModel):
    target_type: TargetType
    objective: str
    target_description: str
    explicit_criteria: list[AnalysisCriterion] = Field(min_length=1)
    ambiguities: list[CampaignAmbiguity] = Field(default_factory=list)