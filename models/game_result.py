"""
Game result DTOs for GM Career Mode.

PlayerGameStats holds the box-score line for a single player in a single game.
TeamGameResult holds aggregate team stats plus a list of player stats.
GameResult wraps home and away TeamGameResults.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List


@dataclass
class PlayerGameStats:
    """One player's stat line for a single game (box-score entry)."""

    player_id: int = 0
    team_id: int = 0
    name: str = ""
    position: str = ""

    # --- Passing ---
    pass_attempts: int = 0
    pass_completions: int = 0
    pass_yards: int = 0
    pass_touchdowns: int = 0
    interceptions_thrown: int = 0
    sacks_taken: int = 0

    # --- Rushing ---
    rush_attempts: int = 0
    rush_yards: int = 0
    rush_touchdowns: int = 0
    fumbles_lost: int = 0

    # --- Receiving ---
    targets: int = 0
    receptions: int = 0
    receiving_yards: int = 0
    receiving_touchdowns: int = 0

    # --- Defense ---
    tackles: int = 0
    sacks: float = 0.0
    tackles_for_loss: int = 0
    interceptions: int = 0
    pass_deflections: int = 0
    forced_fumbles: int = 0
    fumble_recoveries: int = 0

    # --- Kicking ---
    fg_attempts: int = 0
    fg_made: int = 0
    xp_attempts: int = 0
    xp_made: int = 0

    # --- Punting ---
    punts: int = 0
    punt_yards: int = 0

    # --- Defensive / special-teams scoring ---
    defensive_touchdowns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "team_id": self.team_id,
            "name": self.name,
            "position": self.position,
            "pass_attempts": self.pass_attempts,
            "pass_completions": self.pass_completions,
            "pass_yards": self.pass_yards,
            "pass_touchdowns": self.pass_touchdowns,
            "interceptions_thrown": self.interceptions_thrown,
            "sacks_taken": self.sacks_taken,
            "rush_attempts": self.rush_attempts,
            "rush_yards": self.rush_yards,
            "rush_touchdowns": self.rush_touchdowns,
            "fumbles_lost": self.fumbles_lost,
            "targets": self.targets,
            "receptions": self.receptions,
            "receiving_yards": self.receiving_yards,
            "receiving_touchdowns": self.receiving_touchdowns,
            "tackles": self.tackles,
            "sacks": self.sacks,
            "tackles_for_loss": self.tackles_for_loss,
            "interceptions": self.interceptions,
            "pass_deflections": self.pass_deflections,
            "forced_fumbles": self.forced_fumbles,
            "fumble_recoveries": self.fumble_recoveries,
            "fg_attempts": self.fg_attempts,
            "fg_made": self.fg_made,
            "xp_attempts": self.xp_attempts,
            "xp_made": self.xp_made,
            "punts": self.punts,
            "punt_yards": self.punt_yards,
            "defensive_touchdowns": self.defensive_touchdowns,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerGameStats":
        return cls(**{k: data.get(k, getattr(cls(), k)) for k in cls.__dataclass_fields__})


@dataclass
class TeamGameResult:
    """Aggregate team-level stats for one side of a game, plus individual player stats."""

    team_id: int = 0
    team_name: str = ""
    score: int = 0

    # Aggregate offensive stats
    total_yards: int = 0
    rush_attempts: int = 0
    rush_yards: int = 0
    pass_attempts: int = 0
    pass_completions: int = 0
    pass_yards: int = 0
    turnovers: int = 0
    sacks_allowed: int = 0

    player_stats: List[PlayerGameStats] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_id": self.team_id,
            "team_name": self.team_name,
            "score": self.score,
            "total_yards": self.total_yards,
            "rush_attempts": self.rush_attempts,
            "rush_yards": self.rush_yards,
            "pass_attempts": self.pass_attempts,
            "pass_completions": self.pass_completions,
            "pass_yards": self.pass_yards,
            "turnovers": self.turnovers,
            "sacks_allowed": self.sacks_allowed,
            "player_stats": [ps.to_dict() for ps in self.player_stats],
        }


@dataclass
class GameResult:
    """Full result of a simulated game: home and away team results."""

    home: TeamGameResult = field(default_factory=TeamGameResult)
    away: TeamGameResult = field(default_factory=TeamGameResult)

    @property
    def home_score(self) -> int:
        return self.home.score

    @property
    def away_score(self) -> int:
        return self.away.score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "home": self.home.to_dict(),
            "away": self.away.to_dict(),
        }
