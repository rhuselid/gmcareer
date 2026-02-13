"""
End-to-end test for season simulation.

Generates a full league (all divisions), generates schedules,
simulates 3 weeks across ALL divisions, and verifies everything works.

Usage:
    python test_season.py
"""
import sys
import os
import sqlite3
import tempfile
import shutil
import random

# Patch the DB path for testing
tmp_dir = tempfile.mkdtemp()
db_path = os.path.join(tmp_dir, "test_season.db")

import db.schema as schema
schema.DB_DIR = tmp_dir
schema.DB_FILENAME = "test_season.db"

from db.schema import get_connection, init_db
from db.operations import (
    insert_manager,
    insert_division,
    insert_team,
    get_divisions_by_level,
    bulk_insert_schedule,
    init_season_state,
    get_season_state,
    get_week_schedule,
    set_schedule_game_id,
    advance_week,
    insert_game,
    get_division_standings,
    get_team_schedule_display,
    get_division_for_team,
)
from generation.generate import _generate_players_for_team
from simulation.schedule import generate_division_schedule
from simulation.engine import simulate_game
from models import Manager


def main() -> None:
    conn = get_connection()
    init_db(conn)

    # Create a manager
    mgr = Manager(name="Test Coach", scouting=5, developing_potential=5,
                  unlocking_potential=5, convincing_players=5, in_game_management=5)
    mgr_id = insert_manager(conn, mgr)

    # Create 2 divisions with 10 teams each (simulating HS)
    div1_id = insert_division(conn, "Northeast", "high_school")
    div2_id = insert_division(conn, "Southeast", "high_school")

    rng = random.Random(42)
    team_ids_d1 = []
    team_ids_d2 = []

    print("Creating 20 teams with rosters...")
    for i in range(10):
        tid = insert_team(conn, div1_id, f"NE Team {i+1}", prestige=50+i, facility_grade=50+i)
        _generate_players_for_team(conn, tid, "high_school", rng)
        team_ids_d1.append(tid)

    for i in range(10):
        tid = insert_team(conn, div2_id, f"SE Team {i+1}", prestige=50+i, facility_grade=50+i)
        _generate_players_for_team(conn, tid, "high_school", rng)
        team_ids_d2.append(tid)

    # Generate schedules
    print("Generating schedules...")
    sched_rows = []
    for div_id, tids in [(div1_id, team_ids_d1), (div2_id, team_ids_d2)]:
        matchups = generate_division_schedule(tids, rng)
        for week, home, away in matchups:
            sched_rows.append((1, week, div_id, home, away))

    bulk_insert_schedule(conn, sched_rows)
    init_season_state(conn, season=1, week=1)

    # Verify schedule
    state = get_season_state(conn)
    print(f"Season state: season={state['current_season']}, week={state['current_week']}")

    total_sched = conn.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
    print(f"Total scheduled games: {total_sched}  (expected 180 = 2 divs x 90)")
    assert total_sched == 180, f"Expected 180, got {total_sched}"

    week1 = get_week_schedule(conn, 1, 1)
    print(f"Week 1 matchups: {len(week1)}  (expected 10 = 2 divs x 5)")
    assert len(week1) == 10, f"Expected 10, got {len(week1)}"

    # Verify each team plays exactly 18 games
    for tid in team_ids_d1 + team_ids_d2:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM schedule WHERE season=1 AND (home_team_id=? OR away_team_id=?)",
            (tid, tid)
        ).fetchone()[0]
        assert cnt == 18, f"Team {tid} has {cnt} games, expected 18"
    print("All teams have exactly 18 scheduled games.")

    # Verify each team plays exactly once per week
    for wk in range(1, 19):
        for tid in team_ids_d1:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM schedule WHERE season=1 AND week=? AND (home_team_id=? OR away_team_id=?)",
                (wk, tid, tid)
            ).fetchone()[0]
            assert cnt == 1, f"Team {tid} plays {cnt} times in week {wk}"
    print("Each team plays exactly once per week in division 1.")

    # Simulate 3 weeks
    user_team = team_ids_d1[0]
    for sim_week in range(1, 4):
        state = get_season_state(conn)
        cur_week = state["current_week"]
        print(f"\nSimulating week {cur_week}...")

        week_rows = get_week_schedule(conn, 1, cur_week)
        for row in week_rows:
            if row["game_id"] is not None:
                continue
            result = simulate_game(
                row["home_team_id"], row["away_team_id"], conn,
                manager_team_id=user_team, manager_in_game=5,
            )
            game_id = insert_game(conn, result, season=1, week=cur_week)
            set_schedule_game_id(conn, row["id"], game_id)

        conn.commit()
        advance_week(conn)

        # Check results
        games_played = conn.execute(
            "SELECT COUNT(*) FROM games WHERE season=1 AND week=?", (cur_week,)
        ).fetchone()[0]
        print(f"  Games simulated this week: {games_played}")
        assert games_played == 10, f"Expected 10, got {games_played}"

    # Check standings
    print("\nDivision 1 Standings after 3 weeks:")
    standings = get_division_standings(div1_id, 1, conn)
    for i, s in enumerate(standings):
        diff = s["points_for"] - s["points_against"]
        marker = " <-- YOUR TEAM" if s["team_id"] == user_team else ""
        print(f"  {i+1:>2}. {s['team_name']:<15} {s['wins']}-{s['losses']}  PF:{s['points_for']:>3}  PA:{s['points_against']:>3}  Diff:{diff:>+4}{marker}")

    # Check user schedule display
    print(f"\nUser team ({user_team}) schedule:")
    user_sched = get_team_schedule_display(user_team, 1, conn)
    for g in user_sched[:5]:
        prefix = "vs" if g["is_home"] else " @"
        if g["game_id"]:
            print(f"  Wk {g['week']:>2}  {prefix} {g['opponent_name']:<15} {g['result']} {g['user_score']}-{g['opp_score']}")
        else:
            print(f"  Wk {g['week']:>2}  {prefix} {g['opponent_name']:<15} --")

    # Check division_for_team
    div_info = get_division_for_team(user_team, conn)
    assert div_info is not None
    assert div_info["id"] == div1_id
    print(f"\nDivision for team {user_team}: {div_info['name']} ({div_info['level']})")

    # Verify total wins = total losses across division
    total_w = sum(s["wins"] for s in standings)
    total_l = sum(s["losses"] for s in standings)
    assert total_w == total_l, f"Wins ({total_w}) != Losses ({total_l})"
    print(f"\nIntegrity: Total W={total_w} == Total L={total_l}")

    state = get_season_state(conn)
    print(f"Season state now: week={state['current_week']}")
    assert state["current_week"] == 4

    conn.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("\nAll season tests passed!")


if __name__ == "__main__":
    main()
