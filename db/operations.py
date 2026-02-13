"""
Database operations for GM Career Mode.
"""
import sqlite3
from typing import Any

from .schema import get_connection
from models import Manager, Division, Team, Player
from models.game_result import PlayerGameStats as PGS, TeamGameResult, GameResult
from models.ratings import compute_overall_at_position, compute_potential_at_position

# Full player SELECT column list (base + all _cap columns for rating computation)
_PLAYER_SELECT_COLS = (
    "id, team_id, position, secondary_position, name, potential, class_year, "
    "height, weight, age, speed, acceleration, lateral_quickness, vision, "
    "lower_body_strength, upper_body_strength, arm_length, vertical_jump, broad_jump, "
    "overall, familiarity, kick_power, arm_strength, run_block, pass_rush, pass_protection, scrambling, "
    "short_accuracy, mid_accuracy, deep_accuracy, throw_under_pressure, "
    "ball_security, catching, route_running, tackling, coverage, block_shedding, pursuit, kick_accuracy, "
    "speed_cap, acceleration_cap, lateral_quickness_cap, vision_cap, "
    "lower_body_strength_cap, upper_body_strength_cap, vertical_jump_cap, broad_jump_cap, "
    "familiarity_cap, kick_power_cap, arm_strength_cap, run_block_cap, pass_rush_cap, "
    "pass_protection_cap, scrambling_cap, short_accuracy_cap, mid_accuracy_cap, "
    "deep_accuracy_cap, throw_under_pressure_cap, ball_security_cap, catching_cap, route_running_cap, "
    "tackling_cap, coverage_cap, block_shedding_cap, pursuit_cap, kick_accuracy_cap"
)

# Same columns with "p." prefix for queries that join players with teams/divisions
_PLAYER_SELECT_COLS_PREFIXED = ", ".join(
    "p." + c.strip() for c in _PLAYER_SELECT_COLS.split(",")
)


def insert_manager(conn: sqlite3.Connection, manager: Manager) -> int:
    """Insert manager and return id."""
    cur = conn.execute(
        """
        INSERT INTO managers (name, scouting, developing_potential, unlocking_potential, convincing_players, in_game_management, prestige, unspent_skill_points)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            manager.name,
            manager.scouting,
            manager.developing_potential,
            manager.unlocking_potential,
            manager.convincing_players,
            manager.in_game_management,
            getattr(manager, "prestige", 50),
            getattr(manager, "unspent_skill_points", 0),
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_current_manager(conn: sqlite3.Connection | None = None) -> Manager | None:
    """Return the current (most recent) manager, or None if no save."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        row = conn.execute(
            """SELECT id, name, scouting, developing_potential, unlocking_potential, convincing_players, in_game_management,
                      COALESCE(prestige, 50) AS prestige, COALESCE(unspent_skill_points, 0) AS unspent_skill_points
               FROM managers ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        return Manager(
            id=row["id"],
            name=row["name"],
            scouting=row["scouting"],
            developing_potential=row["developing_potential"],
            unlocking_potential=row["unlocking_potential"],
            convincing_players=row["convincing_players"],
            in_game_management=row["in_game_management"],
            prestige=row["prestige"],
            unspent_skill_points=row["unspent_skill_points"],
        )
    finally:
        if close:
            conn.close()


def insert_division(conn: sqlite3.Connection, name: str, level: str) -> int:
    """Insert division and return id."""
    cur = conn.execute(
        "INSERT INTO divisions (name, level) VALUES (?, ?)",
        (name, level),
    )
    conn.commit()
    return cur.lastrowid


def insert_team(
    conn: sqlite3.Connection,
    division_id: int,
    name: str,
    prestige: int,
    facility_grade: int,
    nil_budget: int | None = None,
    budget: int | None = None,
) -> int:
    """Insert team and return id."""
    cur = conn.execute(
        """
        INSERT INTO teams (division_id, name, prestige, facility_grade, nil_budget, budget)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (division_id, name, prestige, facility_grade, nil_budget, budget),
    )
    conn.commit()
    return cur.lastrowid


_PLAYER_INSERT_COLUMNS = 65  # 38 base + 27 _cap columns (including familiarity_cap)

def insert_player(conn: sqlite3.Connection, player: Player) -> int:
    """Insert player and return id."""
    def _cap(attr: str, default: int = 50) -> int:
        return getattr(player, f"{attr}_cap", getattr(player, attr, default))

    values = [
        player.team_id,
        player.position,
        player.secondary_position,
        player.name or None,
        player.potential if hasattr(player, "potential") else 0,
        player.class_year if hasattr(player, "class_year") else 1,
        player.height,
        player.weight,
        player.age,
        player.speed,
        player.acceleration,
        player.lateral_quickness,
        player.vision,
        player.lower_body_strength,
        player.upper_body_strength,
        getattr(player, "arm_length", 32),
        getattr(player, "vertical_jump", 50),
        getattr(player, "broad_jump", 50),
        player.overall,
        player.familiarity,
        player.kick_power,
        player.arm_strength,
        player.run_block,
        player.pass_rush,
        player.pass_protection,
        player.scrambling,
        getattr(player, "short_accuracy", 50),
        getattr(player, "mid_accuracy", 50),
        getattr(player, "deep_accuracy", 50),
        getattr(player, "throw_under_pressure", 50),
        getattr(player, "ball_security", 50),
        getattr(player, "catching", 50),
        getattr(player, "route_running", 50),
        getattr(player, "tackling", 50),
        getattr(player, "coverage", 50),
        getattr(player, "block_shedding", 50),
        getattr(player, "pursuit", 50),
        getattr(player, "kick_accuracy", 50),
        _cap("speed"),
        _cap("acceleration"),
        _cap("lateral_quickness"),
        _cap("vision"),
        _cap("lower_body_strength"),
        _cap("upper_body_strength"),
        _cap("vertical_jump"),
        _cap("broad_jump"),
        _cap("familiarity"),
        _cap("kick_power"),
        _cap("arm_strength"),
        _cap("run_block"),
        _cap("pass_rush"),
        _cap("pass_protection"),
        _cap("scrambling"),
        _cap("short_accuracy"),
        _cap("mid_accuracy"),
        _cap("deep_accuracy"),
        _cap("throw_under_pressure"),
        _cap("ball_security"),
        _cap("catching"),
        _cap("route_running"),
        _cap("tackling"),
        _cap("coverage"),
        _cap("block_shedding"),
        _cap("pursuit"),
        _cap("kick_accuracy"),
    ]
    assert len(values) == _PLAYER_INSERT_COLUMNS, (
        f"insert_player: expected {_PLAYER_INSERT_COLUMNS} values, got {len(values)}"
    )
    placeholders = ", ".join(["?"] * _PLAYER_INSERT_COLUMNS)
    try:
        cur = conn.execute(
            f"""
            INSERT INTO players (
                team_id, position, secondary_position, name, potential, class_year,
                height, weight, age, speed, acceleration, lateral_quickness, vision,
                lower_body_strength, upper_body_strength,
                arm_length, vertical_jump, broad_jump,
                overall, familiarity, kick_power, arm_strength, run_block, pass_rush, pass_protection, scrambling,
                short_accuracy, mid_accuracy, deep_accuracy, throw_under_pressure,
                ball_security, catching, route_running,
                tackling, coverage, block_shedding, pursuit, kick_accuracy,
                speed_cap, acceleration_cap, lateral_quickness_cap, vision_cap,
                lower_body_strength_cap, upper_body_strength_cap, vertical_jump_cap, broad_jump_cap,
                familiarity_cap, kick_power_cap, arm_strength_cap, run_block_cap, pass_rush_cap,
                pass_protection_cap, scrambling_cap, short_accuracy_cap, mid_accuracy_cap,
                deep_accuracy_cap, throw_under_pressure_cap, ball_security_cap, catching_cap, route_running_cap,
                tackling_cap, coverage_cap, block_shedding_cap, pursuit_cap, kick_accuracy_cap
            ) VALUES ({placeholders})
            """,
            values,
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        # #region agent log
        import json
        import time
        _log_path = r"c:\Users\rmhus\repos\GMCareer\.cursor\debug.log"
        try:
            _cols = [row[1] for row in conn.execute("PRAGMA table_info(players)").fetchall()]
        except Exception:
            _cols = []
        _payload = {
            "id": f"log_{int(time.time() * 1000)}_insert_player",
            "timestamp": int(time.time() * 1000),
            "location": "db/operations.py:insert_player",
            "message": "insert_player failed",
            "data": {"error_type": type(e).__name__, "error": str(e), "players_columns": _cols},
            "runId": "pre-fix",
            "hypothesisId": "H1",
        }
        try:
            with open(_log_path, "a", encoding="utf-8") as _f:
                _f.write(json.dumps(_payload) + "\n")
        except Exception:
            pass
        # #endregion
        raise


def get_divisions_by_level(conn: sqlite3.Connection, level: str) -> list[tuple[int, str]]:
    """Return list of (division_id, name) for the given level."""
    rows = conn.execute(
        "SELECT id, name FROM divisions WHERE level = ? ORDER BY id",
        (level,),
    ).fetchall()
    return [(r["id"], r["name"]) for r in rows]


def set_setup_progress(
    conn: sqlite3.Connection,
    manager_id: int,
    status: str,
    progress_pct: float,
    current_step: str | None = None,
) -> None:
    """Upsert setup progress for the given manager."""
    conn.execute(
        """
        INSERT INTO setup_progress (manager_id, status, progress_pct, current_step)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(manager_id) DO UPDATE SET
            status = excluded.status,
            progress_pct = excluded.progress_pct,
            current_step = excluded.current_step,
            updated_at = datetime('now')
        """,
        (manager_id, status, progress_pct, current_step),
    )
    conn.commit()


def get_all_divisions_with_teams_and_players(
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """
    Return divisions ordered by level (high_school, college, professional), each with
    teams and each team with players (sorted by overall DESC).
    """
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        return _divisions_with_teams_and_players(conn, level_filter=None)
    finally:
        if close:
            conn.close()


def get_high_school_divisions_with_teams_and_players(
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Return only high school divisions with teams and players (players sorted by overall DESC)."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        return _divisions_with_teams_and_players(conn, level_filter="high_school")
    finally:
        if close:
            conn.close()


def _divisions_with_teams_and_players(
    conn: sqlite3.Connection,
    level_filter: str | None = None,
) -> list[dict[str, Any]]:
    level_order = ("high_school", "college", "professional")
    if level_filter:
        level_order = (level_filter,)
    divisions = []
    for level in level_order:
        div_rows = conn.execute(
            "SELECT id, name, level FROM divisions WHERE level = ? ORDER BY id",
            (level,),
        ).fetchall()
        for div_row in div_rows:
            div_id, div_name, div_level = div_row["id"], div_row["name"], div_row["level"]
            team_rows = conn.execute(
                "SELECT id, name, prestige, facility_grade, nil_budget, budget FROM teams WHERE division_id = ? ORDER BY name",
                (div_id,),
            ).fetchall()
            teams = []
            for t in team_rows:
                team_id = t["id"]
                player_rows = conn.execute(
                    """SELECT id, position, secondary_position, overall, age, speed
                       FROM players WHERE team_id = ? ORDER BY overall DESC, position, id""",
                    (team_id,),
                ).fetchall()
                players = [
                    {
                        "id": p["id"],
                        "position": p["position"],
                        "secondary_position": p["secondary_position"],
                        "overall": p["overall"],
                        "age": p["age"],
                        "speed": p["speed"],
                    }
                    for p in player_rows
                ]
                teams.append({
                    "id": team_id,
                    "name": t["name"],
                    "prestige": t["prestige"],
                    "facility_grade": t["facility_grade"],
                    "nil_budget": t["nil_budget"],
                    "budget": t["budget"],
                    "players": players,
                })
            divisions.append({
                "id": div_id,
                "name": div_name,
                "level": div_level,
                "teams": teams,
            })
    return divisions


def get_manager_current_team_id(manager_id: int, conn: sqlite3.Connection | None = None) -> int | None:
    """Return the current team id for the manager, or None."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        row = conn.execute(
            "SELECT current_team_id FROM managers WHERE id = ?",
            (manager_id,),
        ).fetchone()
        if row is None or row["current_team_id"] is None:
            return None
        return row["current_team_id"]
    finally:
        if close:
            conn.close()


def set_manager_team(conn: sqlite3.Connection, manager_id: int, team_id: int) -> None:
    """Set the manager's current team."""
    conn.execute(
        "UPDATE managers SET current_team_id = ? WHERE id = ?",
        (team_id, manager_id),
    )
    conn.commit()


def get_team_by_id(team_id: int, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    """Return team row as dict (id, name, division_id, prestige, facility_grade, nil_budget, budget) or None."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        row = conn.execute(
            "SELECT id, name, division_id, prestige, facility_grade, nil_budget, budget FROM teams WHERE id = ?",
            (team_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        if close:
            conn.close()


def get_team_roster_with_depth(
    team_id: int,
    conn: sqlite3.Connection | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Return roster grouped by unit: offense, defense, special_teams.
    Each unit is a list of players (id, position, secondary_position, overall, age, speed, depth_rank).
    Players are ordered by depth chart if set, else by overall DESC.
    """
    from models.constants import POSITIONS_OFFENSE, POSITIONS_DEFENSE, POSITIONS_SPECIAL_TEAMS

    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        # Depth order per position: (team_id, position) -> [(rank, player_id), ...]
        depth_rows = conn.execute(
            "SELECT position, rank, player_id FROM depth_chart WHERE team_id = ? ORDER BY position, rank",
            (team_id,),
        ).fetchall()
        depth_by_pos: dict[str, list[int]] = {}
        for r in depth_rows:
            depth_by_pos.setdefault(r["position"], []).append(r["player_id"])

        all_players = conn.execute(
            f"SELECT {_PLAYER_SELECT_COLS} FROM players WHERE team_id = ?",
            (team_id,),
        ).fetchall()
        players_by_id = {}
        for p in all_players:
            d = dict(p)
            if d.get("name") is None:
                d["name"] = f"Player #{d['id']}"
            if d.get("potential") is None:
                d["potential"] = d.get("overall", 0)
            if d.get("class_year") is None:
                d["class_year"] = 1
            players_by_id[p["id"]] = d

        def ordered_for_positions(positions: list[str]) -> list[dict[str, Any]]:
            out = []
            for pos in positions:
                pids = depth_by_pos.get(pos)
                if pids:
                    for rank, pid in enumerate(pids):
                        if pid in players_by_id:
                            row = dict(players_by_id[pid])
                            row["depth_rank"] = rank
                            out.append(row)
                else:
                    pos_players = [dict(players_by_id[p["id"]]) for p in all_players if p["position"] == pos]
                    pos_players.sort(key=lambda x: (-x["overall"], x["id"]))
                    for rank, row in enumerate(pos_players):
                        row["depth_rank"] = rank
                        out.append(row)
            return out

        return {
            "offense": ordered_for_positions(POSITIONS_OFFENSE),
            "defense": ordered_for_positions(POSITIONS_DEFENSE),
            "special_teams": ordered_for_positions(POSITIONS_SPECIAL_TEAMS),
        }
    finally:
        if close:
            conn.close()


def get_depth_order(team_id: int, position: str, conn: sqlite3.Connection | None = None) -> list[int]:
    """Return ordered list of player_ids for position (depth chart)."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        rows = conn.execute(
            "SELECT player_id FROM depth_chart WHERE team_id = ? AND position = ? ORDER BY rank",
            (team_id, position),
        ).fetchall()
        return [r["player_id"] for r in rows]
    finally:
        if close:
            conn.close()


def set_depth_order(
    conn: sqlite3.Connection,
    team_id: int,
    position: str,
    player_ids: list[int],
    *,
    commit: bool = True,
) -> None:
    """Set depth chart order for a position (replaces existing).
    Removes each player from any other position first so UNIQUE (team_id, player_id) is not violated.
    If commit is False, caller must commit (e.g. to batch multiple positions in one transaction).
    """
    for pid in player_ids:
        conn.execute("DELETE FROM depth_chart WHERE team_id = ? AND player_id = ?", (team_id, pid))
    conn.execute("DELETE FROM depth_chart WHERE team_id = ? AND position = ?", (team_id, position))
    for rank, pid in enumerate(player_ids):
        conn.execute(
            "INSERT INTO depth_chart (team_id, position, rank, player_id) VALUES (?, ?, ?, ?)",
            (team_id, position, rank, pid),
        )
    if commit:
        conn.commit()


def update_player_position(conn: sqlite3.Connection, player_id: int, new_position: str) -> None:
    """Update a player's position (e.g. after drag to another card)."""
    conn.execute("UPDATE players SET position = ? WHERE id = ?", (new_position, player_id))
    conn.commit()


def recompute_player_ratings(
    conn: sqlite3.Connection,
    player_id: int,
    position: str,
    *,
    commit: bool = True,
) -> None:
    """Recalculate overall and potential at the given position from attributes and store them."""
    player = get_player_by_id(player_id, conn)
    if player is None:
        return
    overall = compute_overall_at_position(player, position)
    potential = compute_potential_at_position(player, position)
    overall = max(0, min(99, overall))
    potential = max(overall, min(99, potential))  # ensure potential >= overall
    conn.execute(
        "UPDATE players SET overall = ?, potential = ? WHERE id = ?",
        (overall, potential, player_id),
    )
    if commit:
        conn.commit()


def update_player_overall(conn: sqlite3.Connection, player_id: int, overall: int) -> None:
    """Update a player's overall rating; also recompute and store potential at current position."""
    player = get_player_by_id(player_id, conn)
    if player is None:
        return
    overall = max(0, min(99, overall))
    potential = compute_potential_at_position(player, player["position"])
    potential = max(overall, min(99, potential))
    conn.execute(
        "UPDATE players SET overall = ?, potential = ? WHERE id = ?",
        (overall, potential, player_id),
    )
    conn.commit()


def update_player_attributes(
    conn: sqlite3.Connection,
    player_id: int,
    updates: dict[str, int],
    *,
    commit: bool = True,
) -> None:
    """Update multiple player attribute columns. If commit is False, caller must commit."""
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [player_id]
    conn.execute(f"UPDATE players SET {set_clause} WHERE id = ?", values)
    if commit:
        conn.commit()


def remove_player_from_depth_position(
    conn: sqlite3.Connection, team_id: int, position: str, player_id: int
) -> None:
    """Remove one player from a position's depth chart and re-rank the rest."""
    rows = conn.execute(
        "SELECT rank, player_id FROM depth_chart WHERE team_id = ? AND position = ? ORDER BY rank",
        (team_id, position),
    ).fetchall()
    remaining = [r["player_id"] for r in rows if r["player_id"] != player_id]
    conn.execute("DELETE FROM depth_chart WHERE team_id = ? AND position = ?", (team_id, position))
    for rank, pid in enumerate(remaining):
        conn.execute(
            "INSERT INTO depth_chart (team_id, position, rank, player_id) VALUES (?, ?, ?, ?)",
            (team_id, position, rank, pid),
        )
    conn.commit()


def add_player_to_depth_position(
    conn: sqlite3.Connection, team_id: int, position: str, player_id: int
) -> None:
    """Append a player to the end of a position's depth chart."""
    rows = conn.execute(
        "SELECT rank FROM depth_chart WHERE team_id = ? AND position = ? ORDER BY rank",
        (team_id, position),
    ).fetchall()
    next_rank = len(rows)
    conn.execute(
        "INSERT INTO depth_chart (team_id, position, rank, player_id) VALUES (?, ?, ?, ?)",
        (team_id, position, next_rank, player_id),
    )
    conn.commit()


def sync_depth_chart_for_position_change(
    conn: sqlite3.Connection,
    team_id: int,
    player_id: int,
    old_position: str,
    new_position: str,
) -> None:
    """After changing a player's position: remove from old depth slot, add to new slot at end."""
    if old_position != new_position:
        remove_player_from_depth_position(conn, team_id, old_position, player_id)
        add_player_to_depth_position(conn, team_id, new_position, player_id)


def get_missing_positions_for_team(
    team_id: int, conn: sqlite3.Connection | None = None
) -> list[str]:
    """Return list of formation positions that have no player on the roster."""
    from models.constants import POSITIONS_OFFENSE, POSITIONS_DEFENSE, POSITIONS_SPECIAL_TEAMS

    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        roster = get_team_roster_with_depth(team_id, conn)
        all_positions = POSITIONS_OFFENSE + POSITIONS_DEFENSE + POSITIONS_SPECIAL_TEAMS
        by_pos: dict[str, list] = {}
        for unit_players in roster.values():
            for p in unit_players:
                by_pos.setdefault(p["position"], []).append(p)
        return [pos for pos in all_positions if not by_pos.get(pos)]
    finally:
        if close:
            conn.close()


def depth_chart_is_valid(
    team_id: int, conn: sqlite3.Connection | None = None
) -> tuple[bool, str]:
    """
    Return (True, "") if every formation position has at least one player; else (False, message).
    Used to allow or block Sim Next Game.
    """
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        missing = get_missing_positions_for_team(team_id, conn)
        if missing:
            return False, "Missing a player at: " + ", ".join(missing) + ". Edit depth chart or add players to those positions."
        return True, ""
    finally:
        if close:
            conn.close()


def generate_depth_chart_best_by_position(
    team_id: int, conn: sqlite3.Connection | None = None
) -> None:
    """
    Set depth chart so the highest-rated (overall) player at each position is first.
    Does not change player positions; only orders existing positions by overall DESC.
    """
    from models.constants import POSITIONS_OFFENSE, POSITIONS_DEFENSE, POSITIONS_SPECIAL_TEAMS

    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        all_positions = POSITIONS_OFFENSE + POSITIONS_DEFENSE + POSITIONS_SPECIAL_TEAMS
        rows = conn.execute(
            "SELECT id, position, overall FROM players WHERE team_id = ?",
            (team_id,),
        ).fetchall()
        by_pos: dict[str, list[dict]] = {}
        for r in rows:
            by_pos.setdefault(r["position"], []).append(dict(r))
        for pos in all_positions:
            players = by_pos.get(pos, [])
            players.sort(key=lambda x: (-x["overall"], x["id"]))
            pids = [p["id"] for p in players]
            if pids:
                set_depth_order(conn, team_id, pos, pids)
    finally:
        if close:
            conn.close()


def get_team_roster_full(
    team_id: int,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Return all players on the team with all stats (for table view)."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        rows = conn.execute(
            f"SELECT {_PLAYER_SELECT_COLS} FROM players WHERE team_id = ? ORDER BY position, id",
            (team_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("name") is None:
                d["name"] = f"Player #{d['id']}"
            if d.get("potential") is None:
                d["potential"] = d.get("overall", 0)
            if d.get("class_year") is None:
                d["class_year"] = 1
            out.append(d)
        return out
    finally:
        if close:
            conn.close()


def get_setup_progress(manager_id: int, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    """Return current setup progress for manager, or None."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        row = conn.execute(
            "SELECT status, progress_pct, current_step FROM setup_progress WHERE manager_id = ?",
            (manager_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "status": row["status"],
            "progress_pct": row["progress_pct"],
            "current_step": row["current_step"],
        }
    finally:
        if close:
            conn.close()


# ---------------------------------------------------------------------------
# Game result persistence
# ---------------------------------------------------------------------------

def insert_game(
    conn: sqlite3.Connection,
    result: GameResult,
    season: int = 1,
    week: int = 1,
) -> int:
    """Persist a GameResult (game row + all player_game_stats rows). Returns game id."""
    h = result.home
    a = result.away
    cur = conn.execute(
        """
        INSERT INTO games (
            season, week, home_team_id, away_team_id,
            home_score, away_score,
            home_total_yards, home_rush_yards, home_pass_yards, home_turnovers,
            away_total_yards, away_rush_yards, away_pass_yards, away_turnovers
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            season, week,
            h.team_id, a.team_id,
            h.score, a.score,
            h.total_yards, h.rush_yards, h.pass_yards, h.turnovers,
            a.total_yards, a.rush_yards, a.pass_yards, a.turnovers,
        ),
    )
    game_id: int = cur.lastrowid  # type: ignore[assignment]

    # Insert all player stat lines
    all_stats: list[PGS] = h.player_stats + a.player_stats
    for ps in all_stats:
        conn.execute(
            """
            INSERT INTO player_game_stats (
                game_id, player_id, team_id, position,
                pass_attempts, pass_completions, pass_yards, pass_touchdowns,
                interceptions_thrown, sacks_taken,
                rush_attempts, rush_yards, rush_touchdowns, fumbles_lost,
                targets, receptions, receiving_yards, receiving_touchdowns,
                tackles, sacks, tackles_for_loss, interceptions,
                pass_deflections, forced_fumbles, fumble_recoveries,
                fg_attempts, fg_made, xp_attempts, xp_made,
                punts, punt_yards, defensive_touchdowns
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?
            )
            """,
            (
                game_id, ps.player_id, ps.team_id, ps.position,
                ps.pass_attempts, ps.pass_completions, ps.pass_yards, ps.pass_touchdowns,
                ps.interceptions_thrown, ps.sacks_taken,
                ps.rush_attempts, ps.rush_yards, ps.rush_touchdowns, ps.fumbles_lost,
                ps.targets, ps.receptions, ps.receiving_yards, ps.receiving_touchdowns,
                ps.tackles, ps.sacks, ps.tackles_for_loss, ps.interceptions,
                ps.pass_deflections, ps.forced_fumbles, ps.fumble_recoveries,
                ps.fg_attempts, ps.fg_made, ps.xp_attempts, ps.xp_made,
                ps.punts, ps.punt_yards, ps.defensive_touchdowns,
            ),
        )
    conn.commit()
    return game_id


def get_game_by_id(
    game_id: int,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Return a game row as dict, or None."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        return dict(row) if row else None
    finally:
        if close:
            conn.close()


def get_games_for_team(
    team_id: int,
    season: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Return all games involving *team_id*, optionally filtered by season."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        sql = "SELECT * FROM games WHERE home_team_id = ? OR away_team_id = ?"
        params: list[Any] = [team_id, team_id]
        if season is not None:
            sql += " AND season = ?"
            params.append(season)
        sql += " ORDER BY season, week"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close:
            conn.close()


def get_player_stats_for_game(
    game_id: int,
    team_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Return player_game_stats rows for a game (with player name), optionally filtered by team."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        base = """
            SELECT pgs.*, p.name AS name
            FROM player_game_stats pgs
            LEFT JOIN players p ON pgs.player_id = p.id
            WHERE pgs.game_id = ?
        """
        if team_id is not None:
            rows = conn.execute(base + " AND pgs.team_id = ?", (game_id, team_id)).fetchall()
        else:
            rows = conn.execute(base, (game_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close:
            conn.close()


def get_team_record(
    team_id: int,
    season: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Return {'wins': W, 'losses': L, 'ties': T} for a team."""
    games = get_games_for_team(team_id, season=season, conn=conn)
    wins = losses = ties = 0
    for g in games:
        if g["home_team_id"] == team_id:
            my_score, opp_score = g["home_score"], g["away_score"]
        else:
            my_score, opp_score = g["away_score"], g["home_score"]
        if my_score > opp_score:
            wins += 1
        elif my_score < opp_score:
            losses += 1
        else:
            ties += 1
    return {"wins": wins, "losses": losses, "ties": ties}


# ---------------------------------------------------------------------------
# Season state
# ---------------------------------------------------------------------------

# Offseason step order (after regular season ends)
OFFSEASON_STEPS = (
    "season_summary",   # 0) End-of-season report (expected vs actual place, stats)
    "team_change",      # 1) User can change teams
    "skill_points",     # 2) Spend earned skill points on GM attributes
    "freshmen",         # 3) New HS freshmen class
    "recruiting",       # 4) HS seniors -> college (best recruited, rest retire)
    "draft",            # 5) College seniors -> NFL (best drafted, rest retire)
    "training_camp",    # 6) HS training camps (user sets focus; run dev)
    "development",      # 7) Offseason development for all (higher rate)
    "complete",         # 8) Advance class years, new schedule, week 1
)


def init_season_state(conn: sqlite3.Connection, season: int = 1, week: int = 1) -> None:
    """Initialise the singleton season_state row (idempotent). Uses only core columns for compatibility."""
    conn.execute(
        "INSERT OR IGNORE INTO season_state (id, current_season, current_week) VALUES (1, ?, ?)",
        (season, week),
    )
    conn.commit()


def get_season_state(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return current_season, current_week, phase, offseason_step. Migrates schema if needed."""
    row = conn.execute(
        "SELECT current_season, current_week FROM season_state WHERE id = 1"
    ).fetchone()
    if row is None:
        init_season_state(conn)
        return {"current_season": 1, "current_week": 1, "phase": "in_season", "offseason_step": None}
    out: dict[str, Any] = {
        "current_season": row["current_season"],
        "current_week": row["current_week"],
    }
    try:
        r2 = conn.execute(
            "SELECT phase, offseason_step FROM season_state WHERE id = 1"
        ).fetchone()
        if r2 is not None:
            out["phase"] = r2["phase"] or "in_season"
            out["offseason_step"] = r2["offseason_step"]
            return out
    except sqlite3.OperationalError:
        pass
    from db.schema import _migrate_season_state_offseason
    _migrate_season_state_offseason(conn)
    r2 = conn.execute(
        "SELECT phase, offseason_step FROM season_state WHERE id = 1"
    ).fetchone()
    out["phase"] = r2["phase"] if r2 else "in_season"
    out["offseason_step"] = r2["offseason_step"] if r2 else None
    return out


def advance_week(conn: sqlite3.Connection) -> None:
    """Increment current_week by 1."""
    conn.execute("UPDATE season_state SET current_week = current_week + 1 WHERE id = 1")
    conn.commit()


def enter_offseason(conn: sqlite3.Connection, completed_team_id: int | None = None) -> None:
    """Set phase to offseason and first step (season_summary). Call when week 18 ends.
    If completed_team_id is provided, store it for awarding skill points (team the manager coached that season).
    """
    conn.execute(
        """
        UPDATE season_state
        SET phase = 'offseason', offseason_step = ?, completed_season_team_id = COALESCE(?, completed_season_team_id)
        WHERE id = 1
        """,
        (OFFSEASON_STEPS[0], completed_team_id),
    )
    conn.commit()


def get_completed_season_team_id(conn: sqlite3.Connection) -> int | None:
    """Team id the manager coached when the season ended (for awarding skill points)."""
    row = conn.execute(
        "SELECT completed_season_team_id FROM season_state WHERE id = 1"
    ).fetchone()
    if row is None:
        return None
    try:
        return row["completed_season_team_id"]
    except (IndexError, KeyError, sqlite3.OperationalError):
        return None


def set_offseason_step(conn: sqlite3.Connection, step: str | None) -> None:
    """Set current offseason step (or NULL when returning to in_season)."""
    conn.execute(
        "UPDATE season_state SET offseason_step = ? WHERE id = 1",
        (step,),
    )
    conn.commit()


def advance_offseason_step(conn: sqlite3.Connection) -> str | None:
    """Move to next offseason step. Returns new step or None if no next step."""
    state = get_season_state(conn)
    step = state.get("offseason_step")
    if not step:
        return None
    try:
        idx = OFFSEASON_STEPS.index(step)
    except ValueError:
        return None
    if idx + 1 >= len(OFFSEASON_STEPS):
        return None
    next_step = OFFSEASON_STEPS[idx + 1]
    set_offseason_step(conn, next_step)
    return next_step


def advance_to_new_season(conn: sqlite3.Connection) -> None:
    """Set phase=in_season, current_week=1, current_season+1, clear offseason_step."""
    conn.execute(
        """
        UPDATE season_state
        SET phase = 'in_season', current_week = 1, current_season = current_season + 1, offseason_step = NULL
        WHERE id = 1
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Season summary & skill points (offseason)
# ---------------------------------------------------------------------------

def get_season_summary(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
) -> dict[str, Any] | None:
    """
    Return end-of-season summary for a team: expected place (by prestige), actual place (by standings),
    wins, losses, points_for, points_against, num_teams, division_name, team_name.
    Returns None if team or division not found.
    """
    div = get_division_for_team(team_id, conn)
    if not div:
        return None
    division_id = div["id"]
    division_name = div["name"]
    team_row = conn.execute("SELECT id, name FROM teams WHERE id = ?", (team_id,)).fetchone()
    if not team_row:
        return None
    team_name = team_row["name"]
    # Expected order: teams in division sorted by prestige DESC (rank 1 = highest prestige)
    teams_by_prestige = conn.execute(
        "SELECT id, name, prestige FROM teams WHERE division_id = ? ORDER BY prestige DESC, id",
        (division_id,),
    ).fetchall()
    expected_rank = None
    for i, t in enumerate(teams_by_prestige):
        if t["id"] == team_id:
            expected_rank = i + 1
            break
    if expected_rank is None:
        return None
    standings = get_division_standings(division_id, season, conn)
    actual_rank = None
    wins = losses = points_for = points_against = 0
    for i, s in enumerate(standings):
        if s["team_id"] == team_id:
            actual_rank = i + 1
            wins = s["wins"]
            losses = s["losses"]
            points_for = s["points_for"]
            points_against = s["points_against"]
            break
    if actual_rank is None:
        return None
    num_teams = len(standings)
    return {
        "team_id": team_id,
        "team_name": team_name,
        "division_name": division_name,
        "season": season,
        "expected_place": expected_rank,
        "actual_place": actual_rank,
        "wins": wins,
        "losses": losses,
        "points_for": points_for,
        "points_against": points_against,
        "num_teams": num_teams,
    }


def compute_skill_points_earned(expected_place: int, actual_place: int, num_teams: int) -> int:
    """
    Points earned from performance vs expectations. Bias toward finishing higher:
    expected 1 / actual 1 is better than expected 10 / actual 10.
    """
    base = 2
    place_diff = expected_place - actual_place  # positive = beat expectation
    # Bias: finishing 1st gives more than finishing last (e.g. (num_teams + 1 - actual_place) // 2)
    bias = max(0, (num_teams + 1 - actual_place) // 2)
    return max(1, base + place_diff + bias)


def update_manager_prestige_after_season(
    conn: sqlite3.Connection,
    manager_id: int,
    expected_place: int,
    actual_place: int,
    num_teams: int,
) -> None:
    """Update manager prestige based on performance vs expectations. Clamped 0-99."""
    row = conn.execute("SELECT prestige FROM managers WHERE id = ?", (manager_id,)).fetchone()
    if not row:
        return
    current = row["prestige"]
    delta = (expected_place - actual_place) * 2  # beat expectation -> +prestige
    new_prestige = max(0, min(99, current + delta))
    conn.execute("UPDATE managers SET prestige = ? WHERE id = ?", (new_prestige, manager_id))
    conn.commit()


def update_team_prestige_from_standings(
    conn: sqlite3.Connection,
    division_id: int,
    season: int,
    drift: float = 0.3,
) -> None:
    """
    Drift each team's prestige toward a value based on where they finished.
    finish 1 -> target 99, last -> target 0, linear in between.
    new_prestige = current * (1 - drift) + target * drift. Clamped 0-99.
    """
    standings = get_division_standings(division_id, season, conn)
    if not standings:
        return
    num_teams = len(standings)
    for rank, s in enumerate(standings, start=1):
        tid = s["team_id"]
        target = round(99 * (num_teams - rank + 1) / num_teams) if num_teams else 50
        row = conn.execute("SELECT prestige FROM teams WHERE id = ?", (tid,)).fetchone()
        if not row:
            continue
        current = row["prestige"]
        new_val = current * (1 - drift) + target * drift
        new_prestige = max(0, min(99, round(new_val)))
        conn.execute("UPDATE teams SET prestige = ? WHERE id = ?", (new_prestige, tid))
    conn.commit()


def run_season_rewards(
    conn: sqlite3.Connection,
    manager_id: int,
    season: int,
) -> dict[str, Any]:
    """
    Award skill points and update manager + team prestige for the completed season.
    Uses completed_season_team_id (team the manager coached). Returns summary dict
    (points_earned, expected_place, actual_place, etc.) or empty dict if no summary.
    """
    team_id = get_completed_season_team_id(conn)
    if team_id is None:
        return {}
    summary = get_season_summary(conn, team_id, season)
    if not summary:
        return {}
    points_earned = compute_skill_points_earned(
        summary["expected_place"],
        summary["actual_place"],
        summary["num_teams"],
    )
    add_unspent_skill_points(conn, manager_id, points_earned)
    update_manager_prestige_after_season(
        conn,
        manager_id,
        summary["expected_place"],
        summary["actual_place"],
        summary["num_teams"],
    )
    # Drift all divisions' team prestige toward this season's finish
    div_rows = conn.execute("SELECT id FROM divisions ORDER BY id").fetchall()
    for d in div_rows:
        update_team_prestige_from_standings(conn, d["id"], season, drift=0.3)
    return {
        **summary,
        "points_earned": points_earned,
    }


def add_unspent_skill_points(conn: sqlite3.Connection, manager_id: int, points: int) -> None:
    """Add earned skill points to manager's unspent pool."""
    conn.execute(
        "UPDATE managers SET unspent_skill_points = unspent_skill_points + ? WHERE id = ?",
        (points, manager_id),
    )
    conn.commit()


def spend_skill_points(
    conn: sqlite3.Connection,
    manager_id: int,
    skill_deltas: dict[str, int],
) -> tuple[bool, str]:
    """
    Apply positive skill deltas (add-only, no respec). Deduct from unspent.
    Returns (success, message). Skills capped at 99.
    """
    from models import MANAGER_SKILLS

    row = conn.execute(
        "SELECT unspent_skill_points, scouting, developing_potential, unlocking_potential, convincing_players, in_game_management FROM managers WHERE id = ?",
        (manager_id,),
    ).fetchone()
    if not row:
        return False, "Manager not found."
    unspent = row["unspent_skill_points"]
    total_requested = 0
    updates: dict[str, int] = {}
    for key in MANAGER_SKILLS:
        delta = skill_deltas.get(key, 0)
        if delta < 0:
            return False, "Cannot reduce skills; only add points."
        if delta == 0:
            continue
        total_requested += delta
        current = row[key]
        new_val = min(99, current + delta)
        updates[key] = new_val
    if total_requested > unspent:
        return False, f"Not enough unspent points (have {unspent}, requested {total_requested})."
    if not updates:
        return True, "No changes."
    set_clauses = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [unspent - total_requested, manager_id]
    conn.execute(
        f"UPDATE managers SET {set_clauses}, unspent_skill_points = ? WHERE id = ?",
        values,
    )
    conn.commit()
    return True, "Skills updated."


def get_teams_in_division_order(conn: sqlite3.Connection, level: str) -> list[dict[str, Any]]:
    """Return all teams for a level (high_school|college|professional), one dict per team with id, name, division_id, prestige, nil_budget."""
    rows = conn.execute(
        """
        SELECT t.id, t.name, t.division_id, t.prestige, t.nil_budget
        FROM teams t
        JOIN divisions d ON t.division_id = d.id
        WHERE d.level = ?
        ORDER BY d.id, t.id
        """,
        (level,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_team_record_for_season(
    conn: sqlite3.Connection, team_id: int, season: int
) -> dict[str, int]:
    """Return wins, losses, ties for a team in a given season (for draft order)."""
    return get_team_record(team_id, season=season, conn=conn)


def get_players_at_level_with_class(
    conn: sqlite3.Connection,
    level: str,
    class_year: int,
) -> list[dict[str, Any]]:
    """Return full player dicts for all players at the given level (high_school|college|professional) with given class_year."""
    rows = conn.execute(
        f"""
        SELECT {_PLAYER_SELECT_COLS_PREFIXED}
        FROM players p
        JOIN teams t ON p.team_id = t.id
        JOIN divisions d ON t.division_id = d.id
        WHERE d.level = ? AND p.class_year = ?
        ORDER BY p.potential DESC, p.overall DESC, p.id
        """,
        (level, class_year),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("name") is None:
            d["name"] = f"Player #{d['id']}"
        if d.get("potential") is None:
            d["potential"] = d.get("overall", 0)
        if d.get("class_year") is None:
            d["class_year"] = 1
        d["team_name"] = ""
        trow = conn.execute("SELECT name FROM teams WHERE id = ?", (d["team_id"],)).fetchone()
        if trow:
            d["team_name"] = trow["name"]
        out.append(d)
    return out


def delete_player(conn: sqlite3.Connection, player_id: int, *, commit: bool = True) -> None:
    """Remove player from depth_chart then delete from players. Caller must handle player_game_stats if needed."""
    conn.execute("DELETE FROM depth_chart WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM player_development_log WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM player_game_stats WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
    if commit:
        conn.commit()


def transfer_player_to_team(
    conn: sqlite3.Connection,
    player_id: int,
    new_team_id: int,
    *,
    new_class_year: int | None = None,
    commit: bool = True,
) -> None:
    """Move player to new team: update team_id (and optionally class_year), remove from old depth_chart, add to new team at end of position."""
    row = conn.execute(
        "SELECT team_id, position FROM players WHERE id = ?",
        (player_id,),
    ).fetchone()
    if row is None:
        return
    old_team_id = row["team_id"]
    position = row["position"]
    if old_team_id == new_team_id:
        return
    conn.execute("DELETE FROM depth_chart WHERE team_id = ? AND player_id = ?", (old_team_id, player_id))
    if new_class_year is not None:
        conn.execute(
            "UPDATE players SET team_id = ?, class_year = ? WHERE id = ?",
            (new_team_id, max(1, min(4, new_class_year)), player_id),
        )
    else:
        conn.execute("UPDATE players SET team_id = ? WHERE id = ?", (new_team_id, player_id))
    # Append to new team's depth at this position
    depth_rows = conn.execute(
        "SELECT rank FROM depth_chart WHERE team_id = ? AND position = ? ORDER BY rank",
        (new_team_id, position),
    ).fetchall()
    next_rank = len(depth_rows)
    conn.execute(
        "INSERT INTO depth_chart (team_id, position, rank, player_id) VALUES (?, ?, ?, ?)",
        (new_team_id, position, next_rank, player_id),
    )
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# Practice plan and development log
# ---------------------------------------------------------------------------

def get_practice_plan(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
    week: int,
) -> dict[str, str] | None:
    """Return {offense_focus, defense_focus} for team/season/week, or None if not set."""
    row = conn.execute(
        "SELECT offense_focus, defense_focus FROM practice_plan WHERE team_id = ? AND season = ? AND week = ?",
        (team_id, season, week),
    ).fetchone()
    if row is None:
        return None
    return {"offense_focus": row["offense_focus"], "defense_focus": row["defense_focus"]}


def set_practice_plan(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
    week: int,
    offense_focus: str,
    defense_focus: str,
) -> None:
    """Upsert practice plan for team/season/week (separate offense and defense focus)."""
    conn.execute(
        """
        INSERT INTO practice_plan (team_id, season, week, offense_focus, defense_focus)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(team_id, season, week) DO UPDATE SET
            offense_focus = excluded.offense_focus,
            defense_focus = excluded.defense_focus
        """,
        (team_id, season, week, offense_focus, defense_focus),
    )
    conn.commit()


def copy_practice_plans_to_next_week(
    conn: sqlite3.Connection,
    season: int,
    cur_week: int,
) -> None:
    """Copy each team's practice plan from cur_week to cur_week+1 so selection carries over."""
    next_week = cur_week + 1
    rows = conn.execute(
        "SELECT team_id, offense_focus, defense_focus FROM practice_plan WHERE season = ? AND week = ?",
        (season, cur_week),
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT INTO practice_plan (team_id, season, week, offense_focus, defense_focus)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(team_id, season, week) DO UPDATE SET
                offense_focus = excluded.offense_focus,
                defense_focus = excluded.defense_focus
            """,
            (row["team_id"], season, next_week, row["offense_focus"], row["defense_focus"]),
        )
    conn.commit()


def get_all_team_ids(conn: sqlite3.Connection) -> list[int]:
    """Return all team ids (for running development for every team)."""
    rows = conn.execute("SELECT id FROM teams ORDER BY id").fetchall()
    return [r["id"] for r in rows]


def get_developing_potential_for_team(conn: sqlite3.Connection, team_id: int) -> int:
    """Return manager developing_potential if manager's current team is this team, else 50."""
    row = conn.execute(
        "SELECT developing_potential FROM managers WHERE current_team_id = ? ORDER BY id DESC LIMIT 1",
        (team_id,),
    ).fetchone()
    if row is None:
        return 50
    return int(row["developing_potential"])


def insert_development_log(
    conn: sqlite3.Connection,
    player_id: int,
    season: int,
    week: int,
    attribute: str,
    change: int,
    *,
    commit: bool = True,
) -> None:
    """Append one row to player_development_log. If commit is False, caller must commit (e.g. to batch)."""
    conn.execute(
        "INSERT INTO player_development_log (player_id, season, week, attribute, change) VALUES (?, ?, ?, ?, ?)",
        (player_id, season, week, attribute, change),
    )
    if commit:
        conn.commit()


def get_player_development_recent(
    conn: sqlite3.Connection,
    player_id: int,
    season: int,
    from_week: int,
    weeks_back: int = 8,
) -> list[dict[str, Any]]:
    """Return development log entries for player in season, from (from_week - weeks_back) to from_week. Sum by attribute."""
    start_week = max(1, from_week - weeks_back)
    rows = conn.execute(
        """
        SELECT attribute, SUM(change) AS total_change
        FROM player_development_log
        WHERE player_id = ? AND season = ? AND week >= ? AND week <= ?
        GROUP BY attribute
        HAVING total_change != 0
        ORDER BY attribute
        """,
        (player_id, season, start_week, from_week),
    ).fetchall()
    return [{"attribute": r["attribute"], "change": int(r["total_change"])} for r in rows]


def get_team_player_development_totals(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
) -> dict[int, int]:
    """Return total development gain per player for team this season. player_id -> total gain."""
    rows = conn.execute(
        """
        SELECT pdl.player_id, COALESCE(SUM(pdl.change), 0) AS total
        FROM player_development_log pdl
        JOIN players p ON p.id = pdl.player_id
        WHERE p.team_id = ? AND pdl.season = ?
        GROUP BY pdl.player_id
        """,
        (team_id, season),
    ).fetchall()
    return {r["player_id"]: int(r["total"]) for r in rows}


def get_team_player_development_for_week(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
    week: int,
) -> dict[int, int]:
    """Return development gain per player for team in a single week. player_id -> gain."""
    rows = conn.execute(
        """
        SELECT pdl.player_id, COALESCE(SUM(pdl.change), 0) AS total
        FROM player_development_log pdl
        JOIN players p ON p.id = pdl.player_id
        WHERE p.team_id = ? AND pdl.season = ? AND pdl.week = ?
        GROUP BY pdl.player_id
        """,
        (team_id, season, week),
    ).fetchall()
    return {r["player_id"]: int(round(float(r["total"]))) for r in rows}


def get_team_player_development_by_attribute_for_week(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
    week: int,
) -> list[tuple[int, str, int]]:
    """Return (player_id, attribute, total_change) for team in a single week. Only rows with change > 0."""
    rows = conn.execute(
        """
        SELECT pdl.player_id, pdl.attribute, SUM(pdl.change) AS total
        FROM player_development_log pdl
        JOIN players p ON p.id = pdl.player_id
        WHERE p.team_id = ? AND pdl.season = ? AND pdl.week = ?
        GROUP BY pdl.player_id, pdl.attribute
        HAVING total > 0
        ORDER BY pdl.player_id, pdl.attribute
        """,
        (team_id, season, week),
    ).fetchall()
    return [(r["player_id"], r["attribute"], int(round(float(r["total"])))) for r in rows]


def get_team_player_development_by_attribute_for_season(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
) -> list[tuple[int, str, int]]:
    """Return (player_id, attribute, total_change) for team over the full season. Only rows with change > 0."""
    rows = conn.execute(
        """
        SELECT pdl.player_id, pdl.attribute, SUM(pdl.change) AS total
        FROM player_development_log pdl
        JOIN players p ON p.id = pdl.player_id
        WHERE p.team_id = ? AND pdl.season = ?
        GROUP BY pdl.player_id, pdl.attribute
        HAVING total > 0
        ORDER BY pdl.player_id, pdl.attribute
        """,
        (team_id, season),
    ).fetchall()
    return [(r["player_id"], r["attribute"], int(round(float(r["total"])))) for r in rows]


def get_team_development_summary(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
    week: int,
) -> dict[str, Any]:
    """
    Return practice results summary for team/season/week: players improved and total gain
    by unit (offense, defense, special).
    """
    from models.constants import POSITIONS_OFFENSE, POSITIONS_DEFENSE, POSITIONS_SPECIAL_TEAMS

    rows = conn.execute(
        """
        SELECT pdl.player_id, p.position, SUM(pdl.change) AS total
        FROM player_development_log pdl
        JOIN players p ON p.id = pdl.player_id
        WHERE p.team_id = ? AND pdl.season = ? AND pdl.week = ?
        GROUP BY pdl.player_id, p.position
        HAVING total > 0
        """,
        (team_id, season, week),
    ).fetchall()
    offense_players = 0
    offense_gain = 0
    defense_players = 0
    defense_gain = 0
    special_players = 0
    special_gain = 0
    for r in rows:
        pos = r["position"] or ""
        total = int(r["total"])
        if pos in POSITIONS_OFFENSE:
            offense_players += 1
            offense_gain += total
        elif pos in POSITIONS_DEFENSE:
            defense_players += 1
            defense_gain += total
        else:
            special_players += 1
            special_gain += total
    return {
        "offense_players": offense_players,
        "offense_gain": offense_gain,
        "defense_players": defense_players,
        "defense_gain": defense_gain,
        "special_players": special_players,
        "special_gain": special_gain,
    }


# ---------------------------------------------------------------------------
# Schedule persistence
# ---------------------------------------------------------------------------

def insert_schedule_entry(
    conn: sqlite3.Connection,
    season: int,
    week: int,
    division_id: int,
    home_team_id: int,
    away_team_id: int,
) -> int:
    """Insert one schedule row. Returns id."""
    cur = conn.execute(
        """
        INSERT INTO schedule (season, week, division_id, home_team_id, away_team_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (season, week, division_id, home_team_id, away_team_id),
    )
    return cur.lastrowid  # type: ignore[return-value]


def bulk_insert_schedule(
    conn: sqlite3.Connection,
    rows: list[tuple[int, int, int, int, int]],
) -> None:
    """Batch-insert schedule rows: [(season, week, division_id, home, away), ...]."""
    conn.executemany(
        "INSERT INTO schedule (season, week, division_id, home_team_id, away_team_id) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def get_week_schedule(
    conn: sqlite3.Connection,
    season: int,
    week: int,
) -> list[dict[str, Any]]:
    """Return all scheduled matchups for a given week (all divisions)."""
    rows = conn.execute(
        """
        SELECT s.id, s.division_id, s.home_team_id, s.away_team_id, s.game_id
        FROM schedule s
        WHERE s.season = ? AND s.week = ?
        ORDER BY s.division_id, s.id
        """,
        (season, week),
    ).fetchall()
    return [dict(r) for r in rows]


def set_schedule_game_id(conn: sqlite3.Connection, schedule_id: int, game_id: int) -> None:
    """Link a schedule row to the resulting game."""
    conn.execute(
        "UPDATE schedule SET game_id = ? WHERE id = ?",
        (game_id, schedule_id),
    )


# ---------------------------------------------------------------------------
# Standings / schedule display helpers
# ---------------------------------------------------------------------------

def get_division_standings(
    division_id: int,
    season: int,
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Return standings for a division: sorted by wins desc, point-diff desc."""
    teams = conn.execute(
        "SELECT id, name FROM teams WHERE division_id = ? ORDER BY name",
        (division_id,),
    ).fetchall()

    standings: list[dict[str, Any]] = []
    for t in teams:
        tid = t["id"]
        games = conn.execute(
            """
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM games
            WHERE season = ? AND (home_team_id = ? OR away_team_id = ?)
            """,
            (season, tid, tid),
        ).fetchall()
        w = l_ = tie = pf = pa = 0
        for g in games:
            if g["home_team_id"] == tid:
                ms, os_ = g["home_score"], g["away_score"]
            else:
                ms, os_ = g["away_score"], g["home_score"]
            pf += ms
            pa += os_
            if ms > os_:
                w += 1
            elif ms < os_:
                l_ += 1
            else:
                tie += 1
        standings.append({
            "team_id": tid,
            "team_name": t["name"],
            "wins": w,
            "losses": l_,
            "ties": tie,
            "points_for": pf,
            "points_against": pa,
        })

    standings.sort(key=lambda x: (-x["wins"], -(x["points_for"] - x["points_against"]), x["team_name"]))
    return standings


def get_division_team_stat_leaders(
    division_id: int,
    season: int,
    conn: sqlite3.Connection,
) -> dict[str, list[dict[str, Any]]]:
    """Return top-5 team-level stat leaders per category (total_yards, rush_yards, pass_yards, fewest_turnovers).
    Each entry: {team_id, team_name, value}. Same shape as division stat leaders for consistent UI."""
    teams = conn.execute(
        "SELECT id, name FROM teams WHERE division_id = ? ORDER BY name",
        (division_id,),
    ).fetchall()

    result: dict[str, list[dict[str, Any]]] = {}
    for tid, tname in [(t["id"], t["name"]) for t in teams]:
        games = conn.execute(
            """
            SELECT home_team_id, away_team_id,
                   home_total_yards, home_rush_yards, home_pass_yards, home_turnovers,
                   away_total_yards, away_rush_yards, away_pass_yards, away_turnovers
            FROM games
            WHERE season = ? AND (home_team_id = ? OR away_team_id = ?)
            """,
            (season, tid, tid),
        ).fetchall()
        total_yards = rush_yards = pass_yards = turnovers = 0
        for g in games:
            if g["home_team_id"] == tid:
                total_yards += g["home_total_yards"] or 0
                rush_yards += g["home_rush_yards"] or 0
                pass_yards += g["home_pass_yards"] or 0
                turnovers += g["home_turnovers"] or 0
            else:
                total_yards += g["away_total_yards"] or 0
                rush_yards += g["away_rush_yards"] or 0
                pass_yards += g["away_pass_yards"] or 0
                turnovers += g["away_turnovers"] or 0

        for key, val in [
            ("total_yards", total_yards),
            ("rush_yards", rush_yards),
            ("pass_yards", pass_yards),
            ("turnovers", turnovers),
        ]:
            result.setdefault(key, []).append({
                "team_id": tid,
                "team_name": tname,
                "value": val,
            })

    # Sort each category and take top 5; for turnovers we want fewest first
    out: dict[str, list[dict[str, Any]]] = {}
    for key in ("total_yards", "rush_yards", "pass_yards"):
        sorted_list = sorted(result.get(key, []), key=lambda x: -x["value"])[:5]
        out[key] = sorted_list
    sorted_turnovers = sorted(result.get("turnovers", []), key=lambda x: x["value"])[:5]
    out["fewest_turnovers"] = sorted_turnovers
    return out


def get_team_schedule_display(
    team_id: int,
    season: int,
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Return a user-friendly schedule list for a team with results."""
    rows = conn.execute(
        """
        SELECT s.week, s.home_team_id, s.away_team_id, s.game_id,
               ht.name AS home_name, at.name AS away_name,
               g.home_score, g.away_score
        FROM schedule s
        JOIN teams ht ON s.home_team_id = ht.id
        JOIN teams at ON s.away_team_id = at.id
        LEFT JOIN games g ON s.game_id = g.id
        WHERE s.season = ? AND (s.home_team_id = ? OR s.away_team_id = ?)
        ORDER BY s.week
        """,
        (season, team_id, team_id),
    ).fetchall()

    schedule: list[dict[str, Any]] = []
    for r in rows:
        is_home = r["home_team_id"] == team_id
        opp_name = r["away_name"] if is_home else r["home_name"]
        opp_id = r["away_team_id"] if is_home else r["home_team_id"]

        result = None
        user_score = opp_score = None
        if r["game_id"] is not None:
            user_score = r["home_score"] if is_home else r["away_score"]
            opp_score = r["away_score"] if is_home else r["home_score"]
            if user_score > opp_score:
                result = "W"
            elif user_score < opp_score:
                result = "L"
            else:
                result = "T"

        schedule.append({
            "week": r["week"],
            "opponent_name": opp_name,
            "opponent_id": opp_id,
            "is_home": is_home,
            "game_id": r["game_id"],
            "user_score": user_score,
            "opp_score": opp_score,
            "result": result,
        })
    return schedule


def get_division_for_team(team_id: int, conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the division dict (id, name, level) for a team."""
    row = conn.execute(
        """
        SELECT d.id, d.name, d.level
        FROM divisions d
        JOIN teams t ON t.division_id = d.id
        WHERE t.id = ?
        """,
        (team_id,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Player profile & season stats
# ---------------------------------------------------------------------------

def get_player_by_id(
    player_id: int,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Return full player row as dict, or None."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        row = conn.execute(
            f"SELECT {_PLAYER_SELECT_COLS} FROM players WHERE id = ?",
            (player_id,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("name") is None:
            d["name"] = f"Player #{d['id']}"
        if d.get("potential") is None:
            d["potential"] = d.get("overall", 0)
        if d.get("class_year") is None:
            d["class_year"] = 1
        # Attach team name
        t = conn.execute("SELECT name FROM teams WHERE id = ?", (d["team_id"],)).fetchone()
        d["team_name"] = t["name"] if t else "Unknown"
        return d
    finally:
        if close:
            conn.close()


def get_player_season_stats(
    player_id: int,
    season: int,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return aggregated season stats for a player."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS games_played,
                SUM(pass_attempts) AS pass_attempts,
                SUM(pass_completions) AS pass_completions,
                SUM(pass_yards) AS pass_yards,
                SUM(pass_touchdowns) AS pass_touchdowns,
                SUM(interceptions_thrown) AS interceptions_thrown,
                SUM(sacks_taken) AS sacks_taken,
                SUM(rush_attempts) AS rush_attempts,
                SUM(rush_yards) AS rush_yards,
                SUM(rush_touchdowns) AS rush_touchdowns,
                SUM(fumbles_lost) AS fumbles_lost,
                SUM(targets) AS targets,
                SUM(receptions) AS receptions,
                SUM(receiving_yards) AS receiving_yards,
                SUM(receiving_touchdowns) AS receiving_touchdowns,
                SUM(tackles) AS tackles,
                SUM(sacks) AS sacks,
                SUM(tackles_for_loss) AS tackles_for_loss,
                SUM(interceptions) AS interceptions,
                SUM(pass_deflections) AS pass_deflections,
                SUM(forced_fumbles) AS forced_fumbles,
                SUM(fumble_recoveries) AS fumble_recoveries,
                SUM(fg_attempts) AS fg_attempts,
                SUM(fg_made) AS fg_made,
                SUM(xp_attempts) AS xp_attempts,
                SUM(xp_made) AS xp_made,
                SUM(punts) AS punts,
                SUM(punt_yards) AS punt_yards,
                SUM(defensive_touchdowns) AS defensive_touchdowns
            FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.id
            WHERE pgs.player_id = ? AND g.season = ?
            """,
            (player_id, season),
        ).fetchone()
        if row is None or row["games_played"] == 0:
            return {"games_played": 0}
        return dict(row)
    finally:
        if close:
            conn.close()


def get_player_prior_season_stats(
    player_id: int,
    current_season: int,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Return aggregated stats per prior season for a player (seasons < current_season).
    Each dict has year, level (division level), games_played, and all stat sums."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        rows = conn.execute(
            """
            SELECT
                g.season AS year,
                MAX(d.level) AS level,
                COUNT(*) AS games_played,
                SUM(pgs.pass_attempts) AS pass_attempts,
                SUM(pgs.pass_completions) AS pass_completions,
                SUM(pgs.pass_yards) AS pass_yards,
                SUM(pgs.pass_touchdowns) AS pass_touchdowns,
                SUM(pgs.interceptions_thrown) AS interceptions_thrown,
                SUM(pgs.sacks_taken) AS sacks_taken,
                SUM(pgs.rush_attempts) AS rush_attempts,
                SUM(pgs.rush_yards) AS rush_yards,
                SUM(pgs.rush_touchdowns) AS rush_touchdowns,
                SUM(pgs.fumbles_lost) AS fumbles_lost,
                SUM(pgs.targets) AS targets,
                SUM(pgs.receptions) AS receptions,
                SUM(pgs.receiving_yards) AS receiving_yards,
                SUM(pgs.receiving_touchdowns) AS receiving_touchdowns,
                SUM(pgs.tackles) AS tackles,
                SUM(pgs.sacks) AS sacks,
                SUM(pgs.tackles_for_loss) AS tackles_for_loss,
                SUM(pgs.interceptions) AS interceptions,
                SUM(pgs.pass_deflections) AS pass_deflections,
                SUM(pgs.forced_fumbles) AS forced_fumbles,
                SUM(pgs.fumble_recoveries) AS fumble_recoveries,
                SUM(pgs.fg_attempts) AS fg_attempts,
                SUM(pgs.fg_made) AS fg_made,
                SUM(pgs.xp_attempts) AS xp_attempts,
                SUM(pgs.xp_made) AS xp_made,
                SUM(pgs.punts) AS punts,
                SUM(pgs.punt_yards) AS punt_yards,
                SUM(pgs.defensive_touchdowns) AS defensive_touchdowns
            FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.id
            JOIN teams t ON t.id = pgs.team_id
            JOIN divisions d ON d.id = t.division_id
            WHERE pgs.player_id = ? AND g.season < ?
            GROUP BY g.season
            ORDER BY g.season DESC
            """,
            (player_id, current_season),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close:
            conn.close()


def get_division_stat_leaders(
    division_id: int,
    season: int,
    conn: sqlite3.Connection,
) -> dict[str, list[dict[str, Any]]]:
    """Return top-5 stat leaders for a division across multiple categories.

    Returns dict with keys: passing_yards, rushing_yards, receiving_yards,
    receiving_receptions, sacks, interceptions — each a list of
    {player_id, name, team_id, team_name, value}.
    """
    # Get all team IDs in this division
    teams = conn.execute(
        "SELECT id, name FROM teams WHERE division_id = ?", (division_id,)
    ).fetchall()
    team_ids = [t["id"] for t in teams]
    team_names = {t["id"]: t["name"] for t in teams}

    if not team_ids:
        return {}

    placeholders = ",".join("?" * len(team_ids))

    categories = {
        "passing_yards": ("SUM(pgs.pass_yards)", "pgs.pass_attempts > 0"),
        "rushing_yards": ("SUM(pgs.rush_yards)", "pgs.rush_attempts > 0"),
        "receiving_yards": ("SUM(pgs.receiving_yards)", "pgs.targets > 0"),
        "receptions": ("SUM(pgs.receptions)", "pgs.targets > 0"),
        "sacks": ("SUM(pgs.sacks)", "1=1"),
        "interceptions": ("SUM(pgs.interceptions)", "1=1"),
    }

    result: dict[str, list[dict[str, Any]]] = {}
    for key, (agg_expr, where_extra) in categories.items():
        rows = conn.execute(
            f"""
            SELECT pgs.player_id, p.name, pgs.team_id,
                   {agg_expr} AS value
            FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.id
            JOIN players p ON pgs.player_id = p.id
            WHERE g.season = ? AND pgs.team_id IN ({placeholders})
              AND {where_extra}
            GROUP BY pgs.player_id
            HAVING value > 0
            ORDER BY value DESC
            LIMIT 5
            """,
            (season, *team_ids),
        ).fetchall()
        result[key] = [
            {
                "player_id": r["player_id"],
                "name": r["name"] or f"Player #{r['player_id']}",
                "team_id": r["team_id"],
                "team_name": team_names.get(r["team_id"], ""),
                "value": r["value"],
            }
            for r in rows
        ]
    return result


def get_team_profile(
    team_id: int,
    season: int,
    conn: sqlite3.Connection,
) -> dict[str, Any] | None:
    """Return team profile info: team details, record, top players, recent results."""
    team = get_team_by_id(team_id, conn)
    if team is None:
        return None

    division = get_division_for_team(team_id, conn)
    record = get_team_record(team_id, season=season, conn=conn)

    # Top players by overall (top 5)
    top_players = conn.execute(
        """SELECT id, name, position, overall, potential, class_year
           FROM players WHERE team_id = ?
           ORDER BY overall DESC LIMIT 5""",
        (team_id,),
    ).fetchall()
    top_players_list = []
    for p in top_players:
        d = dict(p)
        if d.get("name") is None:
            d["name"] = f"Player #{d['id']}"
        top_players_list.append(d)

    # Recent game results (last 5)
    recent_games = conn.execute(
        """
        SELECT g.id, g.week, g.home_team_id, g.away_team_id,
               g.home_score, g.away_score,
               ht.name AS home_name, at.name AS away_name
        FROM games g
        JOIN teams ht ON g.home_team_id = ht.id
        JOIN teams at ON g.away_team_id = at.id
        WHERE g.season = ? AND (g.home_team_id = ? OR g.away_team_id = ?)
        ORDER BY g.week DESC
        LIMIT 5
        """,
        (season, team_id, team_id),
    ).fetchall()

    recent = []
    for g in recent_games:
        is_home = g["home_team_id"] == team_id
        my_score = g["home_score"] if is_home else g["away_score"]
        opp_score = g["away_score"] if is_home else g["home_score"]
        opp_name = g["away_name"] if is_home else g["home_name"]
        result_str = "W" if my_score > opp_score else ("L" if my_score < opp_score else "T")
        recent.append({
            "game_id": g["id"],
            "week": g["week"],
            "opponent": opp_name,
            "is_home": is_home,
            "my_score": my_score,
            "opp_score": opp_score,
            "result": result_str,
        })

    return {
        "team": team,
        "division": division,
        "record": record,
        "top_players": top_players_list,
        "recent_games": recent,
    }


# ---------------------------------------------------------------------------
# Player database search (all levels, non-retired)
# ---------------------------------------------------------------------------

# Allowed player attribute columns for filter (numeric)
_PLAYER_SEARCH_NUMERIC_ATTRS = frozenset({
    "speed", "acceleration", "lateral_quickness", "vision",
    "lower_body_strength", "upper_body_strength", "arm_length",
    "vertical_jump", "broad_jump", "overall", "potential",
    "familiarity", "kick_power", "arm_strength", "run_block",
    "pass_rush", "pass_protection", "scrambling",
    "short_accuracy", "mid_accuracy", "deep_accuracy", "throw_under_pressure",
    "ball_security", "catching", "route_running",
    "tackling", "coverage", "block_shedding", "pursuit", "kick_accuracy",
    "height", "weight", "age", "class_year",
})

_ALLOWED_ATTR_OPS = frozenset({">", ">=", "=", "<=", "<", "!="})


def _build_one_condition(c: dict[str, Any]) -> tuple[str, list[Any]] | None:
    """Build (sql_fragment, params) for one condition dict. Returns None if invalid."""
    if not isinstance(c, dict) or "type" not in c:
        return None
    t = c.get("type")
    if t == "position":
        is_in = c.get("is_in", True)
        positions = c.get("positions") or []
        if not isinstance(positions, list):
            return None
        positions = [str(x).strip().upper() for x in positions if x]
        if not positions:
            return None
        placeholders = ", ".join("?" * len(positions))
        if is_in:
            sql = f"(p.position IN ({placeholders}) OR (p.secondary_position IS NOT NULL AND p.secondary_position IN ({placeholders})))"
        else:
            sql = f"(p.position NOT IN ({placeholders}) AND (p.secondary_position IS NULL OR p.secondary_position NOT IN ({placeholders})))"
        return sql, positions + positions
    elif t == "attribute":
        attr = (c.get("attribute") or "").strip().lower().replace(" ", "_")
        if attr not in _PLAYER_SEARCH_NUMERIC_ATTRS:
            return None
        op = (c.get("op") or "=").strip()
        if op not in _ALLOWED_ATTR_OPS:
            op = "="
        try:
            val = int(c.get("value", 0))
        except (TypeError, ValueError):
            return None
        return f"(p.{attr} {op} ?)", [val]
    elif t == "bio":
        field = (c.get("field") or "").strip().lower()
        if field == "level":
            level_val = (c.get("value") or "").strip().lower()
            if level_val not in ("high_school", "college", "professional"):
                return None
            return "(d.level = ?)", [level_val]
        elif field == "class_year":
            try:
                cy = int(c.get("value", 1))
                if 1 <= cy <= 4:
                    return "(p.class_year = ?)", [cy]
            except (TypeError, ValueError):
                pass
            return None
        elif field == "age":
            op = (c.get("op") or "=").strip()
            if op not in _ALLOWED_ATTR_OPS:
                op = "="
            try:
                age_val = int(c.get("value", 0))
                return f"(p.age {op} ?)", [age_val]
            except (TypeError, ValueError):
                return None
    return None


def search_players_database(
    conn: sqlite3.Connection,
    conditions: list[dict[str, Any]],
    connectives: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Return all players at every level (not retired; schema has no retired flag)
    that match the given conditions combined with AND/OR.
    conditions: list of condition dicts (type position|attribute|bio, ...).
    connectives: list of "and"|"or", length = len(conditions)-1; connective[i] joins condition i with i+1.
    Left-associative: (cond0 CONN0 cond1) CONN1 cond2. Default connectives = all "or".
    Returns list of player dicts with team_name and level (division level) added.
    """
    base_sql = f"""
        SELECT p.id, p.team_id, p.position, p.secondary_position, p.name, p.potential, p.class_year,
               p.height, p.weight, p.age, p.speed, p.acceleration, p.lateral_quickness, p.vision,
               p.lower_body_strength, p.upper_body_strength, p.arm_length, p.vertical_jump, p.broad_jump,
               p.overall, p.familiarity, p.kick_power, p.arm_strength, p.run_block, p.pass_rush,
               p.pass_protection, p.scrambling,
               p.short_accuracy, p.mid_accuracy, p.deep_accuracy, p.throw_under_pressure,
               p.ball_security, p.catching, p.route_running,
               p.tackling, p.coverage, p.block_shedding, p.pursuit, p.kick_accuracy,
               t.name AS team_name, d.level AS level
        FROM players p
        JOIN teams t ON p.team_id = t.id
        JOIN divisions d ON t.division_id = d.id
    """
    parts: list[tuple[str, list[Any]]] = []
    for c in conditions:
        one = _build_one_condition(c)
        if one is not None:
            parts.append(one)

    if not parts:
        base_sql += " ORDER BY p.overall DESC, p.position, p.id"
        rows = conn.execute(base_sql, []).fetchall()
    else:
        n = len(parts)
        if connectives is None or len(connectives) != n - 1:
            connectives = ["or"] * (n - 1)
        conn_normalized = []
        for i, conn_val in enumerate(connectives):
            conn_normalized.append("and" if (str(conn_val).strip().lower() == "and") else "or")

        where_sql = parts[0][0]
        all_params: list[Any] = list(parts[0][1])
        for i in range(1, n):
            conn_word = conn_normalized[i - 1].upper()
            where_sql = f"(({where_sql}) {conn_word} {parts[i][0]})"
            all_params.extend(parts[i][1])
        base_sql += " WHERE " + where_sql
        base_sql += " ORDER BY p.overall DESC, p.position, p.id"
        rows = conn.execute(base_sql, all_params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("name") is None:
            d["name"] = f"Player #{d['id']}"
        if d.get("potential") is None:
            d["potential"] = d.get("overall", 0)
        if d.get("class_year") is None:
            d["class_year"] = 1
        out.append(d)
    return out
