"""
Position-specific overall and potential rating calculations.
Single source of truth: weighted sum of attributes (current for overall, ceiling for potential).
Potential is scaled by build fit (height/weight vs position archetype) so e.g. a 274 lb player
has very low potential at WR/CB.
"""
from .constants import (
    POSITION_POTENTIAL_WEIGHTS,
    POSITION_WPI_RANGE,
    ARM_LENGTH_INCHES_RANGE,
)


def _attr_value_for_weight(attr: str, value: float, default: float = 50.0) -> float:
    """Value for position-fit formula; arm_length (inches) is scaled to 0-99."""
    if attr == "arm_length":
        lo, hi = ARM_LENGTH_INCHES_RANGE
        inches = value if isinstance(value, (int, float)) else (lo + hi) // 2
        return min(99.0, max(0.0, (float(inches) - lo) / (hi - lo) * 99.0))
    return min(99.0, max(0.0, float(value) if value is not None else default))


def compute_overall_at_position(player_attrs: dict, position: str) -> int:
    """Weighted sum of current attributes for a position. Returns 0-99."""
    weights = POSITION_POTENTIAL_WEIGHTS.get(position, {})
    total = 0.0
    for attr, w in weights.items():
        val = player_attrs.get(attr, 50)
        total += w * _attr_value_for_weight(attr, val)
    return min(99, max(0, round(total)))


def position_build_fit(player_attrs: dict, position: str) -> float:
    """Return 0.0-1.0: how well the player's build (height/weight) fits the position.
    Uses weight-per-inch vs position's acceptable range. Missing height/weight -> 1.0 (no penalty)."""
    height = player_attrs.get("height")
    weight = player_attrs.get("weight")
    if height is None or weight is None or height <= 0:
        return 1.0
    wpi = weight / max(height, 60)
    range_tuple = POSITION_WPI_RANGE.get(position)
    if not range_tuple:
        return 1.0
    wpi_min, wpi_max = range_tuple
    margin = 0.5  # pounds per inch outside range before we apply full penalty
    if wpi_min <= wpi <= wpi_max:
        return 1.0
    if wpi < wpi_min:
        over = wpi_min - wpi
        if over >= margin:
            return max(0.25, 1.0 - (over - margin) * 1.2)  # steep decay; floor 0.25
        return 0.3 + 0.7 * (1.0 - over / margin)
    else:
        over = wpi - wpi_max
        if over >= margin:
            return max(0.25, 1.0 - (over - margin) * 1.2)  # e.g. 274 lb @ WR: wpi 3.91 vs 2.5 -> ~0.25
        return 0.3 + 0.7 * (1.0 - over / margin)


def compute_potential_at_position(player_attrs: dict, position: str) -> int:
    """Weighted sum of ceiling attributes for a position, scaled by build fit. Returns 0-99.
    For trainable attributes uses {attr}_cap; for arm_length uses current (no cap).
    Build fit (height/weight vs position) multiplies the result so wrong body types get low potential."""
    weights = POSITION_POTENTIAL_WEIGHTS.get(position, {})
    total = 0.0
    for attr, w in weights.items():
        if attr == "arm_length":
            val = player_attrs.get(attr, (ARM_LENGTH_INCHES_RANGE[0] + ARM_LENGTH_INCHES_RANGE[1]) // 2)
        else:
            cap_key = f"{attr}_cap"
            val = player_attrs.get(cap_key)
            if val is None:
                val = player_attrs.get(attr, 50)
        total += w * _attr_value_for_weight(attr, val)
    raw = min(99.0, max(0.0, total))
    build_fit = position_build_fit(player_attrs, position)
    return min(99, max(0, round(raw * build_fit)))
