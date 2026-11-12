"""Tier 1 — deterministic requirements/exclusions filter.

Applies structured predicate criteria (requirements and exclusions only;
preferences and semantic/hybrid criteria are intentionally skipped here) to
reduce a large prospect list to a manageable subset before Tier 2 retrieval.

Zero LLM cost, O(n).
"""

from nirite.ingestion.normalizer import ALIASES, GEO_HIERARCHY
from nirite.models.campaign import CriterionKind, EvaluationMode
from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect


def get_field_value(prospect: Prospect | CompanyProspect, field_name: str) -> str | None:
    """Read a field from a prospect, checking canonical fields then extra_fields.

    When the field is stored under a variant name, resolve it through ALIASES:
    the canonical field and its aliases are matched as exact extra_fields keys,
    then as keys sharing a word token (e.g. predicate ``city`` reads
    ``town``, ``city name``, ``person city`` or ``company city``).
    """

    value = getattr(prospect, field_name, None)
    if value is not None:
        return value

    extra_fields = prospect.extra_fields
    value = extra_fields.get(field_name)
    if value is not None:
        return value

    names: list[str] = []
    for canonical, aliases in ALIASES.items():
        if field_name == canonical or field_name in aliases:
            names = [canonical, *aliases]
            break

    for name in names:
        value = extra_fields.get(name)
        if value is not None:
            return value

    if names:
        wanted = {word for name in names for word in name.lower().split()}
        for key, value in extra_fields.items():
            if {word for word in key.lower().split()} & wanted:
                return value

    return None


def _as_str(value) -> str:
    return str(value).strip() if value is not None else ""


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_predicate(
    field_value: str | None,
    operator: str,
    value,
    upper_value=None,
) -> bool:
    """Apply a single predicate operator to a field value.

    Returns False when the field value is missing or cannot be compared
    (e.g. non-numeric value for a numeric operator).
    """

    if field_value is None:
        return False

    f_str = _as_str(field_value)

    if operator == "eq":
        return f_str.lower() == str(value).lower()
    if operator == "neq":
        return f_str.lower() != str(value).lower()
    if operator == "contains":
        return str(value).lower() in f_str.lower()
    if operator == "in":
        return f_str.lower() in [str(v).lower() for v in value]
    if operator == "exists":
        return f_str != ""

    # Numeric operators require numeric conversion on both sides.
    f_num = _to_float(f_str)
    if f_num is None:
        return False

    if operator == "gt":
        v_num = _to_float(value)
        return v_num is not None and f_num > v_num
    if operator == "gte":
        v_num = _to_float(value)
        return v_num is not None and f_num >= v_num
    if operator == "lt":
        v_num = _to_float(value)
        return v_num is not None and f_num < v_num
    if operator == "lte":
        v_num = _to_float(value)
        return v_num is not None and f_num <= v_num
    if operator == "between":
        lo = _to_float(value)
        hi = _to_float(upper_value)
        return lo is not None and hi is not None and lo <= f_num <= hi

    return False


def _criterion_applies(criterion) -> bool:
    """True if a criterion should be enforced in Tier 1 (structured only,
    requirement or exclusion, with a predicate)."""

    return (
        criterion.evaluation_mode == EvaluationMode.STRUCTURED
        and criterion.kind in {CriterionKind.REQUIREMENT, CriterionKind.EXCLUSION}
        and criterion.predicate is not None
    )


def _expand_geo_predicate(field, operator, value):
    """Expand country=X into state/city-within-X checks via GEO_HIERARCHY.

    Legacy prospects that ingestion never enriched (country missing, state/
    city present) still match a country requirement. Only country eq/in
    predicates are expanded; everything else is a single pass-through check.
    _prospect_passes ORs the returned checks.
    """
    if field != "country" or operator not in ("eq", "in"):
        return [(field, operator, value)]

    checks = [(field, operator, value)]
    countries = [value] if operator == "eq" else list(value)
    for country in countries:
        hierarchy = GEO_HIERARCHY.get(country, {})
        for state in hierarchy.get("states", set()):
            checks.append(("state", "eq", state))
        for city in hierarchy.get("cities", set()):
            checks.append(("city", "eq", city))
    return checks


def _prospect_passes(predicate, prospect: Prospect | CompanyProspect) -> bool:
    """True if ANY expanded check matches (OR logic for geo expansion)."""
    return any(
        evaluate_predicate(
            get_field_value(prospect, field),
            operator,
            value,
            predicate.upper_value,
        )
        for field, operator, value in _expand_geo_predicate(
            predicate.field.value,
            predicate.operator.value,
            predicate.value,
        )
    )


def tier1_filter(prospects: list[Prospect | CompanyProspect], spec) -> list[Prospect | CompanyProspect]:
    """Filter prospects through Tier 1 deterministic rules.

    Returns a new list; the input is never mutated.

    Requirements with structured predicates must pass.
    Exclusions with structured predicates must not match.
    Semantic/hybrid criteria and preferences are intentionally skipped.
    """

    requirements = [
        c for c in spec.criteria if _criterion_applies(c) and c.kind == CriterionKind.REQUIREMENT
    ]
    exclusions = [
        c for c in spec.criteria if _criterion_applies(c) and c.kind == CriterionKind.EXCLUSION
    ]

    result: list[Prospect | CompanyProspect] = []
    for prospect in prospects:
        if requirements and not all(
            _prospect_passes(c.predicate, prospect) for c in requirements
        ):
            continue
        if exclusions and any(
            _prospect_passes(c.predicate, prospect) for c in exclusions
        ):
            continue
        result.append(prospect)

    return result
