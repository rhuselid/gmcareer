"""
Game simulation engine for GM Career Mode.

Simulates a full football game between two teams, producing non-deterministic
but realistic individual player statistics.  Key design goals:

1. **Attribute-driven**: Player stats (speed, run_block, pass_rush, etc.) and
   team composition directly influence outcomes.  Per the README, rushing yards
   are ~1/3 RB ability + 2/3 OL run-blocking, multiplied by randomness.
2. **Internally consistent**: Aggregate team stats equal the sum of individual
   player stats (e.g. total passing yards == sum of receiving yards).
3. **Non-deterministic**: Uses a seeded RNG so games are reproducible when
   desired, but every game is different.
4. **Manager influence**: The human player's ``in_game_management`` skill
   provides a small rating bonus to their team.
"""
from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from db.operations import get_team_roster_with_depth, get_team_by_id
from models.game_result import PlayerGameStats, TeamGameResult, GameResult

# ---------------------------------------------------------------------------
# Formation constants — how many starters per position
# ---------------------------------------------------------------------------
STARTERS_COUNT: dict[str, int] = {
    # Offense (11)
    "QB": 1, "RB": 1, "WR": 3, "TE": 1,
    "LT": 1, "LG": 1, "C": 1, "RG": 1, "RT": 1,
    # Defense (11)
    "DE": 2, "DT": 1, "NT": 1, "OLB": 2, "ILB": 1, "CB": 2, "S": 2,
    # Special teams
    "K": 1, "P": 1,
}

OL_POSITIONS = ("LT", "LG", "C", "RG", "RT")
DL_POSITIONS = ("DE", "DT", "NT")
LB_POSITIONS = ("OLB", "ILB")
DB_POSITIONS = ("CB", "S")

# Defensive stat distribution weights — position × attribute importance
TACKLE_WEIGHTS: dict[str, float] = {
    "ILB": 9.0, "OLB": 7.0, "S": 5.5, "CB": 4.0,
    "DE": 4.0, "DT": 3.5, "NT": 3.0,
}
SACK_WEIGHTS: dict[str, float] = {
    "DE": 5.0, "OLB": 3.5, "DT": 2.5, "NT": 1.5,
    "ILB": 0.5, "S": 0.3, "CB": 0.2,
}
INT_WEIGHTS: dict[str, float] = {
    "CB": 5.0, "S": 4.0, "OLB": 1.0, "ILB": 1.0,
    "DE": 0.1, "DT": 0.0, "NT": 0.0,
}
PD_WEIGHTS: dict[str, float] = {
    "CB": 5.0, "S": 3.5, "OLB": 1.5, "ILB": 1.0,
    "DE": 0.5, "DT": 0.2, "NT": 0.1,
}
TFL_WEIGHTS: dict[str, float] = {
    "DE": 4.0, "DT": 3.5, "NT": 3.0, "OLB": 3.0,
    "ILB": 2.5, "S": 1.0, "CB": 0.5,
}
FF_WEIGHTS: dict[str, float] = {
    "DE": 4.0, "OLB": 3.0, "DT": 2.0, "NT": 1.5,
    "ILB": 1.5, "S": 1.0, "CB": 0.5,
}


# ===================================================================
# Helper utilities
# ===================================================================

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe_mean(values: list[float], default: float = 30.0) -> float:
    return sum(values) / len(values) if values else default


def _weighted_partition(
    total: int,
    weights: list[float],
    rng: random.Random,
    noise: float = 0.04,
) -> list[int]:
    """Split *total* into ``len(weights)`` non-negative ints that sum to
    *total*, roughly proportional to *weights* with small Gaussian noise.

    The noise parameter controls how much randomness is injected (0 = exact
    proportional split, 0.04 = slight game-to-game variance).
    """
    n = len(weights)
    if n == 0:
        return []
    if total <= 0:
        return [0] * n

    w_sum = sum(weights)
    if w_sum <= 0:
        weights = [1.0] * n
        w_sum = float(n)

    # Normalise and inject noise
    noisy = [max(0.001, w / w_sum + rng.gauss(0, noise)) for w in weights]
    n_sum = sum(noisy)

    # Proportional allocation (floating)
    raw = [total * (nw / n_sum) for nw in noisy]
    result = [max(0, int(r)) for r in raw]

    # Distribute rounding remainder to the highest-weighted slots
    remainder = total - sum(result)
    if remainder != 0:
        indices = sorted(range(n), key=lambda i: noisy[i], reverse=True)
        step = 1 if remainder > 0 else -1
        for i in range(abs(remainder)):
            idx = indices[i % n]
            result[idx] = max(0, result[idx] + step)

    # Final safety: force exact sum
    diff = total - sum(result)
    if diff != 0:
        idx = max(range(n), key=lambda i: result[i])
        result[idx] = max(0, result[idx] + diff)

    return result


# ===================================================================
# Roster extraction
# ===================================================================

def _extract_position_groups(
    team_id: int,
    conn: sqlite3.Connection,
) -> dict[str, list[dict[str, Any]]]:
    """Return all players for *team_id* grouped by position.

    Players within each position are ordered by depth-chart rank (if set)
    then by overall rating.  The first player in each list is the starter.
    ``team_id`` is injected into every player dict for convenience.
    """
    roster = get_team_roster_with_depth(team_id, conn)
    by_pos: dict[str, list[dict[str, Any]]] = {}
    seen_ids: set[int] = set()
    for unit_players in roster.values():
        for p in unit_players:
            pid = p["id"]
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            p_copy = dict(p)
            p_copy["team_id"] = team_id
            by_pos.setdefault(p_copy["position"], []).append(p_copy)
    return by_pos


def _starters(
    pos_group: dict[str, list[dict]],
    position: str,
    n: int | None = None,
) -> list[dict]:
    """Return the top-*n* players at *position* (defaults to formation count)."""
    if n is None:
        n = STARTERS_COUNT.get(position, 1)
    return pos_group.get(position, [])[:n]


# ===================================================================
# Unit ratings — aggregate one team's strengths into simple numbers
# ===================================================================

@dataclass
class UnitRatings:
    """Condensed strength ratings for one team (all 0-99 scale)."""

    # Offense
    ol_run_block: float = 30.0
    ol_pass_protect: float = 30.0
    qb_passing: float = 30.0
    qb_mobility: float = 30.0
    rb_rushing: float = 30.0
    receiving_corps: float = 30.0
    # Defense
    dl_pass_rush: float = 30.0
    dl_run_stop: float = 30.0
    lb_rating: float = 30.0
    secondary_rating: float = 30.0
    # Special teams
    kick_power: float = 30.0
    punt_power: float = 30.0


def _compute_ratings(
    pos_group: dict[str, list[dict]],
    bonus: float = 0.0,
) -> UnitRatings:
    """Derive unit ratings from a team's position-grouped roster.

    *bonus* is a small additive boost (from manager skill / home field).
    """
    r = UnitRatings()

    # --- Offensive line ---
    ol = []
    for pos in OL_POSITIONS:
        ol.extend(_starters(pos_group, pos, 1))
    r.ol_run_block = _clamp(_safe_mean([p.get("run_block", 30) for p in ol]) + bonus, 0, 99)
    r.ol_pass_protect = _clamp(_safe_mean([p.get("pass_protection", 30) for p in ol]) + bonus, 0, 99)

    # --- Quarterback ---
    qbs = _starters(pos_group, "QB", 1)
    if qbs:
        qb = qbs[0]
        r.qb_passing = _clamp(
            0.18 * qb.get("arm_strength", 30)
            + 0.14 * qb.get("vision", 30)
            + 0.14 * (qb.get("short_accuracy", 50) + qb.get("mid_accuracy", 50)) / 2
            + 0.12 * qb.get("deep_accuracy", 50)
            + 0.12 * qb.get("throw_under_pressure", 50)
            + 0.10 * qb.get("speed", 30)
            + 0.10 * qb.get("acceleration", 30)
            + bonus, 0, 99,
        )
        r.qb_mobility = _clamp(
            0.30 * qb.get("scrambling", 30)
            + 0.30 * qb.get("speed", 30)
            + 0.20 * qb.get("acceleration", 30)
            + 0.20 * qb.get("lateral_quickness", 30),
            0, 99,
        )

    # --- Running back (primary) ---
    rbs = _starters(pos_group, "RB", 1)
    if rbs:
        rb = rbs[0]
        r.rb_rushing = _clamp(
            0.20 * rb.get("speed", 30)
            + 0.20 * rb.get("acceleration", 30)
            + 0.14 * rb.get("lateral_quickness", 30)
            + 0.12 * rb.get("broad_jump", 50)
            + 0.12 * rb.get("vision", 30)
            + 0.10 * rb.get("ball_security", 50)
            + 0.12 * rb.get("lower_body_strength", 30)
            + bonus, 0, 99,
        )

    # --- Receiving corps ---
    receivers = _starters(pos_group, "WR", 3) + _starters(pos_group, "TE", 1)
    r.receiving_corps = _clamp(
        _safe_mean([
            0.30 * p.get("catching", 50)
            + 0.25 * p.get("route_running", 50)
            + 0.20 * p.get("speed", 30)
            + 0.15 * p.get("lateral_quickness", 30)
            + 0.10 * p.get("vision", 30)
            for p in receivers
        ]) + bonus, 0, 99,
    )

    # --- Defensive line ---
    dl = []
    for pos in DL_POSITIONS:
        dl.extend(_starters(pos_group, pos))
    r.dl_pass_rush = _clamp(
        _safe_mean([
            0.70 * p.get("pass_rush", 30) + 0.30 * p.get("block_shedding", 50)
            for p in dl
        ]) + bonus, 0, 99,
    )
    r.dl_run_stop = _clamp(
        _safe_mean([
            0.30 * p.get("lower_body_strength", 30)
            + 0.25 * p.get("upper_body_strength", 30)
            + 0.20 * p.get("block_shedding", 50)
            + 0.15 * p.get("tackling", 50)
            + 0.10 * p.get("pursuit", 50)
            for p in dl
        ]) + bonus, 0, 99,
    )

    # --- Linebackers ---
    lbs = []
    for pos in LB_POSITIONS:
        lbs.extend(_starters(pos_group, pos))
    r.lb_rating = _clamp(
        _safe_mean([
            0.25 * p.get("tackling", 50)
            + 0.22 * p.get("pursuit", 50)
            + 0.18 * p.get("speed", 30)
            + 0.18 * p.get("lateral_quickness", 30)
            + 0.17 * p.get("block_shedding", 50)
            + 0.10 * p.get("vision", 30)
            for p in lbs
        ]) + bonus, 0, 99,
    )

    # --- Secondary ---
    dbs = []
    for pos in DB_POSITIONS:
        dbs.extend(_starters(pos_group, pos))
    r.secondary_rating = _clamp(
        _safe_mean([
            0.30 * p.get("coverage", 50)
            + 0.22 * p.get("tackling", 50)
            + 0.22 * p.get("speed", 30)
            + 0.16 * p.get("lateral_quickness", 30)
            + 0.10 * p.get("vision", 30)
            for p in dbs
        ]) + bonus, 0, 99,
    )

    # --- Special teams ---
    kickers = _starters(pos_group, "K", 1)
    if kickers:
        k = kickers[0]
        r.kick_power = _clamp(
            0.55 * k.get("kick_power", 30) + 0.45 * k.get("kick_accuracy", 50),
            0, 99,
        )
    else:
        r.kick_power = 30.0
    punters = _starters(pos_group, "P", 1)
    if punters:
        p = punters[0]
        r.punt_power = _clamp(
            0.60 * p.get("kick_power", 30) + 0.40 * p.get("kick_accuracy", 50),
            0, 99,
        )
    else:
        r.punt_power = 30.0

    return r


# ===================================================================
# Stat-line merging helper
# ===================================================================

_ADDITIVE_INT_FIELDS = [
    "pass_attempts", "pass_completions", "pass_yards", "pass_touchdowns",
    "interceptions_thrown", "sacks_taken",
    "rush_attempts", "rush_yards", "rush_touchdowns", "fumbles_lost",
    "targets", "receptions", "receiving_yards", "receiving_touchdowns",
    "tackles", "tackles_for_loss", "interceptions", "pass_deflections",
    "forced_fumbles", "fumble_recoveries",
    "fg_attempts", "fg_made", "xp_attempts", "xp_made",
    "punts", "punt_yards", "defensive_touchdowns",
]


def _merge_stats(stats_list: list[PlayerGameStats]) -> list[PlayerGameStats]:
    """Merge multiple stat entries for the same player into one."""
    by_id: dict[int, PlayerGameStats] = {}
    for s in stats_list:
        if s.player_id in by_id:
            existing = by_id[s.player_id]
            for fld in _ADDITIVE_INT_FIELDS:
                setattr(existing, fld, getattr(existing, fld) + getattr(s, fld))
            existing.sacks += s.sacks  # float
        else:
            by_id[s.player_id] = s
    return list(by_id.values())


# ===================================================================
# Core matchup simulation
# ===================================================================
#   Simulates ONE team's offensive possession against the OTHER team's
#   defense.  Returns offensive player stats, defensive player stats,
#   the offensive score, any defensive bonus score (pick-sixes / fumble
#   return TDs), and aggregate numbers.
# ===================================================================

def _simulate_matchup(
    off_ratings: UnitRatings,
    def_ratings: UnitRatings,
    off_pos: dict[str, list[dict]],
    def_pos: dict[str, list[dict]],
    off_team_id: int,
    def_team_id: int,
    rng: random.Random,
) -> tuple[list[PlayerGameStats], list[PlayerGameStats], int, int, dict[str, Any]]:
    """Simulate one team on offense vs the other on defense.

    Returns
    -------
    off_player_stats : list[PlayerGameStats]
    def_player_stats : list[PlayerGameStats]
    off_score : int
    def_score_bonus : int  (pick-sixes, fumble-return TDs)
    aggregates : dict      (team-level totals for TeamGameResult)
    """

    # ------------------------------------------------------------------ #
    #  Matchup differentials                                               #
    # ------------------------------------------------------------------ #
    # README: rushing = (1/3 RB + 2/3 OL) vs defense
    rush_off = (1 / 3) * off_ratings.rb_rushing + (2 / 3) * off_ratings.ol_run_block
    rush_def = (
        0.50 * def_ratings.dl_run_stop
        + 0.30 * def_ratings.lb_rating
        + 0.20 * def_ratings.secondary_rating
    )
    rush_matchup = rush_off - rush_def  # positive ⇒ offense advantage

    pass_off = (
        0.35 * off_ratings.qb_passing
        + 0.30 * off_ratings.receiving_corps
        + 0.35 * off_ratings.ol_pass_protect
    )
    pass_def = (
        0.35 * def_ratings.dl_pass_rush
        + 0.25 * def_ratings.lb_rating
        + 0.40 * def_ratings.secondary_rating
    )
    pass_matchup = pass_off - pass_def

    # ------------------------------------------------------------------ #
    #  Play volume & run/pass split                                        #
    # ------------------------------------------------------------------ #
    total_plays = rng.randint(57, 72)

    run_pct = 0.43 + (rush_matchup - pass_matchup) / 400.0
    run_pct = _clamp(run_pct + rng.gauss(0, 0.05), 0.28, 0.62)

    rush_attempts = max(12, round(total_plays * run_pct))
    total_pass_plays = total_plays - rush_attempts  # includes sacks

    # ------------------------------------------------------------------ #
    #  Sacks                                                               #
    # ------------------------------------------------------------------ #
    sack_diff = def_ratings.dl_pass_rush - off_ratings.ol_pass_protect
    sack_rate = _clamp(0.065 + sack_diff / 500.0 + rng.gauss(0, 0.015), 0.02, 0.15)
    sacks = max(0, round(total_pass_plays * sack_rate))
    sacks = min(sacks, max(0, total_pass_plays - 5))  # keep ≥5 actual throws

    pass_attempts = max(5, total_pass_plays - sacks)

    # ------------------------------------------------------------------ #
    #  Rushing aggregate                                                   #
    # ------------------------------------------------------------------ #
    base_ypc = 4.3
    ypc = base_ypc + rush_matchup / 20.0
    ypc = _clamp(ypc * rng.gauss(1.0, 0.12), 1.5, 7.5)
    rush_yards = max(0, round(rush_attempts * ypc))

    # ------------------------------------------------------------------ #
    #  Passing aggregate                                                   #
    # ------------------------------------------------------------------ #
    comp_pct = _clamp(0.63 + pass_matchup / 200.0 + rng.gauss(0, 0.05), 0.40, 0.80)
    completions = max(0, min(pass_attempts, round(pass_attempts * comp_pct)))

    ypa = _clamp((7.0 + pass_matchup / 20.0) * rng.gauss(1.0, 0.12), 3.5, 12.0)
    pass_yards = max(0, round(pass_attempts * ypa))

    # ------------------------------------------------------------------ #
    #  Turnovers                                                           #
    # ------------------------------------------------------------------ #
    int_rate = _clamp(0.025 - pass_matchup / 500.0 + rng.gauss(0, 0.008), 0.0, 0.08)
    interceptions = min(5, max(0, round(pass_attempts * int_rate)))

    fumbles_lost = min(4, max(0, round(
        rush_attempts * 0.015 + sacks * 0.08 + rng.gauss(0, 0.4)
    )))

    # ------------------------------------------------------------------ #
    #  Scoring                                                             #
    # ------------------------------------------------------------------ #
    total_yards = rush_yards + pass_yards
    num_drives = max(6, round(total_plays / rng.uniform(5.5, 7.0)))
    ypd = total_yards / max(1, num_drives)

    td_rate = _clamp(0.10 + ypd / 150.0 + rng.gauss(0, 0.03), 0.05, 0.50)

    total_tds = 0
    fg_attempts = 0
    for _ in range(num_drives):
        roll = rng.random()
        if roll < td_rate:
            total_tds += 1
        elif roll < td_rate + 0.15:
            fg_attempts += 1

    # Split TDs into rush / pass
    rush_share = rush_yards / max(1, total_yards) if total_yards > 0 else 0.5
    rush_tds = sum(1 for _ in range(total_tds) if rng.random() < _clamp(rush_share * 1.1, 0.1, 0.9))
    pass_tds = total_tds - rush_tds

    # Field goals
    fg_pct = _clamp(0.72 + off_ratings.kick_power / 400.0, 0.60, 0.95)
    fg_made = sum(1 for _ in range(fg_attempts) if rng.random() < fg_pct)

    # Extra points
    xp_pct = _clamp(0.94 + off_ratings.kick_power / 1500.0, 0.90, 0.995)
    xp_made = sum(1 for _ in range(total_tds) if rng.random() < xp_pct)

    off_score = total_tds * 6 + xp_made + fg_made * 3

    # Defensive scoring (pick-sixes, fumble-return TDs)
    pick_sixes = sum(1 for _ in range(interceptions) if rng.random() < 0.12)
    fumble_ret_tds = sum(1 for _ in range(fumbles_lost) if rng.random() < 0.08)
    def_score_bonus = (pick_sixes + fumble_ret_tds) * 7  # assume PAT made

    # ================================================================== #
    #  DISTRIBUTE STATS TO INDIVIDUAL PLAYERS                              #
    # ================================================================== #
    player_map: dict[int, PlayerGameStats] = {}

    def _get_or_create(player: dict) -> PlayerGameStats:
        pid = player["id"]
        if pid not in player_map:
            player_map[pid] = PlayerGameStats(
                player_id=pid,
                team_id=player.get("team_id", 0),
                name=player.get("name", f"Player #{pid}"),
                position=player["position"],
            )
        return player_map[pid]

    # ---- QB passing stats ----
    qbs = _starters(off_pos, "QB", 1)
    if qbs:
        qs = _get_or_create(qbs[0])
        qs.pass_attempts = pass_attempts
        qs.pass_completions = completions
        qs.pass_yards = pass_yards
        qs.pass_touchdowns = pass_tds
        qs.interceptions_thrown = interceptions
        qs.sacks_taken = sacks

    # ---- Rushing distribution (QB scrambles + RBs) ----
    rushers: list[dict] = []
    rush_weights: list[float] = []

    if qbs:
        scramble_share = _clamp(0.05 + off_ratings.qb_mobility / 400.0, 0.02, 0.20)
        rushers.append(qbs[0])
        rush_weights.append(max(0.02, scramble_share))

    rbs = _starters(off_pos, "RB", 2)
    for i, rb in enumerate(rbs):
        w = (0.35 * rb.get("speed", 30) + 0.35 * rb.get("acceleration", 30) + 0.30 * rb.get("lateral_quickness", 30)) * (2.0 if i == 0 else 1.0)
        rushers.append(rb)
        rush_weights.append(w)

    if rushers:
        att_splits = _weighted_partition(rush_attempts, rush_weights, rng)
        yard_splits = _weighted_partition(rush_yards, rush_weights, rng)
        td_pool = rush_tds
        # Assign rush TDs weighted by yards
        rtd_weights = [max(0.1, float(yard_splits[i])) for i in range(len(rushers))]
        rtd_splits = _weighted_partition(td_pool, rtd_weights, rng)
        # Fumbles: more likely for carriers with low ball_security
        fumble_risk = [rush_weights[i] * (100 - rushers[i].get("ball_security", 50)) for i in range(len(rushers))]
        fumble_risk = [max(0.1, w) for w in fumble_risk]
        fum_splits = _weighted_partition(fumbles_lost, fumble_risk, rng)

        for i, rusher in enumerate(rushers):
            ps = _get_or_create(rusher)
            ps.rush_attempts += att_splits[i]
            ps.rush_yards += yard_splits[i]
            ps.rush_touchdowns += rtd_splits[i]
            ps.fumbles_lost += fum_splits[i]

    # ---- Receiving distribution (WR + TE + RB check-downs) ----
    all_receivers: list[dict] = []
    target_weights: list[float] = []

    wrs = _starters(off_pos, "WR", 3)
    for i, wr in enumerate(wrs):
        all_receivers.append(wr)
        w = 0.40 * wr.get("catching", 50) + 0.35 * wr.get("route_running", 50) + 0.25 * wr.get("speed", 30)
        target_weights.append(w * (1.5 if i == 0 else 1.0))

    tes = _starters(off_pos, "TE", 1)
    for te in tes:
        all_receivers.append(te)
        w = 0.40 * te.get("catching", 50) + 0.35 * te.get("route_running", 50) + 0.25 * te.get("speed", 30)
        target_weights.append(w * 0.85)

    for rb in rbs:
        all_receivers.append(rb)
        w = 0.45 * rb.get("catching", 50) + 0.35 * rb.get("route_running", 50) + 0.20 * rb.get("speed", 30)
        target_weights.append(w * 0.30)

    if all_receivers:
        tgt_splits = _weighted_partition(pass_attempts, target_weights, rng)
        rec_splits = _weighted_partition(completions, target_weights, rng)

        # Enforce receptions ≤ targets
        for i in range(len(all_receivers)):
            if rec_splits[i] > tgt_splits[i]:
                rec_splits[i] = tgt_splits[i]
        # Redistribute deficit
        deficit = completions - sum(rec_splits)
        attempts = 0
        while deficit > 0 and attempts < len(all_receivers) * 3:
            for i in sorted(
                range(len(all_receivers)),
                key=lambda idx: target_weights[idx],
                reverse=True,
            ):
                if deficit <= 0:
                    break
                if rec_splits[i] < tgt_splits[i]:
                    rec_splits[i] += 1
                    deficit -= 1
            attempts += 1

        # Yards proportional to receptions (with noise)
        rec_yard_weights = [max(0.1, rec_splits[i] + rng.gauss(0, 0.5)) for i in range(len(all_receivers))]
        yard_splits = _weighted_partition(pass_yards, rec_yard_weights, rng)

        # Pass TDs to receivers proportional to yards
        ptd_weights = [max(0.1, float(yard_splits[i])) for i in range(len(all_receivers))]
        ptd_splits = _weighted_partition(pass_tds, ptd_weights, rng)

        for i, rec in enumerate(all_receivers):
            ps = _get_or_create(rec)
            ps.targets += tgt_splits[i]
            ps.receptions += rec_splits[i]
            ps.receiving_yards += yard_splits[i]
            ps.receiving_touchdowns += ptd_splits[i]

    # ---- Kicker stats ----
    kickers = _starters(off_pos, "K", 1)
    if kickers:
        ks = _get_or_create(kickers[0])
        ks.fg_attempts = fg_attempts
        ks.fg_made = fg_made
        ks.xp_attempts = total_tds
        ks.xp_made = xp_made

    # ---- Punter stats ----
    punters = _starters(off_pos, "P", 1)
    if punters:
        non_scoring_drives = max(
            0,
            num_drives - total_tds - fg_made - interceptions - fumbles_lost,
        )
        punt_count = max(2, non_scoring_drives + rng.randint(-1, 1))
        avg_punt = _clamp(35.0 + off_ratings.punt_power / 5.0, 30, 55)
        punt_total_yards = max(0, round(punt_count * avg_punt * rng.gauss(1.0, 0.08)))

        pps = _get_or_create(punters[0])
        pps.punts = punt_count
        pps.punt_yards = punt_total_yards

    off_stats = list(player_map.values())

    # ================================================================== #
    #  DEFENSIVE PLAYER STATS (for the *defensive* team)                   #
    # ================================================================== #
    def_player_map: dict[int, PlayerGameStats] = {}

    def _get_or_create_def(player: dict) -> PlayerGameStats:
        pid = player["id"]
        if pid not in def_player_map:
            def_player_map[pid] = PlayerGameStats(
                player_id=pid,
                team_id=player.get("team_id", 0),
                name=player.get("name", f"Player #{pid}"),
                position=player["position"],
            )
        return def_player_map[pid]

    def_players: list[dict] = []
    for pos in list(DL_POSITIONS) + list(LB_POSITIONS) + list(DB_POSITIONS):
        def_players.extend(_starters(def_pos, pos))

    if def_players:
        # Total tackles ≈ total offensive plays
        total_tackles = max(0, total_plays + rng.randint(-5, 5))
        tackle_w = [
            TACKLE_WEIGHTS.get(p["position"], 1.0)
            * (0.5 * (p.get("tackling", 50) / 50.0) + 0.3 * (p.get("pursuit", 50) / 50.0) + 0.2 * (p.get("speed", 30) / 50.0))
            for p in def_players
        ]
        tackle_splits = _weighted_partition(total_tackles, tackle_w, rng)

        # Sacks
        sack_w = [
            SACK_WEIGHTS.get(p["position"], 0.1)
            * (0.7 * (p.get("pass_rush", 30) / 50.0) + 0.3 * (p.get("block_shedding", 50) / 50.0))
            for p in def_players
        ]
        sack_splits = _weighted_partition(sacks, sack_w, rng)

        # Tackles for loss (≥ sacks, since sacks are a subset)
        total_tfl = max(sacks, round(total_plays * 0.08 + rng.gauss(0, 1)))
        tfl_w = [
            TFL_WEIGHTS.get(p["position"], 0.5) * (0.5 * (p.get("tackling", 50) / 50.0) + 0.5 * (p.get("pursuit", 50) / 50.0))
            for p in def_players
        ]
        tfl_splits = _weighted_partition(total_tfl, tfl_w, rng)

        # Interceptions
        int_w = [
            max(0.001, INT_WEIGHTS.get(p["position"], 0.0)
            * (0.5 * (p.get("coverage", 50) / 50.0) + 0.3 * (p.get("speed", 30) / 50.0) + 0.2 * (p.get("lateral_quickness", 30) / 50.0)))
            for p in def_players
        ]
        int_splits = _weighted_partition(interceptions, int_w, rng)

        # Pass deflections (≥ interceptions)
        total_pd = max(interceptions, round(pass_attempts * 0.08 + rng.gauss(0, 1)))
        pd_w = [
            PD_WEIGHTS.get(p["position"], 0.1)
            * (0.5 * (p.get("coverage", 50) / 50.0) + 0.3 * (p.get("speed", 30) / 50.0) + 0.2 * (p.get("lateral_quickness", 30) / 50.0))
            for p in def_players
        ]
        pd_splits = _weighted_partition(total_pd, pd_w, rng)

        # Forced fumbles
        ff_w = [
            FF_WEIGHTS.get(p["position"], 0.5) * (0.5 * (p.get("tackling", 50) / 50.0) + 0.5 * (p.get("pursuit", 50) / 50.0))
            for p in def_players
        ]
        ff_splits = _weighted_partition(fumbles_lost, ff_w, rng)

        # Fumble recoveries (≤ total forced fumbles, distributed similarly)
        fr_count = min(fumbles_lost, max(0, fumbles_lost - rng.randint(0, max(1, fumbles_lost))))
        fr_splits = _weighted_partition(fr_count, ff_w, rng)

        # Defensive TDs
        def_td_total = pick_sixes + fumble_ret_tds
        def_td_w = [
            int_w[i] * 2.0 + ff_w[i]
            for i in range(len(def_players))
        ]
        def_td_splits = _weighted_partition(def_td_total, def_td_w, rng)

        for i, dp in enumerate(def_players):
            ds = _get_or_create_def(dp)
            ds.tackles += tackle_splits[i]
            ds.sacks += float(sack_splits[i])
            ds.tackles_for_loss += tfl_splits[i]
            ds.interceptions += int_splits[i]
            ds.pass_deflections += pd_splits[i]
            ds.forced_fumbles += ff_splits[i]
            ds.fumble_recoveries += fr_splits[i]
            ds.defensive_touchdowns += def_td_splits[i]

    def_stats = list(def_player_map.values())

    # ---- Aggregate stats for TeamGameResult ----
    agg: dict[str, Any] = {
        "total_plays": total_plays,
        "rush_attempts": rush_attempts,
        "rush_yards": rush_yards,
        "pass_attempts": pass_attempts,
        "pass_completions": completions,
        "pass_yards": pass_yards,
        "sacks_allowed": sacks,
        "interceptions": interceptions,
        "fumbles_lost": fumbles_lost,
        "total_yards": total_yards,
        "fg_attempts": fg_attempts,
        "fg_made": fg_made,
    }

    return off_stats, def_stats, off_score, def_score_bonus, agg


# ===================================================================
# Public API
# ===================================================================

def simulate_game(
    home_team_id: int,
    away_team_id: int,
    conn: sqlite3.Connection,
    *,
    manager_team_id: int | None = None,
    manager_in_game: int = 0,
    seed: int | None = None,
) -> GameResult:
    """Simulate a single football game between two teams.

    Parameters
    ----------
    home_team_id : int
        Database ID of the home team.
    away_team_id : int
        Database ID of the away team.
    conn : sqlite3.Connection
        Open database connection (read-only usage).
    manager_team_id : int | None
        If provided, this team receives a small in-game-management bonus.
    manager_in_game : int
        The manager's ``in_game_management`` skill (0-99).
    seed : int | None
        Optional RNG seed for reproducible results.

    Returns
    -------
    GameResult
        Complete box-score with individual player stats for both teams.
    """
    rng = random.Random(seed)

    # Team metadata
    home_team = get_team_by_id(home_team_id, conn) or {"id": home_team_id, "name": "Home"}
    away_team = get_team_by_id(away_team_id, conn) or {"id": away_team_id, "name": "Away"}

    # Rosters grouped by position
    home_pos = _extract_position_groups(home_team_id, conn)
    away_pos = _extract_position_groups(away_team_id, conn)

    # Manager + home-field advantage → rating bonus
    home_bonus = 1.5  # small home-field edge
    away_bonus = 0.0
    if manager_team_id == home_team_id:
        home_bonus += (manager_in_game / 99.0) * 3.0
    elif manager_team_id == away_team_id:
        away_bonus += (manager_in_game / 99.0) * 3.0

    home_ratings = _compute_ratings(home_pos, home_bonus)
    away_ratings = _compute_ratings(away_pos, away_bonus)

    # --- Home offense vs Away defense ---
    home_off, away_def, home_off_score, away_def_bonus, home_agg = _simulate_matchup(
        home_ratings, away_ratings,
        home_pos, away_pos,
        home_team_id, away_team_id,
        rng,
    )

    # --- Away offense vs Home defense ---
    away_off, home_def, away_off_score, home_def_bonus, away_agg = _simulate_matchup(
        away_ratings, home_ratings,
        away_pos, home_pos,
        away_team_id, home_team_id,
        rng,
    )

    # Combine & merge stats per team
    home_all = _merge_stats(home_off + home_def)
    away_all = _merge_stats(away_off + away_def)

    home_score = home_off_score + home_def_bonus
    away_score = away_off_score + away_def_bonus

    home_result = TeamGameResult(
        team_id=home_team_id,
        team_name=home_team.get("name", "Home"),
        score=home_score,
        total_yards=home_agg["total_yards"],
        rush_attempts=home_agg["rush_attempts"],
        rush_yards=home_agg["rush_yards"],
        pass_attempts=home_agg["pass_attempts"],
        pass_completions=home_agg["pass_completions"],
        pass_yards=home_agg["pass_yards"],
        turnovers=home_agg["interceptions"] + home_agg["fumbles_lost"],
        sacks_allowed=home_agg["sacks_allowed"],
        player_stats=home_all,
    )

    away_result = TeamGameResult(
        team_id=away_team_id,
        team_name=away_team.get("name", "Away"),
        score=away_score,
        total_yards=away_agg["total_yards"],
        rush_attempts=away_agg["rush_attempts"],
        rush_yards=away_agg["rush_yards"],
        pass_attempts=away_agg["pass_attempts"],
        pass_completions=away_agg["pass_completions"],
        pass_yards=away_agg["pass_yards"],
        turnovers=away_agg["interceptions"] + away_agg["fumbles_lost"],
        sacks_allowed=away_agg["sacks_allowed"],
        player_stats=away_all,
    )

    return GameResult(home=home_result, away=away_result)
