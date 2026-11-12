from enum import StrEnum

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

class PredicateField(StrEnum):
    FULL_NAME = "full_name"
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    JOB_TITLE = "job_title"
    COMPANY_NAME = "company_name"
    COMPANY_DOMAIN = "company_domain"
    COMPANY_WEBSITE = "company_website"
    PROFILE_URL = "profile_url"
    EMAIL = "email"
    COUNTRY = "country"
    STATE = "state"
    CITY = "city"
    INDUSTRY = "industry"
    COMPANY_SIZE = "company_size"
    REGION = "region"
    LINKEDIN_URL = "linkedin_url"
    DESCRIPTION = "description"
    
class FieldPredicate(CampaignModel):
    field: PredicateField
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

    kind: CriterionKind = Field(
        description=(
            "Whether this criterion is a hard requirement, "
            "disqualifying exclusion, or ranking preference."
        )
    )
    evaluation_mode: EvaluationMode

    predicate: FieldPredicate | None = None

    weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Optional ranking weight between 0 and 1. "
            "Only applicable to preference criteria. "
            "Must be null or omitted for requirements and exclusions."
        ),
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

    status: CampaignStatus = CampaignStatus.READY

    clarifications: list[Clarification] = Field(
        default_factory=list
    )

    schema_version: int = 1
    version: int = 1

    @model_validator(mode="before")
    @classmethod
    def determine_status(cls, data):
        if not isinstance(data, dict):
            return data

        data = data.copy()
        clarifications = data.get("clarifications") or []

        data["status"] = (
            CampaignStatus.NEEDS_CLARIFICATION
            if clarifications
            else CampaignStatus.READY
        )

        return data

    @model_validator(mode="after")
    def validate_clarification_references(self):
        known = {criterion.id for criterion in self.spec.criteria}

        for clarification in self.clarifications:
            unknown = set(clarification.related_criterion_ids) - known
            if unknown:
                raise ValueError(
                    "Clarification references unknown criterion IDs: "
                    f"{sorted(unknown)}"
                )

        return self