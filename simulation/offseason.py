"""
Offseason simulation for GM Career Mode.

Runs after week 18: freshmen class, recruiting (HS seniors -> college),
draft (college seniors -> NFL), training camps (HS development), offseason development,
then advance class years and new season.
"""
from __future__ import annotations

import random
import sqlite3
from typing import Any

from db.operations import (
    get_season_state,
    get_teams_in_division_order,
    get_team_record_for_season,
    get_players_at_level_with_class,
    transfer_player_to_team,
    delete_player,
    depth_chart_is_valid,
    get_missing_positions_for_team,
    generate_depth_chart_best_by_position,
    OFFSEASON_STEPS,
)
from simulation.development import run_development_for_team
from simulation.schedule import generate_division_schedule
from db.operations import bulk_insert_schedule, get_practice_plan, set_practice_plan
from models.constants import PRACTICE_FOCUS_DEFAULT

# Recruiting: slots per college team per offseason
RECRUITS_PER_COLLEGE = 8

# Draft: picks per NFL team (one round for simplicity; can expand)
DRAFT_ROUNDS = 1

# Offseason development: multiplier vs in-season weekly development
OFFSEASON_DEV_MULTIPLIER = 2.0

# Training camp: multiplier for HS-only development in training_camp step
TRAINING_CAMP_DEV_MULTIPLIER = 2.0


def _get_rng(season: int, step: str) -> random.Random:
    """Seeded RNG for reproducible offseason (same season/step => same outcome)."""
    return random.Random((season * 1000) + hash(step) % 1000)


def run_freshmen_class(conn: sqlite3.Connection, season: int) -> dict[str, Any]:
    """Add one incoming freshmen class to every high school team. Returns summary and new_players list."""
    from generation.generate import generate_freshmen_class_for_team

    rng = _get_rng(season, "freshmen")
    teams = get_teams_in_division_order(conn, "high_school")
    team_names = {t["id"]: t["name"] for t in teams}
    new_players: list[dict[str, Any]] = []
    for t in teams:
        added = generate_freshmen_class_for_team(conn, t["id"], rng, count=8)
        for p in added:
            p["team_name"] = team_names.get(p["team_id"], "")
            new_players.append(p)
    return {
        "teams": len(teams),
        "players_added": len(new_players),
        "new_players": new_players,
    }


# Number of top schools each recruit considers (player interest)
RECRUIT_TOP_SCHOOLS = 5


def _compute_player_interest(
    seniors: list[dict],
    college_teams: list[dict],
    rng: random.Random,
) -> dict[int, list[int]]:
    """
    For each player id, compute interest score toward each college and return
    player_id -> list of college_id in descending interest (top schools first).
    Interest = prestige * 0.5 + (nil_budget/5000) * 0.3 + random noise.
    """
    out: dict[int, list[int]] = {}
    for p in seniors:
        pid = p["id"]
        scores: list[tuple[float, int]] = []
        for ct in college_teams:
            prestige = (ct.get("prestige") or 0) / 99.0
            nil = (ct.get("nil_budget") or 0) / 5000.0  # scale to ~0–2 for big budgets
            noise = rng.gauss(0, 0.08)
            interest = prestige * 0.5 + min(1.0, nil) * 0.3 + noise
            scores.append((interest, ct["id"]))
        scores.sort(key=lambda x: -x[0])
        out[pid] = [cid for _, cid in scores]
    return out


def run_recruiting(conn: sqlite3.Connection, season: int) -> dict[str, Any]:
    """
    HS seniors -> college using a player interest system. Each player has
    interest in schools (prestige + NIL + randomness). Colleges get
    RECRUITS_PER_COLLEGE slots; when a college picks, it takes the best
    available player who has that school in their top RECRUIT_TOP_SCHOOLS.
    Unrecruited seniors retire.
    """
    seniors = get_players_at_level_with_class(conn, "high_school", 4)
    if not seniors:
        return {"recruited": 0, "retired": 0, "colleges": 0}
    college_teams = get_teams_in_division_order(conn, "college")
    college_teams.sort(key=lambda x: -(x.get("prestige") or 0))
    rng = _get_rng(season, "recruiting")
    player_top_schools = _compute_player_interest(seniors, college_teams, rng)
    used: set[int] = set()
    recruited = 0
    for ct in college_teams:
        cid = ct["id"]
        for _ in range(RECRUITS_PER_COLLEGE):
            # Best available player who has this college in their top N
            best = None
            best_pot = -1
            for p in seniors:
                if p["id"] in used:
                    continue
                top = player_top_schools.get(p["id"], [])
                if cid not in top[:RECRUIT_TOP_SCHOOLS]:
                    continue
                if p.get("potential", 0) > best_pot:
                    best_pot = p["potential"]
                    best = p
            if best is None:
                # No interested player; take best available
                for p in seniors:
                    if p["id"] in used:
                        continue
                    if p.get("potential", 0) > best_pot:
                        best_pot = p["potential"]
                        best = p
            if best is None:
                break
            used.add(best["id"])
            transfer_player_to_team(conn, best["id"], cid, new_class_year=1, commit=False)
            recruited += 1
    conn.commit()
    retired = 0
    for p in seniors:
        if p["id"] in used:
            continue
        delete_player(conn, p["id"], commit=False)
        retired += 1
    conn.commit()
    walk_ons_added = _fill_roster_for_level(conn, "high_school", season)
    return {
        "recruited": recruited,
        "retired": retired,
        "colleges": len(college_teams),
        "walk_ons_added": walk_ons_added,
    }


def _fill_roster_for_level(conn: sqlite3.Connection, level: str, season: int) -> int:
    """
    Ensure every team at the given level can field a valid depth chart.
    Add walk-on players for any missing position. Returns total walk-ons added.
    """
    from generation.generate import generate_walk_on

    rng = _get_rng(season, f"fill_roster_{level}")
    teams = get_teams_in_division_order(conn, level)
    total_added = 0
    for t in teams:
        team_id = t["id"]
        valid, _ = depth_chart_is_valid(team_id, conn)
        while not valid:
            missing = get_missing_positions_for_team(team_id, conn)
            for pos in missing:
                generate_walk_on(conn, team_id, level, pos, rng)
                total_added += 1
            generate_depth_chart_best_by_position(team_id, conn)
            valid, _ = depth_chart_is_valid(team_id, conn)
    return total_added


def run_draft(conn: sqlite3.Connection, season: int) -> dict[str, Any]:
    """
    College seniors -> NFL. Draft order: worst record first (by wins, then point diff).
    Each NFL team gets DRAFT_ROUNDS pick(s). Best available senior by potential. Rest retire.
    """
    seniors = get_players_at_level_with_class(conn, "college", 4)
    if not seniors:
        return {"drafted": 0, "retired": 0, "teams": 0}
    pro_teams = get_teams_in_division_order(conn, "professional")
    # Draft order: worst record first (fewest wins, then most losses)
    records = []
    for t in pro_teams:
        rec = get_team_record_for_season(conn, t["id"], season)
        records.append((t["id"], t["name"], rec["wins"], rec["losses"]))
    records.sort(key=lambda x: (x[2], -x[3]))  # fewer wins first; then more losses first
    draft_order = [r[0] for r in records]
    picked = set()
    drafted = 0
    total_picks = len(draft_order) * DRAFT_ROUNDS
    for pick_num in range(total_picks):
        team_id = draft_order[pick_num % len(draft_order)]
        best = None
        best_pot = -1
        for p in seniors:
            if p["id"] in picked:
                continue
            if p.get("potential", 0) > best_pot:
                best_pot = p["potential"]
                best = p
        if best is None:
            break
        picked.add(best["id"])
        transfer_player_to_team(conn, best["id"], team_id, commit=False)
        drafted += 1
    conn.commit()
    retired = 0
    for p in seniors:
        if p["id"] in picked:
            continue
        delete_player(conn, p["id"], commit=False)
        retired += 1
    conn.commit()
    walk_ons_added = _fill_roster_for_level(conn, "college", season)
    return {
        "drafted": drafted,
        "retired": retired,
        "teams": len(pro_teams),
        "walk_ons_added": walk_ons_added,
    }


# Week 0 = offseason (training camp / offseason dev) for logging
OFFSEASON_WEEK = 0


def run_training_camps(conn: sqlite3.Connection, season: int) -> dict[str, Any]:
    """
    Run training camp development for all HS teams. Uses practice plan if set for
    (team, season, 0) or balanced; run development twice for 2x effect.
    """
    from db.operations import get_all_team_ids
    from db.operations import get_division_for_team

    team_ids = get_all_team_ids(conn)
    hs_team_ids = []
    for tid in team_ids:
        div = get_division_for_team(tid, conn)
        if div and div.get("level") == "high_school":
            hs_team_ids.append(tid)
    total_gain = 0
    for team_id in hs_team_ids:
        plan = get_practice_plan(conn, team_id, season, OFFSEASON_WEEK)
        if plan is None:
            plan = {"offense_focus": PRACTICE_FOCUS_DEFAULT, "defense_focus": PRACTICE_FOCUS_DEFAULT}
            set_practice_plan(conn, team_id, season, OFFSEASON_WEEK, plan["offense_focus"], plan["defense_focus"])
        for _ in range(2):
            summary = run_development_for_team(conn, team_id, season, OFFSEASON_WEEK, plan=plan)
            total_gain += sum(s.get("total_gain", 0) for s in summary)
    return {"teams": len(hs_team_ids), "total_gain": total_gain}


def run_offseason_development(conn: sqlite3.Connection, season: int) -> dict[str, Any]:
    """
    Run development for ALL teams (HS + college) over 4 virtual "weeks" at offseason week 0
    so there is more change than in-season.
    """
    from db.operations import get_all_team_ids
    from db.operations import get_division_for_team

    team_ids = get_all_team_ids(conn)
    non_pro = [t for t in team_ids if get_division_for_team(t, conn) and get_division_for_team(t, conn).get("level") != "professional"]
    total_gain = 0
    for team_id in non_pro:
        plan = get_practice_plan(conn, team_id, season, OFFSEASON_WEEK)
        if plan is None:
            plan = {"offense_focus": PRACTICE_FOCUS_DEFAULT, "defense_focus": PRACTICE_FOCUS_DEFAULT}
            set_practice_plan(conn, team_id, season, OFFSEASON_WEEK, plan["offense_focus"], plan["defense_focus"])
        for _ in range(4):
            summary = run_development_for_team(conn, team_id, season, OFFSEASON_WEEK, plan=plan)
            total_gain += sum(s.get("total_gain", 0) for s in summary)
    return {"teams": len(non_pro), "total_gain": total_gain}


def advance_class_years(conn: sqlite3.Connection) -> None:
    """Bump class_year for all players: 1->2, 2->3, 3->4. Seniors already moved or retired."""
    conn.execute(
        "UPDATE players SET class_year = MIN(4, class_year + 1) WHERE class_year < 4"
    )
    conn.commit()


def generate_schedule_for_season(conn: sqlite3.Connection, season: int, rng: random.Random | None = None) -> None:
    """Build and insert schedule for the given season (all divisions)."""
    if rng is None:
        rng = random.Random(season)
    all_divs = conn.execute("SELECT id FROM divisions ORDER BY id").fetchall()
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
            schedule_rows.append((season, week, div_id, home_id, away_id))
    if schedule_rows:
        bulk_insert_schedule(conn, schedule_rows)


def run_offseason_complete(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    Final offseason step: advance class years, generate next season schedule, set phase to in_season.
    Call after development step. Returns summary.
    """
    state = get_season_state(conn)
    season = state["current_season"]
    next_season = season + 1
    advance_class_years(conn)
    rng = _get_rng(season, "complete")
    generate_schedule_for_season(conn, next_season, rng)
    from db.operations import advance_to_new_season
    advance_to_new_season(conn)
    return {"new_season": next_season}
