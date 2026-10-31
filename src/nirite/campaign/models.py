from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

class CampaignModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True
    )

class TargetType(StrEnum):
    COMPANY = "company"
    PERSON = "person"
    BOTH = "both"

class CriterionKind(StrEnum):
    REQUIREMENT = "requirement"
    EXCLUSION = "exclusion"
    PREFERENCE = "preference"

class EvaluationMode(StrEnum):
    STRUCTURED = "structured"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"

class PredicateOperator(StrEnum):
    EQ = "eq"
    NEQ = "neq"
    CONTAINS = "contains"
    IN = "in"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    EXISTS = "exists"

class SearchFacet(StrEnum):
    INDUSTRY = "industry"
    SERVICE = "service"
    CUSTOMER_TYPE = "customer_type"
    GEOGRAPHY = "geography"
    COMPANY_SIZE = "company_size"
    ROLE = "role"
    ALTERNATIVE_TERMS = "alternative_terms"
    OTHER = "other"

class CampaignStatus(StrEnum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"

PredicateValue = str | int | float | bool | list[str]

class FieldPredicate(CampaignModel):
    field: str
    operator: PredicateOperator
    value : PredicateValue | None = None
    upper_value: PredicateValue | None = None

    @model_validator(mode="after")
    def validate_values(self):
        if self.operator == PredicateOperator.EXISTS:
            if self.value is not None or self.upper_value is not None:
                raise ValueError("EXISTS must not contain comparison values.")
        elif self.value is None:
            raise ValueError("This operator requires a value.")

        if self.operator == PredicateOperator.BETWEEN:
            if self.upper_value is None:
                raise ValueError("BETWEEN requires upper_value.")
        elif self.upper_value is not None:
            raise ValueError("upper_value only for BETWEEN.")

        return self

class Criterion(CampaignModel):
    id: str
    description: str

    kind : CriterionKind
    evaluation_mode = EvaluationMode

    predicate = FieldPredicate | None = None

    weight = float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    evidence_hints: list[str] = Field (
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_evaluation_mode(self):
        if (
            self.evaluation_mode == EvaluationMode.STRUCTURED
            and self.predicate is None
        ):
            raise ValueError("Structured criteria require a predicate.")

        if (
            self.evaluation_mode == EvaluationMode.SEMANTIC
            and self.predicate is not None
        ):
            raise ValueError("Semantic criteria cannot have a predicate.")

        if (
            self.kind != CriterionKind.PREFERENCE
            and self.weight is not None
        ):
            raise ValueError("Only preferences can have a ranking weight.")

        return self

class CampaignSpec(CampaignModel):
    target_type: TargetType

    objective: str
    target_description: str

    criteria: list[Criterion] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def validate_criterion_ids(self):
        ids = [criterion.id for criterion in self.criteria]

        if len(ids) != len(set(ids)):
            raise ValueError("Criterion IDs must be unique.")

        return self

class SearchQuery(CampaignModel):
    id: str
    query: str

    facet: SearchFacet
    rationale: str
        
class QueryPlan(CampaignModel):
    queries: list[SearchQuery] = Field(
        min_length=1,
        max_length=7
    )

    @model_validator(mode="after")
    def validate_queries(self):
        ids = [query.id for query in self.queries]

        if len(ids) != len(set(ids)):
            raise ValueError("Query IDs must be unique.")

        normalised = [
            query.query.casefold()
            for query in self.queries
        ]

        if len(normalised) != len(set(normalised)):
            raise ValueError("Duplicate search queries are not allowed.")

        return self

class Clarification(CampaignModel):
    question: str
    reason: str

    related_criterion_ids: list[str] = Field(
        default_factory=list
    )

class CampaignDefinition(CampaignModel):
    original_prompt: str

    spec: CampaignSpec
    query_plan: QueryPlan

    status: CampaignStatus

    clarifications: list[Clarification] = Field(
        default_factory=list
    )

    schema_version: int = 1
    version: int = 1

    @model_validator(mode="after")
    def validate_status(self):
        if (
            self.status == CampaignStatus.NEEDS_CLARIFICATION
            and not self.clarifications
        ):
            raise ValueError(
                "A campaign needing clarification "
                "must contain at least one question."
            )

        return self
    