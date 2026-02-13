"""
GM Career Mode — Flask app.
Entry point for the web UI (character creation, etc.).
"""
import threading
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash

from models import Manager, MANAGER_SKILLS, STARTING_SKILL_POINTS
from models.ratings import compute_overall_at_position, compute_potential_at_position
from db import (
    reset_for_new_manager,
    get_connection,
    insert_manager,
    get_current_manager,
    get_high_school_divisions_with_teams_and_players,
    get_manager_current_team_id,
    set_manager_team,
    get_team_by_id,
    get_team_roster_with_depth,
    get_team_roster_full,
    get_depth_order,
    set_depth_order,
    update_player_position,
    recompute_player_ratings,
    depth_chart_is_valid,
    generate_depth_chart_best_by_position,
    set_setup_progress,
    get_setup_progress,
    # Season & schedule
    get_season_state,
    get_week_schedule,
    set_schedule_game_id,
    advance_week,
    enter_offseason,
    set_offseason_step,
    advance_offseason_step,
    OFFSEASON_STEPS,
    insert_game,
    get_division_standings,
    get_division_team_stat_leaders,
    get_team_schedule_display,
    get_division_for_team,
    get_season_summary,
    get_completed_season_team_id,
    run_season_rewards,
    spend_skill_points,
    get_player_stats_for_game,
    # Player / team profiles & stat leaders
    get_player_by_id,
    get_player_season_stats,
    get_player_prior_season_stats,
    get_division_stat_leaders,
    get_team_profile,
    # Practice and development
    get_practice_plan,
    set_practice_plan,
    copy_practice_plans_to_next_week,
    get_player_development_recent,
    get_team_player_development_totals,
    get_team_player_development_for_week,
    get_team_player_development_by_attribute_for_week,
    get_team_player_development_by_attribute_for_season,
    get_team_development_summary,
    search_players_database,
)
from generation import generate_all_teams_and_players
from simulation import (
    simulate_game,
    run_development_all_teams,
    run_freshmen_class,
    run_recruiting,
    run_draft,
    run_training_camps,
    run_offseason_development,
    run_offseason_complete,
)

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-production"

SKILL_KEYS = list(MANAGER_SKILLS.keys())

# Serialize sim_week so spam-clicking cannot run multiple sims concurrently (prevents week skips)
_sim_week_lock = threading.Lock()


@app.route("/")
def index() -> str:
    """Home: redirect to character creation for now."""
    return redirect(url_for("character_creation"))


@app.route("/create", methods=["GET"])
def character_creation() -> str:
    """Show character creation form (allocate manager skill points)."""
    values = {k: 0 for k in SKILL_KEYS}
    return render_template(
        "character_creation.html",
        skills=MANAGER_SKILLS,
        total_points=STARTING_SKILL_POINTS,
        values=values,
        name="",
        seed="",
    )


def _render_creation_error(
    error: str,
    name: str = "",
    values: dict | None = None,
    seed: str = "",
):
    allocation = values or {k: 0 for k in SKILL_KEYS}
    return render_template(
        "character_creation.html",
        skills=MANAGER_SKILLS,
        total_points=STARTING_SKILL_POINTS,
        error=error,
        values=allocation,
        name=name,
        seed=seed,
    ), 400


@app.route("/create", methods=["POST"])
def character_creation_submit():
    """Validate allocation, create manager in DB, start background generation, redirect to setup page."""
    raw = request.form
    name = (raw.get("name") or "").strip()
    seed_raw = (raw.get("seed") or "").strip()
    seed: int | str | None = seed_raw if seed_raw else None
    if seed is not None and seed_raw:
        try:
            seed = int(seed_raw)
        except ValueError:
            seed = seed_raw  # allow string seeds (hashed)

    allocation = {}
    for key in SKILL_KEYS:
        try:
            allocation[key] = int(raw.get(key, 0))
        except (TypeError, ValueError):
            allocation[key] = 0

    total = sum(allocation.values())
    if total != STARTING_SKILL_POINTS:
        return _render_creation_error(
            f"Total must be exactly {STARTING_SKILL_POINTS} points (you used {total}).",
            name=name,
            values=allocation,
            seed=seed_raw,
        )

    try:
        manager = Manager(name=name, **allocation)
    except ValueError as e:
        return _render_creation_error(str(e), name=name, values=allocation, seed=seed_raw)

    reset_for_new_manager()
    conn = get_connection()
    try:
        manager_id = insert_manager(conn, manager)
        set_setup_progress(conn, manager_id, "generating", 0.0, "Starting...")
    finally:
        conn.close()

    session["manager_id"] = manager_id
    session["manager"] = manager.to_dict()
    thread = threading.Thread(
        target=generate_all_teams_and_players,
        args=(manager_id,),
        kwargs={"seed": seed},
        daemon=True,
    )
    thread.start()
    return redirect(url_for("setup_in_progress"))


@app.route("/creating")
def setup_in_progress():
    """Show progress bar while league is being generated; JS polls /api/setup-status."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    return render_template("setup_in_progress.html")


@app.route("/api/setup-status")
def api_setup_status():
    """Return current generation progress (status, progress_pct, current_step)."""
    manager_id = session.get("manager_id")
    if manager_id is None:
        return jsonify({"error": "No manager"}), 404
    progress = get_setup_progress(manager_id)
    if progress is None:
        return jsonify({"status": "unknown", "progress_pct": 0, "current_step": ""})
    return jsonify(progress)


@app.route("/created")
def character_created():
    """Show confirmation after character creation; load manager from DB."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    conn = get_connection()
    try:
        manager = get_current_manager(conn)
    finally:
        conn.close()
    if manager is None:
        return redirect(url_for("character_creation"))
    return render_template(
        "character_created.html",
        manager=manager.to_dict(),
        skills=MANAGER_SKILLS,
    )


LEVEL_LABELS = {"high_school": "High School", "college": "College", "professional": "NFL"}


@app.route("/teams")
def team_selection():
    """Show divisions (HS only in-season; all levels during offseason) with teams and player lists."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    conn = get_connection()
    try:
        season_state = get_season_state(conn)
        offseason = season_state.get("phase") == "offseason"
        if offseason:
            from db.operations import get_all_divisions_with_teams_and_players
            divisions = get_all_divisions_with_teams_and_players(conn)
        else:
            divisions = get_high_school_divisions_with_teams_and_players(conn)
        current_team_id = get_manager_current_team_id(session["manager_id"], conn)
    finally:
        conn.close()
    regions = [{"id": d["id"], "name": d["name"], "level": d.get("level", "high_school")} for d in divisions]
    return render_template(
        "team_selection.html",
        divisions=divisions,
        regions=regions,
        current_team_id=current_team_id,
        offseason=offseason,
        level_labels=LEVEL_LABELS,
    )


@app.route("/teams/select", methods=["POST"])
def team_select():
    """Set the manager's current team and redirect to team selection."""
    manager_id = session.get("manager_id")
    if manager_id is None:
        return redirect(url_for("character_creation"))
    try:
        team_id = int(request.form.get("team_id", 0))
    except (TypeError, ValueError):
        return redirect(url_for("team_selection"))
    if team_id <= 0:
        return redirect(url_for("team_selection"))
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM teams WHERE id = ?", (team_id,)).fetchone()
        if row is None:
            return redirect(url_for("team_selection"))
        set_manager_team(conn, manager_id, team_id)
        season_state = get_season_state(conn)
        if season_state.get("phase") == "offseason":
            conn.close()
            return redirect(url_for("offseason_hub"))
    finally:
        conn.close()
    return redirect(url_for("manage_team"))


TOTAL_WEEKS = 18  # double round-robin for 10-team divisions


@app.route("/team")
def manage_team():
    """Manage team page: Season hub + Offense / Defense / Special Teams depth chart."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    current_team_id = get_manager_current_team_id(session["manager_id"])
    if current_team_id is None:
        return redirect(url_for("team_selection"))
    conn = get_connection()
    try:
        season_state = get_season_state(conn)
        if season_state.get("phase") == "offseason":
            conn.close()
            return redirect(url_for("offseason_hub"))
        team = get_team_by_id(current_team_id, conn)
        if team is None:
            return redirect(url_for("team_selection"))
        roster = get_team_roster_with_depth(current_team_id, conn)
        roster_full = get_team_roster_full(current_team_id, conn)

        from models.constants import (
            POSITIONS_OFFENSE,
            POSITIONS_DEFENSE,
            POSITIONS_SPECIAL_TEAMS as ST_POSITIONS,
            FORMATION_OFFENSE,
            FORMATION_DEFENSE,
            FORMATION_SPECIAL,
        )
        # Number of formation slots per position (e.g. WR=3, CB=2); positions with one slot default to 1
        formation_slot_count: dict[str, int] = {}
        for grid in (FORMATION_OFFENSE, FORMATION_DEFENSE, FORMATION_SPECIAL):
            for row in grid:
                for cell in row:
                    if cell:
                        formation_slot_count[cell] = formation_slot_count.get(cell, 0) + 1
        starter_ids = set()
        for pos in POSITIONS_OFFENSE + POSITIONS_DEFENSE + ST_POSITIONS:
            order = get_depth_order(current_team_id, pos, conn)
            if order:
                n_starters = formation_slot_count.get(pos, 1)
                for player_id in order[:n_starters]:
                    starter_ids.add(player_id)

        # ---- Season data ----
        season_state = get_season_state(conn)
        cur_season = season_state["current_season"]
        cur_week = season_state["current_week"]

        division = get_division_for_team(current_team_id, conn)
        division_id = division["id"] if division else 0
        division_name = division["name"] if division else ""

        standings = get_division_standings(division_id, cur_season, conn) if division_id else []
        division_team_stat_leaders = get_division_team_stat_leaders(division_id, cur_season, conn) if division_id else {}
        user_schedule = get_team_schedule_display(current_team_id, cur_season, conn)
        season_complete = cur_week > TOTAL_WEEKS

        # ---- Division stat leaders for season tab ----
        stat_leaders = get_division_stat_leaders(division_id, cur_season, conn) if division_id else {}

        # ---- Depth chart validity (for Sim button) ----
        depth_chart_valid, depth_chart_invalid_reason = depth_chart_is_valid(current_team_id, conn)

        # ---- Practice plan for current week (offense + defense focus) ----
        practice_plan = get_practice_plan(conn, current_team_id, cur_season, cur_week)
        had_plan_this_week = practice_plan is not None
        if practice_plan is None and cur_week > 1:
            # Carry over last week's selection so UI and next sim use it
            practice_plan = get_practice_plan(conn, current_team_id, cur_season, cur_week - 1)
        if practice_plan is None:
            practice_plan = {"offense_focus": "balanced", "defense_focus": "balanced"}
        else:
            # Normalize to lowercase so DB values match constants
            practice_plan = {
                "offense_focus": (practice_plan.get("offense_focus") or "balanced").strip().lower() or "balanced",
                "defense_focus": (practice_plan.get("defense_focus") or "balanced").strip().lower() or "balanced",
            }
        if not had_plan_this_week:
            set_practice_plan(conn, current_team_id, cur_season, cur_week, practice_plan["offense_focus"], practice_plan["defense_focus"])

        # ---- Development totals this season (for roster "improved" indicator) ----
        player_development_totals = get_team_player_development_totals(conn, current_team_id, cur_season)
        # Attribute-level development for Practice tab (last week + season)
        last_week_attr: dict[int, dict[str, int]] = {}
        if cur_week > 1:
            for pid, attr, total in get_team_player_development_by_attribute_for_week(
                conn, current_team_id, cur_season, cur_week - 1
            ):
                last_week_attr.setdefault(pid, {})[attr] = total
        season_attr: dict[int, dict[str, int]] = {}
        for pid, attr, total in get_team_player_development_by_attribute_for_season(
            conn, current_team_id, cur_season
        ):
            season_attr.setdefault(pid, {})[attr] = total
        practice_player_development_attributes: list[dict] = []
        for p in roster_full:
            pid = p["id"]
            lw = last_week_attr.get(pid, {})
            se = season_attr.get(pid, {})
            all_attrs = sorted(set(lw.keys()) | set(se.keys()))
            for attr in all_attrs:
                practice_player_development_attributes.append({
                    "player": p,
                    "attribute": attr,
                    "change_last_week": lw.get(attr, 0),
                    "change_season": se.get(attr, 0),
                })
        # Sort by player name then attribute for stable default view
        practice_player_development_attributes.sort(
            key=lambda r: (r["player"]["name"], r["attribute"])
        )
    finally:
        conn.close()
    from models.constants import (
        POSITIONS_OFFENSE,
        POSITIONS_DEFENSE,
        POSITIONS_SPECIAL_TEAMS,
        FORMATION_OFFENSE,
        FORMATION_DEFENSE,
        FORMATION_SPECIAL,
        FORMATION_DEFENSE_LABELS,
        CLASS_LABELS,
        POSITIONS,
        OFFENSE_PRACTICE_OPTIONS,
        DEFENSE_PRACTICE_OPTIONS,
    )

    def compute_position_fits_and_potentials(player: dict) -> tuple[dict, dict]:
        """Return (overall per position, potential per position) using models.ratings."""
        fits = {pos: compute_overall_at_position(player, pos) for pos in POSITIONS}
        potentials = {pos: compute_potential_at_position(player, pos) for pos in POSITIONS}
        return fits, potentials

    def by_position(players: list) -> dict:
        out = {}
        for p in players:
            out.setdefault(p["position"], []).append(p)
        return out
    roster_grouped = {
        "offense": by_position(roster["offense"]),
        "defense": by_position(roster["defense"]),
        "special_teams": by_position(roster["special_teams"]),
    }

    for p in roster_full:
        p["position_fits"], p["position_potentials"] = compute_position_fits_and_potentials(p)

    position_groups = {
        "offense": POSITIONS_OFFENSE,
        "defense": POSITIONS_DEFENSE,
        "special_teams": POSITIONS_SPECIAL_TEAMS,
    }

    def formation_with_slots(formation):
        """Convert formation grid of position names into (position, slot_index) per cell.
        Slot index is 1-based per position (e.g. WR1, WR2, WR3)."""
        slot_counter = {}
        result = []
        for row in formation:
            new_row = []
            for pos in row:
                if pos:
                    slot_counter[pos] = slot_counter.get(pos, 0) + 1
                    new_row.append((pos, slot_counter[pos]))
                else:
                    new_row.append(("", 0))
            result.append(new_row)
        return result

    formation_offense_slots = formation_with_slots(FORMATION_OFFENSE)
    formation_defense_slots = formation_with_slots(FORMATION_DEFENSE)
    formation_special_slots = formation_with_slots(FORMATION_SPECIAL)

    def positions_with_multiple_slots(slots_grid):
        """Return set of position names that appear in more than one slot."""
        slot_max = {}
        for row in slots_grid:
            for pos, idx in row:
                if pos:
                    slot_max[pos] = max(slot_max.get(pos, 0), idx)
        return {pos for pos, m in slot_max.items() if m > 1}

    offense_positions_multiple = positions_with_multiple_slots(formation_offense_slots)
    defense_positions_multiple = positions_with_multiple_slots(formation_defense_slots)
    special_positions_multiple = positions_with_multiple_slots(formation_special_slots)

    return render_template(
        "manage_team.html",
        team=team,
        roster_grouped=roster_grouped,
        roster_full=roster_full,
        starter_ids=starter_ids,
        position_groups=position_groups,
        formation_offense=FORMATION_OFFENSE,
        formation_defense=FORMATION_DEFENSE,
        formation_special=FORMATION_SPECIAL,
        formation_offense_slots=formation_offense_slots,
        formation_defense_slots=formation_defense_slots,
        formation_special_slots=formation_special_slots,
        offense_positions_multiple=offense_positions_multiple,
        defense_positions_multiple=defense_positions_multiple,
        special_positions_multiple=special_positions_multiple,
        formation_defense_labels=FORMATION_DEFENSE_LABELS,
        class_labels=CLASS_LABELS,
        all_positions=POSITIONS,
        # Season data
        season=cur_season,
        week=cur_week,
        total_weeks=TOTAL_WEEKS,
        division_name=division_name,
        standings=standings,
        division_team_stat_leaders=division_team_stat_leaders,
        user_schedule=user_schedule,
        season_complete=season_complete,
        current_team_id=current_team_id,
        stat_leaders=stat_leaders,
        depth_chart_valid=depth_chart_valid,
        depth_chart_invalid_reason=depth_chart_invalid_reason,
        practice_plan=practice_plan,
        practice_offense_options=OFFENSE_PRACTICE_OPTIONS,
        practice_defense_options=DEFENSE_PRACTICE_OPTIONS,
        practice_player_development_attributes=practice_player_development_attributes,
        player_development_totals=player_development_totals,
    )


@app.route("/team/practice", methods=["POST"])
def team_practice_set():
    """Set practice plan for the current week: offense focus and defense focus (each Offense/Defense or Balanced)."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    current_team_id = get_manager_current_team_id(session["manager_id"])
    if current_team_id is None:
        return redirect(url_for("team_selection"))
    from models.constants import OFFENSE_FOCUS_KEYS, DEFENSE_FOCUS_KEYS
    offense_focus = (request.form.get("offense_focus") or "").strip().lower()
    defense_focus = (request.form.get("defense_focus") or "").strip().lower()
    if offense_focus not in OFFENSE_FOCUS_KEYS:
        offense_focus = "balanced"
    if defense_focus not in DEFENSE_FOCUS_KEYS:
        defense_focus = "balanced"
    conn = get_connection()
    try:
        season_state = get_season_state(conn)
        set_practice_plan(
            conn,
            current_team_id,
            season_state["current_season"],
            season_state["current_week"],
            offense_focus,
            defense_focus,
        )
    finally:
        conn.close()
    return redirect(url_for("manage_team"))


@app.route("/team/depth-chart")
def depth_chart_edit():
    """Edit depth chart: reorder players by position (Offense / Defense / Special Teams)."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    current_team_id = get_manager_current_team_id(session["manager_id"])
    if current_team_id is None:
        return redirect(url_for("team_selection"))
    conn = get_connection()
    try:
        team = get_team_by_id(current_team_id, conn)
        if team is None:
            return redirect(url_for("team_selection"))
        roster = get_team_roster_with_depth(current_team_id, conn)
        # Build per-position lists for editing (position -> list of player dicts in current order)
        from models.constants import POSITIONS_OFFENSE, POSITIONS_DEFENSE, POSITIONS_SPECIAL_TEAMS
        all_positions = POSITIONS_OFFENSE + POSITIONS_DEFENSE + POSITIONS_SPECIAL_TEAMS
        position_players: dict[str, list] = {}
        for unit_name, players in roster.items():
            by_pos: dict[str, list] = {}
            for p in players:
                by_pos.setdefault(p["position"], []).append(p)
            for pos in (POSITIONS_OFFENSE if unit_name == "offense" else
                       POSITIONS_DEFENSE if unit_name == "defense" else POSITIONS_SPECIAL_TEAMS):
                position_players[pos] = by_pos.get(pos, [])
        position_groups_list = [
            ("offense", "Offense", POSITIONS_OFFENSE),
            ("defense", "Defense", POSITIONS_DEFENSE),
            ("special_teams", "Special Teams", POSITIONS_SPECIAL_TEAMS),
        ]
        # Flat list of all roster players (deduped by id) for "Add player" dropdowns
        seen_ids = set()
        all_players = []
        for unit_players in roster.values():
            for p in unit_players:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    all_players.append(p)
    finally:
        conn.close()
    return render_template(
        "depth_chart_edit.html",
        team=team,
        roster=roster,
        position_players=position_players,
        position_groups_list=position_groups_list,
        all_players=all_players,
    )


@app.route("/team/depth-chart/add-player", methods=["POST"])
def depth_chart_add_player():
    """Move a player to a position (e.g. from defense to offense). Updates position and depth chart."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    current_team_id = get_manager_current_team_id(session["manager_id"])
    if current_team_id is None:
        return redirect(url_for("team_selection"))
    try:
        player_id = int(request.form.get("player_id", 0))
        new_position = (request.form.get("position") or "").strip().upper()
    except (TypeError, ValueError):
        return redirect(url_for("depth_chart_edit"))
    from models.constants import POSITIONS_OFFENSE, POSITIONS_DEFENSE, POSITIONS_SPECIAL_TEAMS
    all_positions = POSITIONS_OFFENSE + POSITIONS_DEFENSE + POSITIONS_SPECIAL_TEAMS
    if new_position not in all_positions:
        return redirect(url_for("depth_chart_edit"))
    conn = get_connection()
    try:
        player = get_player_by_id(player_id, conn)
        if player is None or player["team_id"] != current_team_id:
            return redirect(url_for("depth_chart_edit"))
        old_position = player["position"]
        update_player_position(conn, player_id, new_position)
        recompute_player_ratings(conn, player_id, new_position)
        generate_depth_chart_best_by_position(current_team_id, conn)
    finally:
        conn.close()
    return redirect(url_for("depth_chart_edit"))


@app.route("/team/depth-chart/generate", methods=["POST"])
def depth_chart_generate():
    """Set depth chart to best (highest overall) player at each position as starter."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    current_team_id = get_manager_current_team_id(session["manager_id"])
    if current_team_id is None:
        return redirect(url_for("team_selection"))
    conn = get_connection()
    try:
        generate_depth_chart_best_by_position(current_team_id, conn)
    finally:
        conn.close()
    next_page = request.form.get("next") or request.args.get("next")
    if next_page == "manage_team":
        return redirect(url_for("manage_team"))
    return redirect(url_for("depth_chart_edit"))


@app.route("/api/team/depth-chart", methods=["POST"])
def api_depth_chart_save():
    """Save depth chart from JSON: { orders: { QB: [id, ...], RB: [...], ... } }. Updates player positions when moved."""
    if session.get("manager_id") is None:
        return jsonify({"error": "Not authenticated"}), 403
    current_team_id = get_manager_current_team_id(session["manager_id"])
    if current_team_id is None:
        return jsonify({"error": "No team"}), 400
    data = request.get_json()
    if not data or "orders" not in data:
        return jsonify({"error": "Missing orders"}), 400
    orders = data["orders"]
    conn = get_connection()
    try:
        # Get current positions for all players on team
        rows = conn.execute(
            "SELECT id, position FROM players WHERE team_id = ?",
            (current_team_id,),
        ).fetchall()
        current_pos = {r["id"]: r["position"] for r in rows}
        # Track (player_id, new_position) for players that moved so we can recompute overall
        position_changes: list[tuple[int, str]] = []
        # Update player position when they appear in a different position
        for position, player_ids in orders.items():
            if not isinstance(player_ids, list):
                continue
            for pid in player_ids:
                try:
                    pid = int(pid)
                except (TypeError, ValueError):
                    continue
                if pid in current_pos and current_pos[pid] != position:
                    update_player_position(conn, pid, position)
                    position_changes.append((pid, position))
                    current_pos[pid] = position
        for pid, new_position in position_changes:
            recompute_player_ratings(conn, pid, new_position)
        # Save depth order for each position (single transaction to reduce lock time)
        from models.constants import POSITIONS_OFFENSE, POSITIONS_DEFENSE, POSITIONS_SPECIAL_TEAMS
        all_positions = POSITIONS_OFFENSE + POSITIONS_DEFENSE + POSITIONS_SPECIAL_TEAMS
        for pos in all_positions:
            pids = orders.get(pos)
            if isinstance(pids, list):
                try:
                    player_ids = [int(x) for x in pids]
                except (TypeError, ValueError):
                    continue
                if player_ids:
                    set_depth_order(conn, current_team_id, pos, player_ids, commit=False)
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/team/depth-chart", methods=["POST"])
def depth_chart_save():
    """Save depth chart order from form (position -> ordered player_ids)."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    current_team_id = get_manager_current_team_id(session["manager_id"])
    if current_team_id is None:
        return redirect(url_for("team_selection"))
    conn = get_connection()
    try:
        from models.constants import POSITIONS_OFFENSE, POSITIONS_DEFENSE, POSITIONS_SPECIAL_TEAMS
        all_positions = POSITIONS_OFFENSE + POSITIONS_DEFENSE + POSITIONS_SPECIAL_TEAMS
        for pos in all_positions:
            key = f"order_{pos}"
            raw = request.form.getlist(key)
            if raw:
                try:
                    player_ids = [int(x) for x in raw if x.strip()]
                except ValueError:
                    continue
                if player_ids:
                    set_depth_order(conn, current_team_id, pos, player_ids)
    finally:
        conn.close()
    return redirect(url_for("manage_team"))


@app.route("/season/sim", methods=["POST"])
def sim_week():
    """Simulate the current week for ALL divisions, then advance the week."""
    manager_id = session.get("manager_id")
    if manager_id is None:
        return redirect(url_for("character_creation"))
    current_team_id = get_manager_current_team_id(manager_id)
    if current_team_id is None:
        return redirect(url_for("team_selection"))

    conn = get_connection()
    try:
        valid, _ = depth_chart_is_valid(current_team_id, conn)
        if not valid:
            return redirect(url_for("manage_team"))

        _sim_week_lock.acquire()
        try:
            season_state = get_season_state(conn)
            cur_season = season_state["current_season"]
            cur_week = season_state["current_week"]

            if cur_week > TOTAL_WEEKS:
                return redirect(url_for("manage_team"))

            # Get manager's in-game management for bonus
            manager = get_current_manager(conn)
            mgr_in_game = manager.in_game_management if manager else 0

            # Fetch all scheduled matchups for this week (every division)
            week_rows = get_week_schedule(conn, cur_season, cur_week)

            for row in week_rows:
                if row["game_id"] is not None:
                    continue  # already simulated (safety check)

                result = simulate_game(
                    row["home_team_id"],
                    row["away_team_id"],
                    conn,
                    manager_team_id=current_team_id,
                    manager_in_game=mgr_in_game,
                )

                game_id = insert_game(conn, result, season=cur_season, week=cur_week)
                set_schedule_game_id(conn, row["id"], game_id)

            # Run development for all teams (practice plan or balanced default)
            dev_results = run_development_all_teams(conn, cur_season, cur_week)
            team_summary = dev_results.get(current_team_id, [])
            num_improved = len(team_summary)
            total_gain = sum(s["total_gain"] for s in team_summary)
            if num_improved > 0:
                flash(
                    f"Development: {num_improved} players gained attributes this week (total +{total_gain} across attributes)."
                )

            # Copy each team's practice plan to next week so selection carries over
            copy_practice_plans_to_next_week(conn, cur_season, cur_week)

            conn.commit()
            if cur_week == TOTAL_WEEKS:
                # Season complete: enter offseason instead of advancing week
                enter_offseason(conn, completed_team_id=current_team_id)
                return redirect(url_for("offseason_hub"))
            advance_week(conn)
        finally:
            _sim_week_lock.release()
    finally:
        conn.close()

    return redirect(url_for("manage_team"))


@app.route("/season/sim-all", methods=["POST"])
def sim_season():
    """Simulate all remaining weeks in the season (current week through week 18)."""
    manager_id = session.get("manager_id")
    if manager_id is None:
        return redirect(url_for("character_creation"))
    current_team_id = get_manager_current_team_id(manager_id)
    if current_team_id is None:
        return redirect(url_for("team_selection"))

    conn = get_connection()
    try:
        valid, _ = depth_chart_is_valid(current_team_id, conn)
        if not valid:
            return redirect(url_for("manage_team"))

        _sim_week_lock.acquire()
        try:
            season_state = get_season_state(conn)
            cur_season = season_state["current_season"]
            cur_week = season_state["current_week"]

            if cur_week > TOTAL_WEEKS:
                conn.close()
                return redirect(url_for("manage_team"))

            manager = get_current_manager(conn)
            mgr_in_game = manager.in_game_management if manager else 0
            weeks_simmed = 0

            while cur_week <= TOTAL_WEEKS:
                week_rows = get_week_schedule(conn, cur_season, cur_week)
                for row in week_rows:
                    if row["game_id"] is not None:
                        continue
                    result = simulate_game(
                        row["home_team_id"],
                        row["away_team_id"],
                        conn,
                        manager_team_id=current_team_id,
                        manager_in_game=mgr_in_game,
                    )
                    game_id = insert_game(conn, result, season=cur_season, week=cur_week)
                    set_schedule_game_id(conn, row["id"], game_id)

                run_development_all_teams(conn, cur_season, cur_week)
                copy_practice_plans_to_next_week(conn, cur_season, cur_week)
                conn.commit()

                weeks_simmed += 1
                if cur_week == TOTAL_WEEKS:
                    enter_offseason(conn, completed_team_id=current_team_id)
                    flash(f"Season complete. Simulated {weeks_simmed} week(s). Entering offseason.")
                    conn.close()
                    return redirect(url_for("offseason_hub"))
                advance_week(conn)
                season_state = get_season_state(conn)
                cur_week = season_state["current_week"]

            flash(f"Simulated {weeks_simmed} week(s).")
        finally:
            _sim_week_lock.release()
    finally:
        conn.close()
    return redirect(url_for("manage_team"))


# ---------------------------------------------------------------------------
# Offseason hub
# ---------------------------------------------------------------------------

OFFSEASON_STEP_LABELS = {
    "season_summary": "Season summary",
    "team_change": "Change teams",
    "skill_points": "Spend skill points",
    "freshmen": "Incoming freshmen",
    "recruiting": "Recruiting (HS → College)",
    "draft": "NFL Draft (College → Pro)",
    "training_camp": "Training camps (HS)",
    "development": "Offseason development",
    "complete": "Start new season",
}


@app.route("/offseason")
def offseason_hub():
    """Offseason hub: current step, change team link, continue button."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    current_team_id = get_manager_current_team_id(session["manager_id"])
    if current_team_id is None:
        return redirect(url_for("team_selection"))
    conn = get_connection()
    try:
        season_state = get_season_state(conn)
        if season_state.get("phase") != "offseason":
            return redirect(url_for("manage_team"))
        step = season_state.get("offseason_step") or OFFSEASON_STEPS[0]
        step_index = list(OFFSEASON_STEPS).index(step) if step in OFFSEASON_STEPS else 0
        team = get_team_by_id(current_team_id, conn)
        division = get_division_for_team(current_team_id, conn) if team else None
        level = division.get("level") if division else ""
        can_change_team = step == "team_change"
        step_label = OFFSEASON_STEP_LABELS.get(step, step)
        offseason_display_result = session.pop("offseason_display_result", None)
        training_camp_plan = None
        if step == "training_camp" and level == "high_school":
            training_camp_plan = get_practice_plan(conn, current_team_id, season_state["current_season"], 0)
            if training_camp_plan is None:
                training_camp_plan = {"offense_focus": "balanced", "defense_focus": "balanced"}
        season_summary = None
        if step == "season_summary":
            summary_team_id = get_completed_season_team_id(conn) or current_team_id
            season_summary = get_season_summary(conn, summary_team_id, season_state["current_season"]) if summary_team_id else None
        manager_for_skills = None
        skill_current_values = {}
        if step == "skill_points":
            manager_for_skills = get_current_manager(conn)
            if manager_for_skills:
                skill_current_values = {k: getattr(manager_for_skills, k, 0) for k in SKILL_KEYS}
        from models.constants import OFFENSE_PRACTICE_OPTIONS, DEFENSE_PRACTICE_OPTIONS
    finally:
        conn.close()
    new_players_my_team = []
    new_players_other = []
    if offseason_display_result and offseason_display_result.get("step") == "freshmen":
        all_new = offseason_display_result.get("new_players") or []
        try:
            my_team_id = int(current_team_id) if current_team_id is not None else None
        except (TypeError, ValueError):
            my_team_id = None
        for p in all_new:
            try:
                pid = int(p.get("team_id")) if p.get("team_id") is not None else None
            except (TypeError, ValueError):
                pid = None
            if pid == my_team_id:
                new_players_my_team.append(p)
            else:
                new_players_other.append(p)
        new_players_other = new_players_other[:40]

    return render_template(
        "offseason.html",
        season=season_state["current_season"],
        step=step,
        step_label=step_label,
        step_index=step_index,
        total_steps=len(OFFSEASON_STEPS),
        team=team,
        division=division,
        level=level,
        can_change_team=can_change_team,
        training_camp_plan=training_camp_plan,
        offense_practice_options=OFFENSE_PRACTICE_OPTIONS if step == "training_camp" and level == "high_school" else (),
        defense_practice_options=DEFENSE_PRACTICE_OPTIONS if step == "training_camp" and level == "high_school" else (),
        offseason_display_result=offseason_display_result,
        new_players_my_team=new_players_my_team,
        new_players_other=new_players_other,
        season_summary=season_summary,
        manager_for_skills=manager_for_skills,
        manager_skills=MANAGER_SKILLS if step == "skill_points" else {},
        skill_current_values=skill_current_values,
    )


@app.route("/offseason/continue", methods=["POST"])
def offseason_continue():
    """Process current offseason step and advance (or complete and go to new season)."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    current_team_id = get_manager_current_team_id(session["manager_id"])
    if current_team_id is None:
        return redirect(url_for("team_selection"))
    conn = get_connection()
    try:
        season_state = get_season_state(conn)
        if season_state.get("phase") != "offseason":
            conn.close()
            return redirect(url_for("manage_team"))
        step = season_state.get("offseason_step")
        season = season_state["current_season"]
        manager_id = session.get("manager_id")

        if step == "season_summary":
            advance_offseason_step(conn)
            flash("Continue to offseason.")
        elif step == "team_change":
            advance_offseason_step(conn)
            next_step = get_season_state(conn).get("offseason_step")
            if next_step == "skill_points" and manager_id is not None:
                run_season_rewards(conn, manager_id, season)
                flash("Skill points and prestige have been updated. Spend your earned points below.")
            else:
                flash("You can change your team above, then continue when ready.")
        elif step == "skill_points":
            skill_deltas = {}
            for key in SKILL_KEYS:
                try:
                    val = request.form.get(f"skill_{key}", "0").strip()
                    skill_deltas[key] = max(0, int(val)) if val else 0
                except (ValueError, TypeError):
                    skill_deltas[key] = 0
            success, msg = spend_skill_points(conn, manager_id, skill_deltas)
            if success:
                flash(msg if msg != "No changes." else "Continue when ready.")
                advance_offseason_step(conn)
            else:
                flash(msg, "error")
        elif step == "freshmen":
            result = run_freshmen_class(conn, season)
            session["offseason_display_result"] = {
                "step": "freshmen",
                "players_added": result["players_added"],
                "teams": result["teams"],
                "new_players": result.get("new_players", []),
            }
            flash(f"Incoming freshmen: {result['players_added']} new players added across {result['teams']} high schools.")
            advance_offseason_step(conn)
        elif step == "recruiting":
            result = run_recruiting(conn, season)
            msg = f"Recruiting: {result['recruited']} HS seniors signed with colleges; {result['retired']} retired."
            if result.get("walk_ons_added", 0) > 0:
                msg += f" {result['walk_ons_added']} walk-ons added to fill rosters."
            flash(msg)
            advance_offseason_step(conn)
        elif step == "draft":
            result = run_draft(conn, season)
            msg = f"NFL Draft: {result['drafted']} college seniors drafted; {result['retired']} retired."
            if result.get("walk_ons_added", 0) > 0:
                msg += f" {result['walk_ons_added']} walk-ons added to fill college rosters."
            flash(msg)
            advance_offseason_step(conn)
        elif step == "training_camp":
            from models.constants import OFFENSE_FOCUS_KEYS, DEFENSE_FOCUS_KEYS
            offense_focus = (request.form.get("offense_focus") or "").strip().lower()
            defense_focus = (request.form.get("defense_focus") or "").strip().lower()
            if offense_focus not in OFFENSE_FOCUS_KEYS:
                offense_focus = "balanced"
            if defense_focus not in DEFENSE_FOCUS_KEYS:
                defense_focus = "balanced"
            set_practice_plan(conn, current_team_id, season, 0, offense_focus, defense_focus)
            result = run_training_camps(conn, season)
            flash(f"Training camps: {result['teams']} HS teams; total +{result['total_gain']} attribute gains.")
            advance_offseason_step(conn)
        elif step == "development":
            result = run_offseason_development(conn, season)
            flash(f"Offseason development: {result['teams']} teams; total +{result['total_gain']} attribute gains.")
            advance_offseason_step(conn)
        elif step == "complete":
            result = run_offseason_complete(conn)
            flash(f"Season {result['new_season']} is here! Good luck.")
            conn.close()
            return redirect(url_for("manage_team"))
        else:
            flash("Unknown offseason step.")
    finally:
        conn.close()
    return redirect(url_for("offseason_hub"))


@app.route("/game/<int:game_id>")
def game_result_view(game_id: int):
    """Show box score for a completed game."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    conn = get_connection()
    try:
        from db.operations import get_game_by_id as _get_game
        game = _get_game(game_id, conn)
        if game is None:
            return redirect(url_for("manage_team"))
        home_team = get_team_by_id(game["home_team_id"], conn) or {}
        away_team = get_team_by_id(game["away_team_id"], conn) or {}
        home_stats = get_player_stats_for_game(game_id, team_id=game["home_team_id"], conn=conn)
        away_stats = get_player_stats_for_game(game_id, team_id=game["away_team_id"], conn=conn)
    finally:
        conn.close()
    return render_template(
        "game_result.html",
        game=game,
        home_team=home_team,
        away_team=away_team,
        home_stats=home_stats,
        away_stats=away_stats,
    )


# ---------------------------------------------------------------------------
# Player profile API
# ---------------------------------------------------------------------------

@app.route("/api/player/<int:player_id>")
def api_player_profile(player_id: int):
    """Return full player profile + season stats as JSON."""
    if session.get("manager_id") is None:
        return jsonify({"error": "Not authenticated"}), 403
    conn = get_connection()
    try:
        player = get_player_by_id(player_id, conn)
        if player is None:
            return jsonify({"error": "Player not found"}), 404
        season_state = get_season_state(conn)
        current_season = season_state["current_season"]
        season_stats = get_player_season_stats(player_id, current_season, conn)
        prior_season_stats = get_player_prior_season_stats(player_id, current_season, conn)
    finally:
        conn.close()
    from models.constants import CLASS_LABELS
    player["class_label"] = CLASS_LABELS.get(player.get("class_year"), str(player.get("class_year", "")))
    return jsonify({"player": player, "season_stats": season_stats, "prior_season_stats": prior_season_stats})


@app.route("/api/player/<int:player_id>/position-fit")
def api_player_position_fit(player_id: int):
    """Return projected OVR at every position for a player (radar/star chart data)."""
    if session.get("manager_id") is None:
        return jsonify({"error": "Not authenticated"}), 403
    conn = get_connection()
    try:
        player = get_player_by_id(player_id, conn)
        if player is None:
            return jsonify({"error": "Player not found"}), 404
    finally:
        conn.close()
    from models.constants import POSITIONS

    fits = {pos: compute_overall_at_position(player, pos) for pos in POSITIONS}
    potentials = {pos: compute_potential_at_position(player, pos) for pos in POSITIONS}

    current_pos = player["position"]
    current_ovr = player["overall"]

    # Key attributes for radar chart
    attrs = {
        "speed": player.get("speed", 0),
        "acceleration": player.get("acceleration", 0),
        "lateral_quickness": player.get("lateral_quickness", 0),
        "vision": player.get("vision", 0),
        "lower_body_strength": player.get("lower_body_strength", 0),
        "upper_body_strength": player.get("upper_body_strength", 0),
        "arm_length": player.get("arm_length", 32),
        "vertical_jump": player.get("vertical_jump", 50),
        "broad_jump": player.get("broad_jump", 50),
        "arm_strength": player.get("arm_strength", 0),
        "kick_power": player.get("kick_power", 0),
        "run_block": player.get("run_block", 0),
        "pass_rush": player.get("pass_rush", 0),
        "pass_protection": player.get("pass_protection", 0),
        "scrambling": player.get("scrambling", 0),
        "short_accuracy": player.get("short_accuracy", 50),
        "mid_accuracy": player.get("mid_accuracy", 50),
        "deep_accuracy": player.get("deep_accuracy", 50),
        "throw_under_pressure": player.get("throw_under_pressure", 50),
        "ball_security": player.get("ball_security", 50),
        "catching": player.get("catching", 50),
        "route_running": player.get("route_running", 50),
        "tackling": player.get("tackling", 50),
        "coverage": player.get("coverage", 50),
        "block_shedding": player.get("block_shedding", 50),
        "pursuit": player.get("pursuit", 50),
        "kick_accuracy": player.get("kick_accuracy", 50),
    }
    return jsonify({
        "player_id": player_id,
        "current_position": current_pos,
        "current_overall": current_ovr,
        "position_fits": fits,
        "position_potentials": potentials,
        "attributes": attrs,
    })


@app.route("/api/player/<int:player_id>/development")
def api_player_development(player_id: int):
    """Return development data: key attributes (current vs cap) and recent changes."""
    if session.get("manager_id") is None:
        return jsonify({"error": "Not authenticated"}), 403
    conn = get_connection()
    try:
        player = get_player_by_id(player_id, conn)
        if player is None:
            return jsonify({"error": "Player not found"}), 404
        season_state = get_season_state(conn)
        cur_season = season_state["current_season"]
        cur_week = season_state["current_week"]
        position = player.get("position", "")
        from models.constants import POSITION_POTENTIAL_WEIGHTS
        weights = POSITION_POTENTIAL_WEIGHTS.get(position, {})
        # Top 6 attributes by weight for this position (skip arm_length for display)
        key_attrs = sorted(
            [a for a in weights.keys() if a != "arm_length"],
            key=lambda a: weights.get(a, 0),
            reverse=True,
        )[:6]
        key_attributes = []
        for attr in key_attrs:
            current = player.get(attr, 50)
            cap = player.get(f"{attr}_cap", 50)
            key_attributes.append({"attribute": attr, "current": current, "cap": cap})
        recent_changes = get_player_development_recent(conn, player_id, cur_season, cur_week, weeks_back=8)
    finally:
        conn.close()
    return jsonify({
        "player_id": player_id,
        "key_attributes": key_attributes,
        "recent_changes": recent_changes,
    })


@app.route("/api/player/<int:player_id>/position", methods=["POST"])
def api_player_set_position(player_id: int):
    """Set a player's position (e.g. move CB to WR). Player must be on manager's team."""
    if session.get("manager_id") is None:
        return jsonify({"error": "Not authenticated"}), 403
    current_team_id = get_manager_current_team_id(session["manager_id"])
    if current_team_id is None:
        return jsonify({"error": "No team"}), 400
    data = request.get_json()
    if not data or "position" not in data:
        return jsonify({"error": "Missing position"}), 400
    new_position = (data.get("position") or "").strip().upper()
    from models.constants import POSITIONS
    if new_position not in POSITIONS:
        return jsonify({"error": "Invalid position"}), 400
    conn = get_connection()
    try:
        player = get_player_by_id(player_id, conn)
        if player is None:
            return jsonify({"error": "Player not found"}), 404
        if player["team_id"] != current_team_id:
            return jsonify({"error": "Player not on your team"}), 403
        old_position = player["position"]
        update_player_position(conn, player_id, new_position)
        recompute_player_ratings(conn, player_id, new_position)
        generate_depth_chart_best_by_position(current_team_id, conn)
    finally:
        conn.close()
    return jsonify({"ok": True, "position": new_position})


# ---------------------------------------------------------------------------
# Team profile API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Player Database (search all levels)
# ---------------------------------------------------------------------------

@app.route("/player-database")
def player_database():
    """Player Database page: search/filter all players at every level (non-retired)."""
    if session.get("manager_id") is None:
        return redirect(url_for("character_creation"))
    from models.constants import POSITIONS, CLASS_LABELS
    from models.constants import TRAINABLE_ATTRIBUTES
    # Attribute list for filter dropdown (friendly names)
    attr_display = [
        "speed", "acceleration", "overall", "potential", "age",
        "lateral_quickness", "vision", "lower_body_strength", "upper_body_strength",
        "arm_strength", "run_block", "pass_rush", "pass_protection", "scrambling",
        "short_accuracy", "mid_accuracy", "deep_accuracy", "catching", "route_running",
        "tackling", "coverage", "block_shedding", "pursuit", "kick_power", "kick_accuracy",
        "height", "weight", "class_year",
    ]
    return render_template(
        "player_database.html",
        level_labels=LEVEL_LABELS,
        positions=POSITIONS,
        class_labels=CLASS_LABELS,
        attribute_options=attr_display,
    )


@app.route("/api/player-database/search", methods=["GET", "POST"])
def api_player_database_search():
    """Search players with AND/OR conditions. POST JSON: { \"conditions\": [ ... ], \"connectives\": [ \"and\"|\"or\", ... ] }."""
    if session.get("manager_id") is None:
        return jsonify({"error": "Not authenticated"}), 403
    conditions = []
    connectives = None
    if request.method == "POST" and request.get_json():
        data = request.get_json()
        conditions = data.get("conditions") or []
        connectives = data.get("connectives")
    conn = get_connection()
    try:
        players = search_players_database(conn, conditions, connectives=connectives)
    finally:
        conn.close()
    from models.constants import CLASS_LABELS
    for p in players:
        p["class_label"] = CLASS_LABELS.get(p.get("class_year"), str(p.get("class_year", "")))
    return jsonify({"players": players})


@app.route("/api/team/<int:team_id>/profile")
def api_team_profile(team_id: int):
    """Return team profile data as JSON."""
    if session.get("manager_id") is None:
        return jsonify({"error": "Not authenticated"}), 403
    conn = get_connection()
    try:
        season_state = get_season_state(conn)
        profile = get_team_profile(team_id, season_state["current_season"], conn)
    finally:
        conn.close()
    if profile is None:
        return jsonify({"error": "Team not found"}), 404
    from models.constants import CLASS_LABELS
    for p in profile["top_players"]:
        p["class_label"] = CLASS_LABELS.get(p.get("class_year"), str(p.get("class_year", "")))
    return jsonify(profile)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
