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
    get_recruiting_offers,
    get_draft_order,
    get_current_draft_pick,
    get_eligible_draft_players,
    record_draft_pick,
    get_draft_picks_made,
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


def _compute_player_interest_scores(
    seniors: list[dict],
    college_teams: list[dict],
    rng: random.Random,
) -> dict[int, list[tuple[int, float]]]:
    """player_id -> list of (college_id, score) descending by score. For UI display."""
    out: dict[int, list[tuple[int, float]]] = {}
    for p in seniors:
        pid = p["id"]
        scores: list[tuple[float, int]] = []
        for ct in college_teams:
            prestige = (ct.get("prestige") or 0) / 99.0
            nil = (ct.get("nil_budget") or 0) / 5000.0
            noise = rng.gauss(0, 0.08)
            interest = prestige * 0.5 + min(1.0, nil) * 0.3 + noise
            scores.append((interest, ct["id"]))
        scores.sort(key=lambda x: -x[0])
        out[pid] = [(cid, sc) for sc, cid in scores]
    return out


def get_recruits_with_interest(
    conn: sqlite3.Connection, season: int, college_team_id: int
) -> list[dict[str, Any]]:
    """Return HS seniors with interest_rank and interest_score toward the given college (for recruiting screen)."""
    seniors = get_players_at_level_with_class(conn, "high_school", 4)
    if not seniors:
        return []
    college_teams = get_teams_in_division_order(conn, "college")
    rng = _get_rng(season, "recruiting")
    interest_scores = _compute_player_interest_scores(seniors, college_teams, rng)
    result = []
    for p in seniors:
        pid = p["id"]
        scores_list = interest_scores.get(pid, [])
        rank = 0
        score = 0.0
        for i, (cid, sc) in enumerate(scores_list):
            if cid == college_team_id:
                rank = i + 1
                score = round(sc * 100)  # 0-100 scale for display
                break
        result.append({
            **p,
            "interest_rank": rank,
            "interest_score": score,
        })
    result.sort(key=lambda x: (-x["interest_score"], -(x.get("potential") or 0)))
    return result


def run_recruiting(
    conn: sqlite3.Connection, season: int, human_team_id: int | None = None
) -> dict[str, Any]:
    """
    HS seniors -> college. Players sign with the school they are most interested in that gave them an offer.
    If human_team_id is set, that team's offers come from recruiting_offers table; other colleges use AI (best available).
    Build all offers, then for each player with offers assign to the offering school they rank highest.
    """
    from collections import defaultdict

    seniors = get_players_at_level_with_class(conn, "high_school", 4)
    if not seniors:
        return {"recruited": 0, "retired": 0, "colleges": 0, "signed": [], "retired_list": [], "walk_ons_added": 0}
    hs_team_names = {t["id"]: t["name"] for t in get_teams_in_division_order(conn, "high_school")}
    college_teams = get_teams_in_division_order(conn, "college")
    college_teams.sort(key=lambda x: -(x.get("prestige") or 0))
    college_names = {t["id"]: t["name"] for t in college_teams}
    rng = _get_rng(season, "recruiting")
    player_top_schools = _compute_player_interest(seniors, college_teams, rng)
    seniors_by_id = {p["id"]: p for p in seniors}

    # Build offers: player_id -> list of team_ids that offered
    offers_by_player: dict[int, list[int]] = defaultdict(list)
    human_offers: set[int] = set()
    if human_team_id is not None:
        human_offers = set(get_recruiting_offers(conn, season, human_team_id))
        for pid in human_offers:
            offers_by_player[pid].append(human_team_id)

    offered_by_college: dict[int, set[int]] = defaultdict(set)
    for pid in human_offers:
        offered_by_college[human_team_id].add(pid)

    for ct in college_teams:
        cid = ct["id"]
        if cid == human_team_id:
            continue  # already added human offers
        for _ in range(RECRUITS_PER_COLLEGE):
            best = None
            best_pot = -1
            for p in seniors:
                pid = p["id"]
                if pid in offered_by_college.get(cid, set()):
                    continue
                top = player_top_schools.get(pid, [])
                if cid not in top[:RECRUIT_TOP_SCHOOLS]:
                    continue
                if p.get("potential", 0) > best_pot:
                    best_pot = p["potential"]
                    best = p
            if best is None:
                for p in seniors:
                    pid = p["id"]
                    if pid in offered_by_college.get(cid, set()):
                        continue
                    if p.get("potential", 0) > best_pot:
                        best_pot = p["potential"]
                        best = p
            if best is None:
                break
            best_id = best["id"]
            offers_by_player[best_id].append(cid)
            offered_by_college[cid].add(best_id)

    # Resolve: each player signs with the offering school they rank highest
    used: set[int] = set()
    signed: list[dict[str, Any]] = []
    for p in seniors:
        pid = p["id"]
        offerers = offers_by_player.get(pid, [])
        if not offerers:
            continue
        top_list = player_top_schools.get(pid, [])
        best_cid = None
        for cid in top_list:
            if cid in offerers:
                best_cid = cid
                break
        if best_cid is None:
            best_cid = offerers[0]
        used.add(pid)
        from_tid = p.get("team_id")
        signed.append({
            "player_id": pid,
            "player_name": p.get("name", f"Player #{pid}"),
            "from_team_id": from_tid,
            "to_team_id": best_cid,
            "from_team_name": hs_team_names.get(from_tid, ""),
            "to_team_name": college_names.get(best_cid, ""),
        })
        transfer_player_to_team(conn, pid, best_cid, new_class_year=1, commit=False)
    conn.commit()

    retired_list: list[dict[str, Any]] = []
    for p in seniors:
        if p["id"] in used:
            continue
        from_tid = p.get("team_id")
        retired_list.append({
            "player_id": p["id"],
            "player_name": p.get("name", f"Player #{p['id']}"),
            "from_team_id": from_tid,
            "from_team_name": hs_team_names.get(from_tid, ""),
        })
        delete_player(conn, p["id"], commit=False)
    conn.commit()
    walk_ons_added = _fill_roster_for_level(conn, "high_school", season)
    return {
        "recruited": len(signed),
        "retired": len(retired_list),
        "colleges": len(college_teams),
        "signed": signed,
        "retired_list": retired_list,
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


def _pick_best_available(eligible: list[dict], team_id: int) -> dict | None:
    """AI logic: choose best available by potential, then overall. Returns player dict or None."""
    if not eligible:
        return None
    return max(eligible, key=lambda p: (p.get("potential") or 0, p.get("overall") or 0))


def run_ai_draft_pick(conn: sqlite3.Connection, season: int) -> dict[str, Any] | None:
    """Run one draft pick for the team on the clock (AI: best available by potential). Returns pick info or None if draft complete."""
    current = get_current_draft_pick(conn, season)
    if current is None:
        return None
    pick_number, team_id = current
    eligible = get_eligible_draft_players(conn, season)
    best = _pick_best_available(eligible, team_id)
    if best is None:
        return None
    college_names = {t["id"]: t["name"] for t in get_teams_in_division_order(conn, "college")}
    pro_names = {t["id"]: t["name"] for t in get_teams_in_division_order(conn, "professional")}
    record_draft_pick(conn, season, pick_number, team_id, best["id"])
    return {
        "pick_number": pick_number,
        "team_id": team_id,
        "team_name": pro_names.get(team_id, ""),
        "player_id": best["id"],
        "player_name": best.get("name", f"Player #{best['id']}"),
        "position": best.get("position", ""),
        "overall": best.get("overall", 0),
        "potential": best.get("potential", 0),
        "from_team_name": college_names.get(best.get("team_id"), ""),
    }


def run_ai_draft_until_user_pick(
    conn: sqlite3.Connection, season: int, user_team_id: int
) -> list[dict[str, Any]]:
    """Run AI draft picks until it's the user's turn or draft is complete. Returns list of picks made."""
    made = []
    while True:
        current = get_current_draft_pick(conn, season)
        if current is None:
            break
        _pick_number, team_id = current
        if team_id == user_team_id:
            break
        pick_info = run_ai_draft_pick(conn, season)
        if pick_info is None:
            break
        made.append(pick_info)
    return made


def run_draft(conn: sqlite3.Connection, season: int) -> dict[str, Any]:
    """
    College seniors -> NFL. Full auto-draft (used when not in interactive draft step).
    Draft order: worst record first. Each team gets DRAFT_ROUNDS pick(s). Best available by potential. Rest retire.
    """
    # If interactive draft already ran (draft_picks exist for this season), retire undrafted and fill rosters only
    picks_made = get_draft_picks_made(conn, season)
    order = get_draft_order(conn, season)
    total_picks = len(order) * DRAFT_ROUNDS
    if len(picks_made) >= total_picks:
        # Draft already done (e.g. by draft step); just retire remaining seniors and fill rosters
        seniors = get_players_at_level_with_class(conn, "college", 4)
        college_names = {t["id"]: t["name"] for t in get_teams_in_division_order(conn, "college")}
        picked_ids = {r["player_id"] for r in picks_made}
        retired_list = []
        for p in seniors:
            if p["id"] in picked_ids:
                continue
            retired_list.append({
                "player_id": p["id"],
                "player_name": p.get("name", f"Player #{p['id']}"),
                "from_team_id": p.get("team_id"),
                "from_team_name": college_names.get(p.get("team_id"), ""),
            })
            delete_player(conn, p["id"], commit=False)
        conn.commit()
        walk_ons_added = _fill_roster_for_level(conn, "college", season)
        return {
            "drafted": len(picks_made),
            "retired": len(retired_list),
            "teams": len(order),
            "drafted_list": [],
            "retired_list": retired_list,
            "walk_ons_added": walk_ons_added,
        }

    seniors = get_players_at_level_with_class(conn, "college", 4)
    if not seniors:
        return {"drafted": 0, "retired": 0, "teams": 0, "drafted_list": [], "retired_list": [], "walk_ons_added": 0}
    college_teams = get_teams_in_division_order(conn, "college")
    college_names = {t["id"]: t["name"] for t in college_teams}
    pro_teams = get_teams_in_division_order(conn, "professional")
    pro_names = {t["id"]: t["name"] for t in pro_teams}
    draft_order = get_draft_order(conn, season)
    picked = set()
    drafted_list: list[dict[str, Any]] = []
    for pick_num in range(min(total_picks, len(draft_order))):
        team_id = draft_order[pick_num]
        to_name = pro_names.get(team_id, "")
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
        from_tid = best.get("team_id")
        drafted_list.append({
            "player_id": best["id"],
            "player_name": best.get("name", f"Player #{best['id']}"),
            "from_team_id": from_tid,
            "to_team_id": team_id,
            "from_team_name": college_names.get(from_tid, ""),
            "to_team_name": to_name,
        })
        transfer_player_to_team(conn, best["id"], team_id, commit=False)
    conn.commit()
    retired_list: list[dict[str, Any]] = []
    for p in seniors:
        if p["id"] in picked:
            continue
        from_tid = p.get("team_id")
        retired_list.append({
            "player_id": p["id"],
            "player_name": p.get("name", f"Player #{p['id']}"),
            "from_team_id": from_tid,
            "from_team_name": college_names.get(from_tid, ""),
        })
        delete_player(conn, p["id"], commit=False)
    conn.commit()
    walk_ons_added = _fill_roster_for_level(conn, "college", season)
    return {
        "drafted": len(drafted_list),
        "retired": len(retired_list),
        "teams": len(pro_teams),
        "drafted_list": drafted_list,
        "retired_list": retired_list,
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
