"""
SQLite schema for GM Career Mode.
Single save: one DB file. New manager = reset DB and create fresh.
"""
import os
import sqlite3
from pathlib import Path

# Single save path (relative to project root)
DB_DIR = "data"
DB_FILENAME = "game.db"


def get_db_path() -> Path:
    """Return absolute path to the single save DB file."""
    root = Path(__file__).resolve().parent.parent
    return root / DB_DIR / DB_FILENAME


def _ensure_db_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Open a connection to the save DB. Creates dir and file if needed.
    timeout: seconds to wait for lock (avoids 'database is locked' under concurrent requests).
    """
    path = get_db_path()
    _ensure_db_dir(path)
    conn = sqlite3.connect(str(path), timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Create all tables if they do not exist."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS managers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                scouting INTEGER NOT NULL,
                developing_potential INTEGER NOT NULL,
                unlocking_potential INTEGER NOT NULL,
                convincing_players INTEGER NOT NULL,
                in_game_management INTEGER NOT NULL,
                prestige INTEGER NOT NULL DEFAULT 50,
                unspent_skill_points INTEGER NOT NULL DEFAULT 0,
                current_team_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS divisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                level TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                division_id INTEGER NOT NULL REFERENCES divisions(id),
                name TEXT NOT NULL,
                prestige INTEGER NOT NULL,
                facility_grade INTEGER NOT NULL,
                nil_budget INTEGER,
                budget INTEGER
            );

            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL REFERENCES teams(id),
                position TEXT NOT NULL,
                secondary_position TEXT,
                name TEXT,
                potential INTEGER,
                class_year INTEGER,
                height INTEGER NOT NULL,
                weight INTEGER NOT NULL,
                age INTEGER NOT NULL,
                speed INTEGER NOT NULL,
                acceleration INTEGER NOT NULL,
                lateral_quickness INTEGER NOT NULL,
                vision INTEGER NOT NULL,
                lower_body_strength INTEGER NOT NULL,
                upper_body_strength INTEGER NOT NULL,
                arm_length INTEGER NOT NULL DEFAULT 32,
                vertical_jump INTEGER NOT NULL DEFAULT 50,
                broad_jump INTEGER NOT NULL DEFAULT 50,
                overall INTEGER NOT NULL,
                familiarity INTEGER NOT NULL,
                kick_power INTEGER NOT NULL,
                arm_strength INTEGER NOT NULL,
                run_block INTEGER NOT NULL,
                pass_rush INTEGER NOT NULL,
                pass_protection INTEGER NOT NULL,
                scrambling INTEGER NOT NULL,
                short_accuracy INTEGER NOT NULL DEFAULT 50,
                mid_accuracy INTEGER NOT NULL DEFAULT 50,
                deep_accuracy INTEGER NOT NULL DEFAULT 50,
                throw_under_pressure INTEGER NOT NULL DEFAULT 50,
                ball_security INTEGER NOT NULL DEFAULT 50,
                catching INTEGER NOT NULL DEFAULT 50,
                route_running INTEGER NOT NULL DEFAULT 50,
                tackling INTEGER NOT NULL DEFAULT 50,
                coverage INTEGER NOT NULL DEFAULT 50,
                block_shedding INTEGER NOT NULL DEFAULT 50,
                pursuit INTEGER NOT NULL DEFAULT 50,
                kick_accuracy INTEGER NOT NULL DEFAULT 50,
                speed_cap INTEGER NOT NULL DEFAULT 50,
                acceleration_cap INTEGER NOT NULL DEFAULT 50,
                lateral_quickness_cap INTEGER NOT NULL DEFAULT 50,
                vision_cap INTEGER NOT NULL DEFAULT 50,
                lower_body_strength_cap INTEGER NOT NULL DEFAULT 50,
                upper_body_strength_cap INTEGER NOT NULL DEFAULT 50,
                vertical_jump_cap INTEGER NOT NULL DEFAULT 50,
                broad_jump_cap INTEGER NOT NULL DEFAULT 50,
                familiarity_cap INTEGER NOT NULL DEFAULT 50,
                kick_power_cap INTEGER NOT NULL DEFAULT 50,
                arm_strength_cap INTEGER NOT NULL DEFAULT 50,
                run_block_cap INTEGER NOT NULL DEFAULT 50,
                pass_rush_cap INTEGER NOT NULL DEFAULT 50,
                pass_protection_cap INTEGER NOT NULL DEFAULT 50,
                scrambling_cap INTEGER NOT NULL DEFAULT 50,
                short_accuracy_cap INTEGER NOT NULL DEFAULT 50,
                mid_accuracy_cap INTEGER NOT NULL DEFAULT 50,
                deep_accuracy_cap INTEGER NOT NULL DEFAULT 50,
                throw_under_pressure_cap INTEGER NOT NULL DEFAULT 50,
                ball_security_cap INTEGER NOT NULL DEFAULT 50,
                catching_cap INTEGER NOT NULL DEFAULT 50,
                route_running_cap INTEGER NOT NULL DEFAULT 50,
                tackling_cap INTEGER NOT NULL DEFAULT 50,
                coverage_cap INTEGER NOT NULL DEFAULT 50,
                block_shedding_cap INTEGER NOT NULL DEFAULT 50,
                pursuit_cap INTEGER NOT NULL DEFAULT 50,
                kick_accuracy_cap INTEGER NOT NULL DEFAULT 50
            );

            CREATE TABLE IF NOT EXISTS setup_progress (
                manager_id INTEGER PRIMARY KEY REFERENCES managers(id),
                status TEXT NOT NULL,
                progress_pct REAL NOT NULL,
                current_step TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS depth_chart (
                team_id INTEGER NOT NULL REFERENCES teams(id),
                position TEXT NOT NULL,
                rank INTEGER NOT NULL,
                player_id INTEGER NOT NULL REFERENCES players(id),
                PRIMARY KEY (team_id, position, rank),
                UNIQUE (team_id, player_id)
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER NOT NULL DEFAULT 1,
                week INTEGER NOT NULL DEFAULT 1,
                home_team_id INTEGER NOT NULL REFERENCES teams(id),
                away_team_id INTEGER NOT NULL REFERENCES teams(id),
                home_score INTEGER NOT NULL,
                away_score INTEGER NOT NULL,
                -- Aggregate home stats
                home_total_yards INTEGER NOT NULL DEFAULT 0,
                home_rush_yards INTEGER NOT NULL DEFAULT 0,
                home_pass_yards INTEGER NOT NULL DEFAULT 0,
                home_turnovers INTEGER NOT NULL DEFAULT 0,
                -- Aggregate away stats
                away_total_yards INTEGER NOT NULL DEFAULT 0,
                away_rush_yards INTEGER NOT NULL DEFAULT 0,
                away_pass_yards INTEGER NOT NULL DEFAULT 0,
                away_turnovers INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS player_game_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL REFERENCES games(id),
                player_id INTEGER NOT NULL REFERENCES players(id),
                team_id INTEGER NOT NULL REFERENCES teams(id),
                position TEXT NOT NULL,
                -- Passing
                pass_attempts INTEGER NOT NULL DEFAULT 0,
                pass_completions INTEGER NOT NULL DEFAULT 0,
                pass_yards INTEGER NOT NULL DEFAULT 0,
                pass_touchdowns INTEGER NOT NULL DEFAULT 0,
                interceptions_thrown INTEGER NOT NULL DEFAULT 0,
                sacks_taken INTEGER NOT NULL DEFAULT 0,
                -- Rushing
                rush_attempts INTEGER NOT NULL DEFAULT 0,
                rush_yards INTEGER NOT NULL DEFAULT 0,
                rush_touchdowns INTEGER NOT NULL DEFAULT 0,
                fumbles_lost INTEGER NOT NULL DEFAULT 0,
                -- Receiving
                targets INTEGER NOT NULL DEFAULT 0,
                receptions INTEGER NOT NULL DEFAULT 0,
                receiving_yards INTEGER NOT NULL DEFAULT 0,
                receiving_touchdowns INTEGER NOT NULL DEFAULT 0,
                -- Defense
                tackles INTEGER NOT NULL DEFAULT 0,
                sacks REAL NOT NULL DEFAULT 0.0,
                tackles_for_loss INTEGER NOT NULL DEFAULT 0,
                interceptions INTEGER NOT NULL DEFAULT 0,
                pass_deflections INTEGER NOT NULL DEFAULT 0,
                forced_fumbles INTEGER NOT NULL DEFAULT 0,
                fumble_recoveries INTEGER NOT NULL DEFAULT 0,
                -- Kicking
                fg_attempts INTEGER NOT NULL DEFAULT 0,
                fg_made INTEGER NOT NULL DEFAULT 0,
                xp_attempts INTEGER NOT NULL DEFAULT 0,
                xp_made INTEGER NOT NULL DEFAULT 0,
                -- Punting
                punts INTEGER NOT NULL DEFAULT 0,
                punt_yards INTEGER NOT NULL DEFAULT 0,
                -- Defensive scoring
                defensive_touchdowns INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER NOT NULL,
                week INTEGER NOT NULL,
                division_id INTEGER NOT NULL REFERENCES divisions(id),
                home_team_id INTEGER NOT NULL REFERENCES teams(id),
                away_team_id INTEGER NOT NULL REFERENCES teams(id),
                game_id INTEGER REFERENCES games(id)
            );

            CREATE TABLE IF NOT EXISTS season_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_season INTEGER NOT NULL DEFAULT 1,
                current_week INTEGER NOT NULL DEFAULT 1,
                phase TEXT NOT NULL DEFAULT 'in_season',
                offseason_step TEXT,
                completed_season_team_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS practice_plan (
                team_id INTEGER NOT NULL REFERENCES teams(id),
                season INTEGER NOT NULL,
                week INTEGER NOT NULL,
                offense_focus TEXT NOT NULL DEFAULT 'balanced',
                defense_focus TEXT NOT NULL DEFAULT 'balanced',
                PRIMARY KEY (team_id, season, week)
            );

            CREATE TABLE IF NOT EXISTS player_development_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL REFERENCES players(id),
                season INTEGER NOT NULL,
                week INTEGER NOT NULL,
                attribute TEXT NOT NULL,
                change INTEGER NOT NULL
            );
        """)
        conn.commit()
        _migrate_season_state_offseason(conn)
        _migrate_managers_prestige_skill_points(conn)
    finally:
        if close:
            conn.close()


def _migrate_season_state_offseason(conn: sqlite3.Connection) -> None:
    """Add phase and offseason_step to season_state if missing (existing saves)."""
    try:
        rows = conn.execute("PRAGMA table_info(season_state)").fetchall()
        cols = {row[1] for row in rows}
        if "phase" not in cols:
            conn.execute(
                "ALTER TABLE season_state ADD COLUMN phase TEXT NOT NULL DEFAULT 'in_season'"
            )
        if "offseason_step" not in cols:
            conn.execute(
                "ALTER TABLE season_state ADD COLUMN offseason_step TEXT"
            )
        if "completed_season_team_id" not in cols:
            conn.execute(
                "ALTER TABLE season_state ADD COLUMN completed_season_team_id INTEGER"
            )
        conn.commit()
    except sqlite3.OperationalError:
        pass


def _migrate_managers_prestige_skill_points(conn: sqlite3.Connection) -> None:
    """Add prestige and unspent_skill_points to managers if missing (existing saves)."""
    try:
        rows = conn.execute("PRAGMA table_info(managers)").fetchall()
        cols = {row[1] for row in rows}
        if "prestige" not in cols:
            conn.execute(
                "ALTER TABLE managers ADD COLUMN prestige INTEGER NOT NULL DEFAULT 50"
            )
        if "unspent_skill_points" not in cols:
            conn.execute(
                "ALTER TABLE managers ADD COLUMN unspent_skill_points INTEGER NOT NULL DEFAULT 0"
            )
        conn.commit()
    except sqlite3.OperationalError:
        pass


def reset_for_new_manager() -> None:
    """
    Reset the save for a new manager: delete DB file and recreate schema.
    Call before inserting the new manager so the world is fresh.
    """
    path = get_db_path()
    if path.exists():
        path.unlink()
    _ensure_db_dir(path)
    conn = get_connection()
    try:
        init_db(conn)
    finally:
        conn.close()
