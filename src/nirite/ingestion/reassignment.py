from pydantic import BaseModel

from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect

ProspectLike = Prospect | CompanyProspect


def get_canonical_fields(model_class: type[BaseModel] = Prospect) -> list[str]:
    excluded = {"source_file", "source_row", "extra_fields"}

    return [
        name
        for name in model_class.model_fields
        if name not in excluded
    ]


def get_extra_fields(prospects: list[ProspectLike]) -> list[str]:
    return list(dict.fromkeys(
        key
        for prospect in prospects
        for key in prospect.extra_fields
    ))


def _model_class_for(prospects: list[ProspectLike]) -> type[BaseModel]:
    if prospects and isinstance(prospects[0], CompanyProspect):
        return CompanyProspect
    return Prospect


# Returns [(kind, key, label), ...]
def get_all_fields(
    prospects: list[ProspectLike]
) -> list[tuple[str, str, str]]:
    fields = [
        ("canonical", name, name)
        for name in get_canonical_fields(_model_class_for(prospects))
    ]

    fields.extend(
        ("extra", name, f"extra: {name}")
        for name in get_extra_fields(prospects)
    )

    return fields


def check_valid_kind(kind: str):
    if kind not in {"canonical", "extra"}:
        raise ValueError(f"Invalid field: {kind}")


def check_canonical_key(kind: str, key: str, model_class: type[BaseModel] = Prospect) -> None:
    if kind.lower() == "canonical" and (
        key not in get_canonical_fields(model_class)
    ):
        raise ValueError(f"Invalid canonical field: {key}")


def get_key(kind: str, key: str, prospect: ProspectLike) -> str | None:
    if kind.lower() == "canonical":
        return getattr(prospect, key)
    else:
        return prospect.extra_fields.get(key)


def set_key(
    kind: str,
    key: str,
    prospect: ProspectLike,
    value: str | None,
) -> None:
    if kind.lower() == "canonical":
        setattr(prospect, key, value)
    elif value is None:
        prospect.extra_fields.pop(key, None)
    else:
        prospect.extra_fields[key] = value


def reassign_field(
    prospects: list[ProspectLike],
    source_kind: str,
    source_key: str,
    target_kind: str,
    target_key: str
) -> None:
    """Move or swap one column of values, decided once for the whole column.

    If the destination holds a value in any record, the two fields are
    swapped in every record (empty values included), so a mislabelled pair of
    columns is corrected consistently. Otherwise the source is moved into the
    empty destination and cleared.
    """
    check_valid_kind(source_kind)
    check_valid_kind(target_kind)

    model_class = _model_class_for(prospects)
    check_canonical_key(source_kind, source_key, model_class)
    check_canonical_key(target_kind, target_key, model_class)

    if source_kind == target_kind and source_key == target_key:
        raise ValueError("Source and destination must be different")

    swap = any(
        get_key(target_kind, target_key, prospect)
        for prospect in prospects
    )

    for prospect in prospects:
        source_value = get_key(source_kind, source_key, prospect) or None
        target_value = get_key(target_kind, target_key, prospect) or None

        if swap:
            set_key(source_kind, source_key, prospect, target_value)
            set_key(target_kind, target_key, prospect, source_value)
        elif source_value is not None:
            set_key(target_kind, target_key, prospect, source_value)
            set_key(source_kind, source_key, prospect, None)


def delete_extra_field(
    prospects: list[ProspectLike],
    field_name: str,
) -> None:
    for prospect in prospects:
        prospect.extra_fields.pop(field_name, None)
