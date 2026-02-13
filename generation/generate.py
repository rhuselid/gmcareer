"""
Generate divisions, teams (with [City] [Mascot] names), and players.
Uses optional seed for reproducibility. Writes progress to setup_progress.

Procedural logic:
- Per-attribute ceilings (_cap); current = ceiling - development gap. Overall/potential at a position = weighted sum of current/ceiling.
- Physical attributes tied to body type: lean -> quicker; heavy -> more lower body strength.
- High school: ~5-10% "diamond" players get boosted ceilings (college/pro potential); assign position by highest potential.
- College/Pro: same ceiling/current logic; position assigned by roster slot.
"""
import random
import sqlite3
from itertools import product

from db.schema import get_connection
from db.operations import (
    get_divisions_by_level,
    insert_division,
    insert_team,
    insert_player,
    set_setup_progress,
    bulk_insert_schedule,
    init_season_state,
)
from simulation.schedule import generate_division_schedule
from models import Player
from models.constants import (
    ROSTER_SIZES,
    ROSTER_POSITION_COUNTS,
    HS_POSITION_FILL_ORDER,
    HIGH_SCHOOL_DIVISION_NAMES,
    COLLEGE_DIVISION_NAMES,
    PRO_DIVISION_NAMES,
    CITIES,
    MASCOTS,
    FIRST_NAMES,
    LAST_NAMES,
    HS_AGE_HEIGHT_WEIGHT,
    TRAINABLE_ATTRIBUTES,
    ARM_LENGTH_INCHES_RANGE,
)
from models.ratings import compute_overall_at_position, compute_potential_at_position


def _seed_rng(seed: int | str | None) -> int:
    """Convert optional seed to int; if None, use random and return it for logging."""
    if seed is None:
        return random.randint(0, 2**31 - 1)
    if isinstance(seed, str):
        return hash(seed) % (2**31)
    return int(seed)


def _random_attr(rng: random.Random, lo: int = 0, hi: int = 99) -> int:
    return rng.randint(lo, hi)


def _unique_team_names(n: int, rng: random.Random) -> list[str]:
    """Generate n unique [City] [Mascot] team names."""
    pairs = list(product(CITIES, MASCOTS))
    rng.shuffle(pairs)
    return [f"{city} {mascot}" for city, mascot in pairs[:n]]


def _class_year_from_age(age: int, level: str) -> int:
    """Class year 1-4 (Fr, So, Jr, Sr) from age."""
    if level == "high_school":
        return min(4, max(1, age - 13))
    if level == "college":
        return min(4, max(1, age - 17))
    return min(4, max(1, age - 21))


def _random_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


# --- Age-appropriate size (HS: no 300+ lb 14-year-olds) ---

def _height_weight_for_age_hs(age: int, rng: random.Random) -> tuple[int, int]:
    """Return (height_inches, weight_lbs) for HS age; realistic ranges."""
    band = HS_AGE_HEIGHT_WEIGHT.get(age, HS_AGE_HEIGHT_WEIGHT[18])
    h_lo, h_hi, w_lo, w_hi = band
    return rng.randint(h_lo, h_hi), rng.randint(w_lo, w_hi)


def _height_weight_for_level(level: str, age: int, rng: random.Random) -> tuple[int, int]:
    """Height/weight by level; HS uses age bands, college/pro use wider ranges."""
    if level == "high_school":
        return _height_weight_for_age_hs(age, rng)
    if level == "college":
        height = rng.randint(68, 76)
        weight = rng.randint(180, 320)
        return height, weight
    height = rng.randint(69, 77)
    weight = rng.randint(190, 330)
    return height, weight


# --- Body type -> attribute bias (lean = quicker, heavy = more strength) ---

def _body_type_bias(height: int, weight: int) -> tuple[dict[str, int], dict[str, int]]:
    """
    Return (positive_bias, negative_bias) for attributes.
    Light for height -> speed/acceleration/lateral up; heavy -> lower/upper body strength, run_block, pass_protection up.
    Uses realistic weight-per-inch: WR/CB ~2.0-2.4, RB ~2.2-2.6, OL/DL ~3.2-4.2.
    """
    # Weight per inch (lbs/in): lean < 2.7 (skill), heavy > 3.5 (linemen). 274 lb @ 5'10" (70 in) = 3.91 -> heavy.
    wpi = weight / max(height, 60)
    lean = wpi < 2.7
    heavy = wpi > 3.5
    pos_bias: dict[str, int] = {}
    neg_bias: dict[str, int] = {}
    if lean:
        pos_bias = {"speed": 8, "acceleration": 8, "lateral_quickness": 6, "vertical_jump": 6, "broad_jump": 5}
        neg_bias = {"lower_body_strength": -6, "upper_body_strength": -4, "run_block": -4, "pass_protection": -4}
    elif heavy:
        pos_bias = {"lower_body_strength": 8, "upper_body_strength": 6, "run_block": 6, "pass_protection": 6}
        neg_bias = {"speed": -6, "acceleration": -6, "lateral_quickness": -4, "vertical_jump": -4, "broad_jump": -4}
    return pos_bias, neg_bias


def _apply_bias(base: int, attr: str, pos_bias: dict, neg_bias: dict) -> int:
    delta = pos_bias.get(attr, 0) + neg_bias.get(attr, 0)
    return max(0, min(99, base + delta))


# --- Per-attribute ceilings; current = ceiling - development gap ---

def _raw_ceiling_attributes(
    level: str,
    age: int,
    height: int,
    weight: int,
    rng: random.Random,
    is_diamond: bool = False,
) -> dict[str, int]:
    """Generate ceiling values (0-99) for all trainable attributes with body-type bias.
    is_diamond (HS only): boost ceilings toward 85-95 for college/pro potential."""
    pos_bias, neg_bias = _body_type_bias(height, weight)
    if level == "high_school":
        lo, hi = (20, 75) if not is_diamond else (50, 92)
    elif level == "college":
        lo, hi = 40, 85
    else:
        lo, hi = 50, 95
    caps = {}
    for attr in TRAINABLE_ATTRIBUTES:
        base = rng.randint(lo, hi)
        caps[attr] = _apply_bias(base, attr, pos_bias, neg_bias)
    return caps


def _current_from_ceiling(
    ceiling_attrs: dict[str, int],
    level: str,
    rng: random.Random,
) -> dict[str, int]:
    """Current = ceiling - random gap (0 to ~25), floored at level minimum."""
    current = {}
    level_floor = 10 if level == "high_school" else (35 if level == "college" else 50)
    for attr, cap in ceiling_attrs.items():
        gap = rng.randint(0, min(28, cap))
        val = max(level_floor, cap - gap) if level != "high_school" else max(0, cap - gap)
        current[attr] = min(99, val)
    return current


# --- Generate raw attributes: ceilings + current (with body-type bias); no position yet ---

def _raw_attributes(
    level: str,
    age: int,
    height: int,
    weight: int,
    rng: random.Random,
    is_diamond: bool = False,
) -> dict[str, int]:
    """Generate ceiling and current for all attributes; arm_length (no cap). Returns dict with attr and attr_cap."""
    caps = _raw_ceiling_attributes(level, age, height, weight, rng, is_diamond=is_diamond)
    current = _current_from_ceiling(caps, level, rng)
    out = {}
    for attr in TRAINABLE_ATTRIBUTES:
        out[attr] = current[attr]
        out[f"{attr}_cap"] = caps[attr]
    # Arm length in inches (28-36); no cap
    lo, hi = ARM_LENGTH_INCHES_RANGE
    arm_inches = rng.randint(lo, hi)
    if height >= 72:
        arm_inches = min(hi, arm_inches + rng.randint(0, 2))
    out["arm_length"] = arm_inches
    return out


# --- High school: generate raw players, assign position by highest potential ---

DIAMOND_CHANCE_HS = 0.07  # ~7% of HS players get boosted ceilings (college/pro potential)

def _generate_raw_players_hs(team_id: int, rng: random.Random) -> list[dict]:
    """Generate 30 raw HS players (age, height, weight, attributes + caps); no position. ~7% diamond."""
    raw = []
    for _ in range(ROSTER_SIZES["high_school"]):
        age = rng.randint(14, 18)
        height, weight = _height_weight_for_age_hs(age, rng)
        is_diamond = rng.random() < DIAMOND_CHANCE_HS
        attrs = _raw_attributes("high_school", age, height, weight, rng, is_diamond=is_diamond)
        raw.append({
            "team_id": team_id,
            "age": age,
            "height": height,
            "weight": weight,
            "name": _random_name(rng),
            "class_year": _class_year_from_age(age, "high_school"),
            **attrs,
        })
    return raw


def _assign_positions_hs(
    raw_players: list[dict],
    slot_order: list[str],
    rng: random.Random,
) -> list[dict]:
    """
    Assign each player to the position where they have highest potential (weighted sum of ceilings).
    Fill slots in the given order. Overall/potential at assigned position from models.ratings.
    """
    for idx, p in enumerate(raw_players):
        p["_idx"] = idx
    assigned_player_idxs: set[int] = set()
    result: list[dict] = []

    for slot_pos in slot_order:
        best_score = -1.0
        best_player: dict | None = None
        for p in raw_players:
            if p["_idx"] in assigned_player_idxs:
                continue
            score = compute_potential_at_position(p, slot_pos)
            if score > best_score:
                best_score = score
                best_player = p
        if best_player is None:
            continue
        assigned_player_idxs.add(best_player["_idx"])
        p_copy = {k: v for k, v in best_player.items() if k != "_idx"}
        overall = compute_overall_at_position(p_copy, slot_pos)
        potential = compute_potential_at_position(p_copy, slot_pos)
        potential = max(overall, potential)  # ensure potential >= overall
        result.append({
            **p_copy,
            "position": slot_pos,
            "secondary_position": None,
            "overall": overall,
            "potential": potential,
        })
    return result


def _player_kwargs_from_dict(p: dict, position: str) -> dict:
    """Build kwargs for Player() from assigned dict (has attr + attr_cap)."""
    def _cap(attr: str, default: int = 50) -> int:
        return p.get(f"{attr}_cap", p.get(attr, default))
    return {
        "team_id": p["team_id"],
        "position": position,
        "secondary_position": p.get("secondary_position"),
        "name": p["name"],
        "potential": p["potential"],
        "class_year": p["class_year"],
        "height": p["height"],
        "weight": p["weight"],
        "age": p["age"],
        "speed": p.get("speed", 0),
        "speed_cap": _cap("speed"),
        "acceleration": p.get("acceleration", 0),
        "acceleration_cap": _cap("acceleration"),
        "lateral_quickness": p.get("lateral_quickness", 0),
        "lateral_quickness_cap": _cap("lateral_quickness"),
        "vision": p.get("vision", 0),
        "vision_cap": _cap("vision"),
        "lower_body_strength": p.get("lower_body_strength", 0),
        "lower_body_strength_cap": _cap("lower_body_strength"),
        "upper_body_strength": p.get("upper_body_strength", 0),
        "upper_body_strength_cap": _cap("upper_body_strength"),
        "arm_length": p.get("arm_length", 32),
        "vertical_jump": p.get("vertical_jump", 50),
        "vertical_jump_cap": _cap("vertical_jump"),
        "broad_jump": p.get("broad_jump", 50),
        "broad_jump_cap": _cap("broad_jump"),
        "overall": p["overall"],
        "familiarity": p.get("familiarity", 0),
        "familiarity_cap": _cap("familiarity"),
        "kick_power": p.get("kick_power", 0),
        "kick_power_cap": _cap("kick_power"),
        "arm_strength": p.get("arm_strength", 0),
        "arm_strength_cap": _cap("arm_strength"),
        "run_block": p.get("run_block", 0),
        "run_block_cap": _cap("run_block"),
        "pass_rush": p.get("pass_rush", 0),
        "pass_rush_cap": _cap("pass_rush"),
        "pass_protection": p.get("pass_protection", 0),
        "pass_protection_cap": _cap("pass_protection"),
        "scrambling": p.get("scrambling", 0),
        "scrambling_cap": _cap("scrambling"),
        "short_accuracy": p.get("short_accuracy", 50),
        "short_accuracy_cap": _cap("short_accuracy"),
        "mid_accuracy": p.get("mid_accuracy", 50),
        "mid_accuracy_cap": _cap("mid_accuracy"),
        "deep_accuracy": p.get("deep_accuracy", 50),
        "deep_accuracy_cap": _cap("deep_accuracy"),
        "throw_under_pressure": p.get("throw_under_pressure", 50),
        "throw_under_pressure_cap": _cap("throw_under_pressure"),
        "ball_security": p.get("ball_security", 50),
        "ball_security_cap": _cap("ball_security"),
        "catching": p.get("catching", 50),
        "catching_cap": _cap("catching"),
        "route_running": p.get("route_running", 50),
        "route_running_cap": _cap("route_running"),
        "tackling": p.get("tackling", 50),
        "tackling_cap": _cap("tackling"),
        "coverage": p.get("coverage", 50),
        "coverage_cap": _cap("coverage"),
        "block_shedding": p.get("block_shedding", 50),
        "block_shedding_cap": _cap("block_shedding"),
        "pursuit": p.get("pursuit", 50),
        "pursuit_cap": _cap("pursuit"),
        "kick_accuracy": p.get("kick_accuracy", 50),
        "kick_accuracy_cap": _cap("kick_accuracy"),
    }


def _generate_raw_freshmen_class(team_id: int, rng: random.Random, count: int = 8) -> list[dict]:
    """Generate N raw HS freshmen (age 14-15, class_year=1); no position. Used for offseason incoming class."""
    raw = []
    for _ in range(count):
        age = rng.randint(14, 15)
        height, weight = _height_weight_for_age_hs(age, rng)
        is_diamond = rng.random() < DIAMOND_CHANCE_HS
        attrs = _raw_attributes("high_school", age, height, weight, rng, is_diamond=is_diamond)
        raw.append({
            "team_id": team_id,
            "age": age,
            "height": height,
            "weight": weight,
            "name": _random_name(rng),
            "class_year": 1,
            **attrs,
        })
    return raw


# First N position slots for incoming freshmen class (one class ≈ 8 players)
FRESHMEN_SLOT_ORDER: list[str] = [
    "QB", "RB", "WR", "C", "DE", "OLB", "CB", "S",
]


def generate_freshmen_class_for_team(
    conn: sqlite3.Connection,
    team_id: int,
    rng: random.Random,
    count: int = 8,
) -> list[dict]:
    """
    Generate and insert one incoming freshmen class for an HS team (offseason).
    Returns list of new player dicts: [{id, team_id, name, position, overall}, ...].
    """
    slot_order = FRESHMEN_SLOT_ORDER[:count] if len(FRESHMEN_SLOT_ORDER) >= count else (
        FRESHMEN_SLOT_ORDER + ["WR", "TE", "ILB"][: count - len(FRESHMEN_SLOT_ORDER)]
    )
    raw = _generate_raw_freshmen_class(team_id, rng, count=count)
    assigned = _assign_positions_hs(raw, slot_order, rng)
    new_players: list[dict] = []
    for p in assigned:
        secondary = None
        if p["position"] in ("K", "P") and rng.random() < 0.4:
            secondary = "P" if p["position"] == "K" else "K"
        p["secondary_position"] = secondary
        kwargs = _player_kwargs_from_dict(p, p["position"])
        player = Player(**kwargs)
        new_id = insert_player(conn, player)
        new_players.append({
            "id": new_id,
            "team_id": team_id,
            "name": p.get("name", f"Player #{new_id}"),
            "position": p["position"],
            "overall": p.get("overall", 0),
        })
    return new_players


def _generate_players_for_team_hs(
    conn: sqlite3.Connection,
    team_id: int,
    rng: random.Random,
) -> None:
    """HS: generate raw players with age-appropriate size, assign position by highest potential, insert."""
    raw = _generate_raw_players_hs(team_id, rng)
    slot_order: list[str] = []
    for pos, count in HS_POSITION_FILL_ORDER:
        slot_order.extend([pos] * count)
    assigned = _assign_positions_hs(raw, slot_order, rng)
    for p in assigned:
        secondary = None
        if p["position"] in ("K", "P") and rng.random() < 0.4:
            secondary = "P" if p["position"] == "K" else "K"
        p["secondary_position"] = secondary
        kwargs = _player_kwargs_from_dict(p, p["position"])
        player = Player(**kwargs)
        insert_player(conn, player)


# --- College/Pro: per-position generation with body-type bias; overall/potential from ratings ---

def _make_player(
    team_id: int,
    position: str,
    level: str,
    rng: random.Random,
    secondary_position: str | None = None,
) -> Player:
    """Create a player for college/pro: ceiling + current from _raw_attributes, overall/potential at position from models.ratings."""
    if level == "college":
        age = rng.randint(18, 22)
    else:
        age = rng.randint(22, 30)
    height, weight = _height_weight_for_level(level, age, rng)
    attrs = _raw_attributes(level, age, height, weight, rng, is_diamond=False)
    overall = compute_overall_at_position(attrs, position)
    potential = compute_potential_at_position(attrs, position)
    potential = max(overall, potential)
    class_year = _class_year_from_age(age, level)
    name = _random_name(rng)
    p = {
        "team_id": team_id,
        "name": name,
        "class_year": class_year,
        "height": height,
        "weight": weight,
        "age": age,
        "overall": overall,
        "potential": potential,
        "secondary_position": secondary_position,
        **attrs,
    }
    kwargs = _player_kwargs_from_dict(p, position)
    return Player(**kwargs)


def generate_walk_on(
    conn: sqlite3.Connection,
    team_id: int,
    level: str,
    position: str,
    rng: random.Random,
) -> int:
    """
    Generate and insert one walk-on player at the given position for the team.
    Used to fill roster gaps after recruiting/draft. Returns new player id.
    """
    if level == "college":
        player = _make_player(team_id, position, "college", rng, secondary_position=None)
        return insert_player(conn, player)
    if level == "high_school":
        raw_list = _generate_raw_freshmen_class(team_id, rng, count=1)
        p = raw_list[0]
        p["position"] = position
        p["secondary_position"] = None
        overall = compute_overall_at_position(p, position)
        potential = compute_potential_at_position(p, position)
        potential = max(overall, potential)
        p["overall"] = overall
        p["potential"] = potential
        kwargs = _player_kwargs_from_dict(p, position)
        player = Player(**kwargs)
        return insert_player(conn, player)
    raise ValueError(f"Unknown level for walk-on: {level}")


def _generate_players_for_team(
    conn: sqlite3.Connection,
    team_id: int,
    level: str,
    rng: random.Random,
) -> None:
    """Fill roster: HS uses position-by-potential assignment; college/pro use per-position generation."""
    if level == "high_school":
        _generate_players_for_team_hs(conn, team_id, rng)
        return
    position_counts = ROSTER_POSITION_COUNTS[level]
    for position, count in position_counts:
        for _ in range(count):
            secondary = None
            if level == "college" and position in ("K", "P") and rng.random() < 0.3:
                secondary = "P" if position == "K" else "K"
            player = _make_player(team_id, position, level, rng, secondary)
            insert_player(conn, player)


def generate_all_teams_and_players(
    manager_id: int,
    seed: int | str | None = None,
) -> None:
    """
    Generate all divisions, teams, and players for the save.
    Progress is written to setup_progress so the UI can poll.
    Call from a background thread after inserting the manager.
    """
    from db.schema import get_connection

    actual_seed = _seed_rng(seed)
    rng = random.Random(actual_seed)

    conn = get_connection()
    conn.row_factory = sqlite3.Row

    try:
        set_setup_progress(conn, manager_id, "generating", 5.0, "Creating divisions...")
        for name in HIGH_SCHOOL_DIVISION_NAMES:
            insert_division(conn, name, "high_school")
        for name in COLLEGE_DIVISION_NAMES:
            insert_division(conn, name, "college")
        for name in PRO_DIVISION_NAMES:
            insert_division(conn, name, "professional")

        hs_divs = get_divisions_by_level(conn, "high_school")
        college_divs = get_divisions_by_level(conn, "college")
        pro_divs = get_divisions_by_level(conn, "professional")

        all_team_names = _unique_team_names(140, rng)
        name_idx = 0

        set_setup_progress(conn, manager_id, "generating", 15.0, "Creating high school teams...")
        for div_id, _ in hs_divs:
            for _ in range(10):
                name = all_team_names[name_idx]
                name_idx += 1
                prestige = _random_attr(rng)
                facility = _random_attr(rng)
                insert_team(conn, div_id, name, prestige, facility, nil_budget=None, budget=None)

        set_setup_progress(conn, manager_id, "generating", 25.0, "Creating high school players...")
        cur = conn.execute(
            "SELECT id FROM teams WHERE division_id IN (SELECT id FROM divisions WHERE level = 'high_school') ORDER BY id"
        )
        hs_team_ids = [row[0] for row in cur.fetchall()]
        for i, team_id in enumerate(hs_team_ids):
            _generate_players_for_team(conn, team_id, "high_school", rng)
            if (i + 1) % 20 == 0:
                pct = 25.0 + (i + 1) / len(hs_team_ids) * 25.0
                set_setup_progress(conn, manager_id, "generating", pct, "Creating high school players...")

        set_setup_progress(conn, manager_id, "generating", 55.0, "Creating college teams...")
        for div_id, _ in college_divs:
            for _ in range(10):
                name = all_team_names[name_idx]
                name_idx += 1
                prestige = _random_attr(rng)
                facility = _random_attr(rng)
                nil_budget = _random_attr(rng, 50, 99) * 1000
                insert_team(conn, div_id, name, prestige, facility, nil_budget=nil_budget, budget=None)

        set_setup_progress(conn, manager_id, "generating", 65.0, "Creating college players...")
        cur = conn.execute(
            "SELECT id FROM teams WHERE division_id IN (SELECT id FROM divisions WHERE level = 'college') ORDER BY id"
        )
        college_team_ids = [row[0] for row in cur.fetchall()]
        for i, team_id in enumerate(college_team_ids):
            _generate_players_for_team(conn, team_id, "college", rng)
            if (i + 1) % 10 == 0:
                pct = 65.0 + (i + 1) / len(college_team_ids) * 15.0
                set_setup_progress(conn, manager_id, "generating", pct, "Creating college players...")

        set_setup_progress(conn, manager_id, "generating", 85.0, "Creating NFL teams...")
        for div_id, _ in pro_divs:
            for _ in range(10):
                name = all_team_names[name_idx]
                name_idx += 1
                prestige = _random_attr(rng, 60, 99)
                facility = _random_attr(rng, 60, 99)
                budget = _random_attr(rng, 80, 99) * 1_000_000
                insert_team(conn, div_id, name, prestige, facility, nil_budget=None, budget=budget)

        set_setup_progress(conn, manager_id, "generating", 92.0, "Creating NFL players...")
        cur = conn.execute(
            "SELECT id FROM teams WHERE division_id IN (SELECT id FROM divisions WHERE level = 'professional') ORDER BY id"
        )
        pro_team_ids = [row[0] for row in cur.fetchall()]
        for i, team_id in enumerate(pro_team_ids):
            _generate_players_for_team(conn, team_id, "professional", rng)
            if (i + 1) % 5 == 0:
                pct = 92.0 + (i + 1) / len(pro_team_ids) * 8.0
                set_setup_progress(conn, manager_id, "generating", pct, "Creating NFL players...")

        # ── Generate schedules for every division ──
        set_setup_progress(conn, manager_id, "generating", 98.0, "Building schedules...")

        all_divs = conn.execute(
            "SELECT id FROM divisions ORDER BY id"
        ).fetchall()
        schedule_rows: list[tuple[int, int, int, int, int]] = []
        for div_row in all_divs:
            div_id = div_row["id"]
            team_rows = conn.execute(
                "SELECT id FROM teams WHERE division_id = ? ORDER BY id",
                (div_id,),
            ).fetchall()
            team_ids = [r["id"] for r in team_rows]
            if len(team_ids) < 2:
                continue
            matchups = generate_division_schedule(team_ids, rng)
            for week, home_id, away_id in matchups:
                schedule_rows.append((1, week, div_id, home_id, away_id))

        if schedule_rows:
            bulk_insert_schedule(conn, schedule_rows)

        # Initialise season state to week 1
        init_season_state(conn, season=1, week=1)

        set_setup_progress(conn, manager_id, "ready", 100.0, "Complete")
    finally:
        conn.close()
