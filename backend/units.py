"""Central unit registry and conversion helpers."""

UNIT_LABELS = {
    "mm": "mm", "cm": "cm",
    "MPa": "MPa", "N/mm2": "N/mm²", "kgf/cm2": "kgf/cm²", "kg/cm2": "kgf/cm²", "psi": "psi",
    "kN": "kN", "N": "N",
    "mm2": "mm²", "cm2": "cm²",
    "kg": "kg", "g": "g",
}

CONVERSIONS: dict[tuple[str, str], float] = {
    # Slump
    ("mm", "cm"): 0.1,
    ("cm", "mm"): 10.0,
    # Strength (canonical = MPa == N/mm²)
    ("MPa", "N/mm2"): 1.0,
    ("N/mm2", "MPa"): 1.0,
    ("MPa", "kgf/cm2"): 10.19716213,
    ("kgf/cm2", "MPa"): 1 / 10.19716213,
    ("MPa", "psi"): 145.037738,
    ("psi", "MPa"): 1 / 145.037738,
    ("N/mm2", "kgf/cm2"): 10.19716213,
    ("kgf/cm2", "N/mm2"): 1 / 10.19716213,
    # Area
    ("mm2", "cm2"): 0.01,
    ("cm2", "mm2"): 100.0,
    # Load
    ("kN", "N"): 1000.0,
    ("N", "kN"): 0.001,
    # Weight
    ("kg", "g"): 1000.0,
    ("g", "kg"): 0.001,
}


def convert(value: float | None, source: str, target: str) -> float | None:
    if value is None:
        return None
    if not source or source == target:
        return value
    factor = CONVERSIONS.get((source, target))
    if factor is None:
        return value
    return round(value * factor, 3)


def convert_for_display(value: float | None, canonical_unit: str, preferred_unit: str | None) -> tuple[float | None, str]:
    if value is None:
        return None, preferred_unit or canonical_unit
    target = preferred_unit or canonical_unit
    return convert(value, canonical_unit, target), target
