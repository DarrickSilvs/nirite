from nirite.schemas import Prospect

def get_canonical_fields() -> set[str]:
    return set(Prospect.model_fields) - {
        "source_file",
        "source_row",
        "extra_fields",
    }

def get_extra_fields(prospects: list[Prospect]) -> list[str]:
    return list(dict.fromkeys(
        key
        for prospect in prospects
        for key in prospect.extra_fields
    ))

# Returns [(kind, key, label), ...]
def get_all_fields(
        prospects: list[Prospect]
) -> list[tuple[str, str, str]]:
    fields = [
        ("canonical", name, name)
        for name in list(get_canonical_fields())
    ]

    fields.extend(
        ("extra", name, f"extra: {name}")
        for name in get_extra_fields(prospects)
    )

    return fields

def check_valid_kind(kind: str):
    if kind not in {"canonical", "extra"}:
        raise ValueError(f"Invalid field: {kind}")

def check_canonical_key(kind: str, key: str):
    if kind.lower() == "canonical" and (
        key not in get_canonical_fields()
    ):
        raise ValueError(f"Invalid canonical field: {key}")

def get_key(kind: str, key: str, prospect: Prospect) -> str:
    if kind.lower() == "canonical":
        return getattr(prospect, key)
    else:
        return prospect.extra_fields.get(key)

def reassign_extra_field(
    prospects: list[Prospect],
    source_kind: str,
    source_key: str,
    target_kind: str,
    target_key: str
) -> None:
    canonical_fields = list(get_canonical_fields())
    check_valid_kind(source_kind)
    check_valid_kind(target_kind)

    check_canonical_key(source_kind, source_key)
    check_canonical_key(target_kind, target_key)

    if source_kind == target_kind and source_key == target_key:
        raise ValueError("Source and destination must be different")

    for prospect in prospects:
        source_value = get_key(source_kind, source_key, prospect)
        target_value = get_key(target_kind, target_key, prospect)

        if not source_value:
            continue

        # Both fields have values, swap them
        if target_value:
            if source_kind == "canonical":
                setattr(prospect, source_key, target_value)
            else:
                prospect.extra_fields[source_key] = target_value

            if target_kind == "canonical":
                setattr(prospect, target_key, source_value)
            else:
                prospect.extra_fields[target_key] = source_value
        else:
            # Destination empty, no swapping
            if target_kind == "canonical":
                setattr(prospect, target_key, source_value)
            else:
                prospect.extra_fields[target_key] = source_value

            # clear source after move
            if source_kind == "canonical":
                setattr(prospect, source_key, None)
            else:
                prospect.extra_fields.pop(source_key, None)

def delete_extra_field(
    prospects: list[Prospect],
    field_name: str,
) -> None:
    for prospect in prospects:
        prospect.extra_fields.pop(field_name, None)
