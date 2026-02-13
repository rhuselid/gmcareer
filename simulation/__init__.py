"""
Simulation engine for GM Career Mode.
Simulates football games between two teams, producing realistic box-score stats.
Also provides round-robin schedule generation, player development, and offseason flow.
"""
from .engine import simulate_game
from .schedule import generate_division_schedule
from .development import run_development_for_team, run_development_all_teams
from .offseason import (
    run_freshmen_class,
    run_recruiting,
    run_draft,
    run_training_camps,
    run_offseason_development,
    run_offseason_complete,
)

__all__ = [
    "simulate_game",
    "generate_division_schedule",
    "run_development_for_team",
    "run_development_all_teams",
    "run_freshmen_class",
    "run_recruiting",
    "run_draft",
    "run_training_camps",
    "run_offseason_development",
    "run_offseason_complete",
]
