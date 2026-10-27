"""Guided ASCE 41-23 §4.4.3.3 average shear stress calculation.

The original calculator in ``calcs/`` is a useful interactive reference, but
it depends on Streamlit and pandas.  This module keeps the calculation itself
small, deterministic, and usable by the Flask workflow and automated tests.
It does not make an engineering determination: the engineer must explicitly
record whether the result is compliant or noncompliant.
"""

from __future__ import annotations

from typing import Any


SHEAR_WALL_CALCULATION_TYPE = "asce41_4433_average_shear_stress"
SOURCE_REFERENCE = "calcs/asce41_4433_shear_wall_app_TABLE47_FIXED.py"

STORY_BANDS = ("1", "2", "3", "4 or more")
STORY_INDEX = {label: index for index, label in enumerate(STORY_BANDS)}

C_TABLE: dict[str, list[float]] = {
    "Wood and cold-formed steel shear wall (W1, W1a, W2, CFS1)": [1.3, 1.1, 1.0, 1.0],
    "Moment frame (S1, S3, C1, PC2a)": [1.3, 1.1, 1.0, 1.0],
    "Shear wall (S4, S5, C2, C3, PC1a, PC2, RM2, URMa)": [1.4, 1.2, 1.1, 1.0],
    "Braced frame (S2)": [1.4, 1.2, 1.1, 1.0],
    "Cold-formed steel strap-braced wall (CFS2)": [1.4, 1.2, 1.1, 1.0],
    "Unreinforced masonry (URM)": [1.0, 1.0, 1.0, 1.0],
    "Flexible diaphragms (S1a, S2a, S5a, C2a, C3a, PC1, RM1)": [1.0, 1.0, 1.0, 1.0],
}

WALL_CATEGORIES = (
    "Reinforced concrete / precast concrete / wood / reinforced masonry / cold-formed steel",
    "Unreinforced masonry",
)
PERFORMANCE_LEVELS = ("Collapse Prevention (CP)", "Immediate Occupancy (IO)")
MATERIALS = (
    "Concrete / reinforced masonry / cold-formed steel",
    "Unreinforced masonry",
    "Wood-framed walls",
)

MS_TABLE = {
    WALL_CATEGORIES[0]: {"Collapse Prevention (CP)": 4.5, "Immediate Occupancy (IO)": 1.5},
    WALL_CATEGORIES[1]: {"Collapse Prevention (CP)": 1.75, "Immediate Occupancy (IO)": 1.0},
}


class CalculationInputError(ValueError):
    """Raised when an input cannot produce a meaningful calculation."""


def is_shear_stress_item(item: dict[str, Any]) -> bool:
    statement = str(item.get("statement", "")).upper()
    return "SHEAR STRESS CHECK" in statement


def _number(value: Any, label: str, *, minimum: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise CalculationInputError(f"{label} must be a number.") from error
    if number < minimum:
        raise CalculationInputError(f"{label} must be at least {minimum:g}.")
    return number


def _integer(value: Any, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise CalculationInputError(f"{label} must be a whole number.") from error
    if number <= 0:
        raise CalculationInputError(f"{label} must be greater than zero.")
    return number


def calculate_average_shear_stress(inputs: dict[str, Any]) -> dict[str, Any]:
    """Calculate the guided shear-wall check and return report-ready values."""

    building_system = str(inputs.get("building_system", "")).strip()
    story_band = str(inputs.get("story_band", "")).strip()
    if building_system not in C_TABLE:
        raise CalculationInputError("Choose a Table 4-7 building system.")
    if story_band not in STORY_INDEX:
        raise CalculationInputError("Choose a story band.")

    units = str(inputs.get("units", "ksf")).strip().lower()
    if units not in {"ksi", "ksf"}:
        raise CalculationInputError("Choose ksi or ksf for the wall stress units.")
    wall_category = str(inputs.get("wall_category", "")).strip()
    if wall_category not in MS_TABLE:
        raise CalculationInputError("Choose a Table 4-8 wall category.")
    performance = str(inputs.get("performance", "")).strip()
    if performance not in MS_TABLE[wall_category]:
        raise CalculationInputError("Choose a supported performance level.")
    material = str(inputs.get("material", "")).strip()
    if material not in MATERIALS:
        raise CalculationInputError("Choose a wall area treatment.")

    c = C_TABLE[building_system][STORY_INDEX[story_band]]
    spectral_acceleration = _number(inputs.get("spectral_acceleration"), "Spectral acceleration Sa")
    seismic_weight = _number(inputs.get("seismic_weight"), "Total seismic weight W")
    base_shear = c * spectral_acceleration * seismic_weight
    period = _number(inputs.get("period"), "Fundamental period T")
    use_six_story_simplification = bool(inputs.get("use_six_story_simplification"))
    if use_six_story_simplification or period <= 0.5:
        exponent = 1.0
    elif period > 2.5:
        exponent = 2.0
    else:
        exponent = 1.0 + (period - 0.5) / 2.0

    raw_levels = inputs.get("levels") or []
    levels: list[dict[str, Any]] = []
    seen_levels: set[int] = set()
    for raw in raw_levels:
        if not any(str(raw.get(key, "")).strip() for key in ("level", "weight", "height")):
            continue
        level = _integer(raw.get("level"), "Level")
        if level in seen_levels:
            raise CalculationInputError(f"Level {level} is listed more than once.")
        seen_levels.add(level)
        levels.append({
            "level": level,
            "weight": _number(raw.get("weight"), f"Weight at level {level}"),
            "height": _number(raw.get("height"), f"Height at level {level}"),
        })
    if not levels:
        raise CalculationInputError("Enter at least one level with weight and height.")
    denominator = sum(level["weight"] * level["height"] ** exponent for level in levels)
    if denominator <= 0:
        raise CalculationInputError("The sum of wi hi^k must be greater than zero.")
    for level in levels:
        level["wi_hi_k"] = level["weight"] * level["height"] ** exponent
        level["force"] = level["wi_hi_k"] / denominator * base_shear
    levels.sort(key=lambda level: level["level"])

    story_level = _integer(inputs.get("story_level"), "Story level j")
    story_shear = sum(level["force"] for level in levels if level["level"] >= story_level)

    modifier = MS_TABLE[wall_category][performance]
    raw_walls = inputs.get("walls") or []
    walls: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_walls, start=1):
        if not any(str(raw.get(key, "")).strip() for key in ("name", "length", "thickness")):
            continue
        length = _number(raw.get("length"), f"Net length for wall {index}")
        thickness = _number(raw.get("thickness"), f"Thickness for wall {index}")
        walls.append({"name": str(raw.get("name") or f"W{index}").strip(), "length": length, "thickness": thickness})
    if not walls:
        raise CalculationInputError("Enter at least one participating wall.")

    total_length = sum(wall["length"] for wall in walls)
    if material == "Wood-framed walls":
        measure = total_length * 12 if units == "ksi" else total_length
        measure_label = f"{total_length:.3f} ft of wall length"
        result_units = "kips/in" if units == "ksi" else "kips/ft"
    else:
        area_in2 = sum(wall["length"] * 12 * wall["thickness"] for wall in walls)
        measure = area_in2 if units == "ksi" else area_in2 / 144
        measure_label = f"{area_in2:.3f} in²"
        result_units = units
    if measure <= 0:
        raise CalculationInputError("The effective wall measure must be greater than zero.")

    average_shear_stress = story_shear / (modifier * measure)
    return {
        "direction": str(inputs.get("direction", "X")).strip() or "X",
        "building_system": building_system,
        "story_band": story_band,
        "modification_factor_C": c,
        "spectral_acceleration_Sa": spectral_acceleration,
        "seismic_weight_W_kips": seismic_weight,
        "base_shear_V_kips": base_shear,
        "period_T_sec": period,
        "distribution_exponent_k": exponent,
        "story_level_j": story_level,
        "story_shear_Vj_kips": story_shear,
        "wall_category": wall_category,
        "performance": performance,
        "modifier_Ms": modifier,
        "material": material,
        "effective_wall_measure": measure,
        "effective_wall_measure_label": measure_label,
        "average_shear_stress": average_shear_stress,
        "result_units": result_units,
        "levels": levels,
        "walls": walls,
        "notes": str(inputs.get("notes", "")).strip(),
        "source_reference": SOURCE_REFERENCE,
    }


def defaults_for_assessment(assessment) -> dict[str, Any]:
    """Return sensible form defaults without classifying the building."""

    try:
        stories = int(str(assessment.stories).strip())
    except (TypeError, ValueError):
        stories = 2
    story_band = str(stories) if str(stories) in {"1", "2", "3"} else "4 or more"
    if str(assessment.building_type).upper() == "URM":
        building_system = "Unreinforced masonry (URM)"
        wall_category = WALL_CATEGORIES[1]
        material = MATERIALS[1]
    else:
        building_system = "Shear wall (S4, S5, C2, C3, PC1a, PC2, RM2, URMa)"
        wall_category = WALL_CATEGORIES[0]
        material = MATERIALS[0]
    performance = "Immediate Occupancy (IO)" if assessment.performance_level == "IO" else "Collapse Prevention (CP)"
    return {
        "direction": "X",
        "units": "ksf",
        "building_system": building_system,
        "story_band": story_band,
        "spectral_acceleration": "",
        "seismic_weight": "",
        "period": "0.5",
        "story_level": "1",
        "wall_category": wall_category,
        "performance": performance,
        "material": material,
        "use_six_story_simplification": False,
    }
