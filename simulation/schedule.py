"""
Round-robin schedule generation for GM Career Mode.

Each division has 10 teams.  A double round-robin (every pair meets twice —
once at each venue) produces 18 weeks of 5 games each (90 games total per
division).  The circle method is used to guarantee every team plays exactly
once per week.
"""
from __future__ import annotations

import random


def generate_division_schedule(
    team_ids: list[int],
    rng: random.Random | None = None,
) -> list[tuple[int, int, int]]:
    """Generate a full double round-robin schedule for one division.

    Parameters
    ----------
    team_ids : list[int]
        Exactly 10 team database IDs.
    rng : random.Random | None
        Optional RNG; if given the initial ordering is shuffled so
        schedules differ across divisions even with the same seed.

    Returns
    -------
    list of (week, home_team_id, away_team_id)
        ``week`` is 1-indexed (1 through 18).
    """
    n = len(team_ids)
    if n < 2:
        return []

    teams = list(team_ids)
    if rng is not None:
        rng.shuffle(teams)

    # Pad to even if needed (shouldn't happen with 10, but defensive)
    if n % 2 != 0:
        teams.append(-1)  # bye marker
        n += 1

    fixed = teams[0]
    rotating = list(teams[1:])
    num_rounds = n - 1  # 9 for 10 teams

    first_half: list[tuple[int, int, int]] = []

    for round_idx in range(num_rounds):
        week = round_idx + 1
        pairs: list[tuple[int, int]] = []

        # Fixed team vs first rotating — alternate home/away each round
        if round_idx % 2 == 0:
            pairs.append((fixed, rotating[0]))
        else:
            pairs.append((rotating[0], fixed))

        # Remaining pairs: i ↔ (len(rotating)-i) in the rotating list
        for i in range(1, n // 2):
            t1 = rotating[i]
            t2 = rotating[n - 1 - i]  # n-1 == len(rotating)
            if i % 2 == 0:
                pairs.append((t1, t2))
            else:
                pairs.append((t2, t1))

        for home, away in pairs:
            if home == -1 or away == -1:
                continue  # skip byes
            first_half.append((week, home, away))

        # Circle-method rotation: last element moves to front
        rotating = [rotating[-1]] + rotating[:-1]

    # Second half: same matchups, swap home/away, offset weeks
    second_half: list[tuple[int, int, int]] = []
    for week, home, away in first_half:
        second_half.append((week + num_rounds, away, home))

    return first_half + second_half
