"""Paper-facing task names, without changing stored episode identifiers."""

FAMILY_ALIASES = {
    "PG": "S1_pixel_grounding",
    "DA": "S2_distance_approach",
    "VS": "S3_view_search",
    "SV": "S4_state_recognition",
    "AI": "T1_grounded_interaction",
    "SI": "T2_search_then_interact",
    "SM": "T3_sequential_manipulation",
    "CR": "T4_constraint_resolving",
}


def normalize_family(value: str) -> str:
    return FAMILY_ALIASES.get(value.strip().upper(), value.strip())
