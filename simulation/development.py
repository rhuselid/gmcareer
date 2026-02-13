"""
Player development engine for GM Career Mode.
Applies weekly (or period) practice: move current attributes toward cap based on
unit-level focus (Offense / Defense / Balanced), manager developing_potential, and team facility_grade.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from models.constants import (
    POSITIONS_OFFENSE,
    POSITIONS_DEFENSE,
    POSITIONS_SPECIAL_TEAMS,
    OFFENSE_PRACTICE_ATTRIBUTES,
    DEFENSE_PRACTICE_ATTRIBUTES,
    PRACTICE_FOCUS_DEFAULT,
)
from db.operations import (
    get_team_roster_full,
    get_team_by_id,
    get_developing_potential_for_team,
    get_practice_plan,
    set_practice_plan,
    update_player_attributes,
    insert_development_log,
    recompute_player_ratings,
)

# Base development rate per week: delta scales with (cap - current) / 99 so growth is smooth.
# At 40 headroom, rate 0.7: need BASE_RATE * 40/99 * 0.7 >= 0.5 to round to 1. BASE_RATE ~2.2+.
# Set so typical players gain 1–2 points per attribute per week when below cap.
BASE_RATE = 3.0

# Manager: 0-99 -> 0.7 to 1.3
def _manager_factor(developing_potential: int) -> float:
    return 0.7 + 0.006 * max(0, min(99, developing_potential))


# Facility: 0-99 -> 0.8 to 1.2
def _facility_factor(facility_grade: int) -> float:
    return 0.8 + 0.004 * max(0, min(99, facility_grade))


def _attributes_for_focus_and_position(
    focus: str,
    position: str,
    is_offense: bool,
) -> list[tuple[str, float]]:
    """
    Return list of (attribute, rate_multiplier) for this focus and position.
    Uses OFFENSE_PRACTICE_ATTRIBUTES or DEFENSE_PRACTICE_ATTRIBUTES; only attributes
    where position is in the focus's position tuple are returned.
    Focus is normalized to lowercase so DB values like "Balanced" match "balanced".
    """
    focus_key = (focus or "").strip().lower() or PRACTICE_FOCUS_DEFAULT
    if is_offense:
        mapping = OFFENSE_PRACTICE_ATTRIBUTES.get(focus_key)
    else:
        mapping = DEFENSE_PRACTICE_ATTRIBUTES.get(focus_key)
    if not mapping:
        mapping = (
            OFFENSE_PRACTICE_ATTRIBUTES.get(PRACTICE_FOCUS_DEFAULT)
            if is_offense
            else DEFENSE_PRACTICE_ATTRIBUTES.get(PRACTICE_FOCUS_DEFAULT)
        )
    if not mapping:
        return []
    out: list[tuple[str, float]] = []
    for attr, positions_tuple, rate in mapping:
        if position in positions_tuple:
            out.append((attr, rate))
    return out


def run_development_for_team(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
    week: int,
    plan: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """
    Run one week of development for a team. If plan is None, read from practice_plan
    or use both offense_focus and defense_focus as PRACTICE_FOCUS_DEFAULT (balanced).
    plan: {offense_focus, defense_focus}. Each unit uses its focus for its players.
    Returns list of summary dicts: e.g. [{"player_id": 1, "attributes_changed": 3, "total_gain": 2}, ...].
    """
    if plan is None:
        plan = get_practice_plan(conn, team_id, season, week)
        if plan is None:
            plan = {"offense_focus": PRACTICE_FOCUS_DEFAULT, "defense_focus": PRACTICE_FOCUS_DEFAULT}
            set_practice_plan(conn, team_id, season, week, plan["offense_focus"], plan["defense_focus"])

    team = get_team_by_id(team_id, conn)
    if team is None:
        return []
    facility_grade = team.get("facility_grade", 50)
    developing_potential = get_developing_potential_for_team(conn, team_id)

    manager_mult = _manager_factor(developing_potential)
    facility_mult = _facility_factor(facility_grade)

    roster = get_team_roster_full(team_id, conn)
    summary_list: list[dict[str, Any]] = []

    for player in roster:
        player_id = player["id"]
        position = player.get("position", "")
        # Per-unit focus: offense players use offense_focus, defense use defense_focus; special teams get nothing
        if position in POSITIONS_OFFENSE:
            unit_focus = (plan.get("offense_focus") or PRACTICE_FOCUS_DEFAULT).strip().lower() or PRACTICE_FOCUS_DEFAULT
            is_offense = True
        elif position in POSITIONS_DEFENSE:
            unit_focus = (plan.get("defense_focus") or PRACTICE_FOCUS_DEFAULT).strip().lower() or PRACTICE_FOCUS_DEFAULT
            is_offense = False
        else:
            continue  # special teams: no development from unit practice
        attrs_with_rate = _attributes_for_focus_and_position(unit_focus, position, is_offense)
        if not attrs_with_rate:
            continue

        updates: dict[str, int] = {}
        log_entries: list[tuple[str, int]] = []

        for attr, rate_mult in attrs_with_rate:
            cap_key = f"{attr}_cap"
            current = player.get(attr, 50)
            cap = player.get(cap_key, 50)
            if current >= cap:
                continue
            headroom = cap - current
            # Diminishing: delta proportional to headroom
            delta_f = (
                BASE_RATE
                * (headroom / 99.0)
                * manager_mult
                * facility_mult
                * rate_mult
            )
            delta_int = round(delta_f)
            # Ensure at least +1 when there is headroom and formula would round to 0 (fixes balanced/no gains)
            if headroom > 0 and delta_int <= 0 and delta_f > 0:
                delta_int = 1
            if delta_int <= 0:
                continue
            new_val = min(cap, current + delta_int)
            actual_change = new_val - current
            if actual_change <= 0:
                continue
            updates[attr] = new_val
            log_entries.append((attr, actual_change))

        if updates:
            update_player_attributes(conn, player_id, updates, commit=False)
            for attr, change in log_entries:
                insert_development_log(conn, player_id, season, week, attr, change, commit=False)
            recompute_player_ratings(conn, player_id, position, commit=False)
            total_gain = sum(c for _, c in log_entries)
            summary_list.append({
                "player_id": player_id,
                "attributes_changed": len(log_entries),
                "total_gain": total_gain,
            })

    conn.commit()
    return summary_list


def run_development_all_teams(
    conn: sqlite3.Connection,
    season: int,
    week: int,
) -> dict[int, list[dict[str, Any]]]:
    """
    Run development for every team for the given season/week.
    Returns dict team_id -> list of player development summaries for that team.
    """
    from db.operations import get_all_team_ids

    team_ids = get_all_team_ids(conn)
    results: dict[int, list[dict[str, Any]]] = {}
    for team_id in team_ids:
        results[team_id] = run_development_for_team(conn, team_id, season, week, plan=None)
    return results
