"""
Procedural generation of divisions, teams, and players for GM Career Mode.
Runs in background after character creation; progress stored in DB.
"""
from .generate import generate_all_teams_and_players

__all__ = ["generate_all_teams_and_players"]
