"""
Quick integration test for the simulation engine.

Creates a minimal league (two teams in one division), generates players,
simulates a game, validates internal consistency, and prints the box score.

Usage:
    python test_simulation.py
"""
import sys
import sqlite3

from db.schema import get_connection, init_db, get_db_path
from db.operations import (
    insert_division,
    insert_team,
    insert_game,
    get_game_by_id,
    get_player_stats_for_game,
    get_team_record,
)
from generation.generate import _generate_players_for_team
from simulation.engine import simulate_game
import random


def main() -> None:
    # Use a temp DB so we don't clobber the real save
    import tempfile, os
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test_sim.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Bootstrap schema
    init_db(conn)

    # Create one division + two teams
    div_id = insert_division(conn, "Test Division", "high_school")
    team_a_id = insert_team(conn, div_id, "Springfield Eagles", prestige=60, facility_grade=55)
    team_b_id = insert_team(conn, div_id, "Riverside Tigers", prestige=70, facility_grade=65)

    # Generate rosters (seeded for reproducibility)
    rng = random.Random(42)
    _generate_players_for_team(conn, team_a_id, "high_school", rng)
    _generate_players_for_team(conn, team_b_id, "high_school", rng)

    # Count players per team
    count_a = conn.execute("SELECT COUNT(*) FROM players WHERE team_id=?", (team_a_id,)).fetchone()[0]
    count_b = conn.execute("SELECT COUNT(*) FROM players WHERE team_id=?", (team_b_id,)).fetchone()[0]
    print(f"Team A roster: {count_a} players | Team B roster: {count_b} players")

    # --- Simulate the game ---
    result = simulate_game(team_a_id, team_b_id, conn, seed=123)

    print("\n" + "=" * 60)
    print(f"  {result.home.team_name:>25}  {result.home_score:>3}")
    print(f"  {result.away.team_name:>25}  {result.away_score:>3}")
    print("=" * 60)

    for side_label, team_res in [("HOME", result.home), ("AWAY", result.away)]:
        print(f"\n--- {side_label}: {team_res.team_name} ---")
        print(f"  Score: {team_res.score}")
        print(f"  Total yards: {team_res.total_yards}  (Rush {team_res.rush_yards}, Pass {team_res.pass_yards})")
        print(f"  Rush attempts: {team_res.rush_attempts}")
        print(f"  Passing: {team_res.pass_completions}/{team_res.pass_attempts}")
        print(f"  Turnovers: {team_res.turnovers}  |  Sacks allowed: {team_res.sacks_allowed}")

        # Print individual stats
        off_players = [p for p in team_res.player_stats if p.pass_attempts or p.rush_attempts or p.receptions or p.fg_attempts or p.punts]
        def_players = [p for p in team_res.player_stats if p.tackles or p.sacks or p.interceptions]

        if off_players:
            print("\n  Offensive Stats:")
            for ps in sorted(off_players, key=lambda x: -(x.pass_yards + x.rush_yards + x.receiving_yards)):
                parts = []
                if ps.pass_attempts:
                    parts.append(f"Pass {ps.pass_completions}/{ps.pass_attempts} {ps.pass_yards}yd {ps.pass_touchdowns}TD {ps.interceptions_thrown}INT")
                if ps.rush_attempts:
                    parts.append(f"Rush {ps.rush_attempts}att {ps.rush_yards}yd {ps.rush_touchdowns}TD")
                if ps.receptions:
                    parts.append(f"Rec {ps.receptions}/{ps.targets}tgt {ps.receiving_yards}yd {ps.receiving_touchdowns}TD")
                if ps.fg_attempts:
                    parts.append(f"FG {ps.fg_made}/{ps.fg_attempts}  XP {ps.xp_made}/{ps.xp_attempts}")
                if ps.punts:
                    parts.append(f"Punt {ps.punts} for {ps.punt_yards}yd")
                if parts:
                    print(f"    {ps.position:>3} {ps.name:<20} | {' | '.join(parts)}")

        if def_players:
            print("\n  Defensive Stats:")
            for ps in sorted(def_players, key=lambda x: -(x.tackles + x.sacks * 2)):
                parts = [f"{ps.tackles}tkl"]
                if ps.sacks:
                    parts.append(f"{ps.sacks:.0f}sk")
                if ps.tackles_for_loss:
                    parts.append(f"{ps.tackles_for_loss}tfl")
                if ps.interceptions:
                    parts.append(f"{ps.interceptions}int")
                if ps.pass_deflections:
                    parts.append(f"{ps.pass_deflections}pd")
                if ps.forced_fumbles:
                    parts.append(f"{ps.forced_fumbles}ff")
                print(f"    {ps.position:>3} {ps.name:<20} | {', '.join(parts)}")

    # ---- Consistency checks ----
    print("\n" + "=" * 60)
    print("Consistency Checks:")
    errors = 0

    for side_label, team_res in [("HOME", result.home), ("AWAY", result.away)]:
        # Sum of receiving yards == team pass yards
        total_rec_yards = sum(p.receiving_yards for p in team_res.player_stats)
        if total_rec_yards != team_res.pass_yards:
            print(f"  FAIL [{side_label}] receiving yards sum ({total_rec_yards}) != team pass yards ({team_res.pass_yards})")
            errors += 1
        else:
            print(f"  OK   [{side_label}] receiving yards sum == team pass yards ({team_res.pass_yards})")

        # Sum of rush yards == team rush yards
        total_rush_yards = sum(p.rush_yards for p in team_res.player_stats)
        if total_rush_yards != team_res.rush_yards:
            print(f"  FAIL [{side_label}] rush yards sum ({total_rush_yards}) != team rush yards ({team_res.rush_yards})")
            errors += 1
        else:
            print(f"  OK   [{side_label}] rush yards sum == team rush yards ({team_res.rush_yards})")

        # Sum of receptions == team completions
        total_receptions = sum(p.receptions for p in team_res.player_stats)
        if total_receptions != team_res.pass_completions:
            print(f"  FAIL [{side_label}] receptions sum ({total_receptions}) != team completions ({team_res.pass_completions})")
            errors += 1
        else:
            print(f"  OK   [{side_label}] receptions sum == team completions ({team_res.pass_completions})")

        # Sum of rush attempts == team rush attempts
        total_rush_att = sum(p.rush_attempts for p in team_res.player_stats)
        if total_rush_att != team_res.rush_attempts:
            print(f"  FAIL [{side_label}] rush attempts sum ({total_rush_att}) != team rush attempts ({team_res.rush_attempts})")
            errors += 1
        else:
            print(f"  OK   [{side_label}] rush attempts sum == team rush attempts ({team_res.rush_attempts})")

    # ---- Test DB persistence ----
    print("\nDB Persistence:")
    game_id = insert_game(conn, result, season=1, week=1)
    print(f"  Inserted game id={game_id}")

    game_row = get_game_by_id(game_id, conn)
    print(f"  Retrieved game: {game_row['home_score']}-{game_row['away_score']}")

    stats_rows = get_player_stats_for_game(game_id, conn=conn)
    print(f"  Player stat rows: {len(stats_rows)}")

    record_a = get_team_record(team_a_id, conn=conn)
    record_b = get_team_record(team_b_id, conn=conn)
    print(f"  Team A record: {record_a}")
    print(f"  Team B record: {record_b}")

    conn.close()

    # Clean up
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    if errors:
        print(f"\n*** {errors} consistency check(s) FAILED ***")
        sys.exit(1)
    else:
        print("\nAll checks passed!")


if __name__ == "__main__":
    main()
