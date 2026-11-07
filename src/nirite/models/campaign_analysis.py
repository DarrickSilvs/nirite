from pydantic import Field, model_validator

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

    @model_validator(mode="after")
    def validate_references(self):
        criterion_ids = [c.id for c in self.explicit_criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Criterion IDs must be unique.")

        ambiguity_ids = [a.id for a in self.ambiguities]
        if len(ambiguity_ids) != len(set(ambiguity_ids)):
            raise ValueError("Ambiguity IDs must be unique.")

        known = set(criterion_ids)
        for ambiguity in self.ambiguities:
            unknown = set(ambiguity.affected_criterion_ids) - known
            if unknown:
                raise ValueError(
                    f"Ambiguity {ambiguity.id} references unknown "
                    f"criteria: {sorted(unknown)}"
                )

        return self