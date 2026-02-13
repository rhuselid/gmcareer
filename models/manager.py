"""
Manager DTO for GM Career Mode.
All skills are scored 0-99. Character creation allocates a fixed pool of points.
"""
from dataclasses import dataclass
from typing import Dict

# Display names and internal keys for the 5 manager skills (README)
MANAGER_SKILLS: Dict[str, str] = {
    "scouting": "Scouting",
    "developing_potential": "Developing Potential",
    "unlocking_potential": "Unlocking New Potential",
    "convincing_players": "Convincing Players to Join",
    "in_game_management": "In-Game Management",
}

# Total points to allocate during character creation
STARTING_SKILL_POINTS = 25

SKILL_MIN = 0
SKILL_MAX = 99


@dataclass
class Manager:
    """Represents the human player as a General Manager."""

    id: int | None = None
    name: str = ""
    scouting: int = 0
    developing_potential: int = 0
    unlocking_potential: int = 0
    convincing_players: int = 0
    in_game_management: int = 0
    prestige: int = 50  # 0-99, updated by performance vs expectations
    unspent_skill_points: int = 0  # earned in offseason, spent on GM attributes

    def __post_init__(self) -> None:
        for key in MANAGER_SKILLS:
            val = getattr(self, key)
            if not SKILL_MIN <= val <= SKILL_MAX:
                raise ValueError(f"{key} must be between {SKILL_MIN} and {SKILL_MAX}, got {val}")
        if not SKILL_MIN <= self.prestige <= SKILL_MAX:
            raise ValueError(f"prestige must be between {SKILL_MIN} and {SKILL_MAX}, got {self.prestige}")
        if self.unspent_skill_points < 0:
            raise ValueError(f"unspent_skill_points must be >= 0, got {self.unspent_skill_points}")

    def to_dict(self) -> Dict:
        d: Dict = {"name": self.name}
        if self.id is not None:
            d["id"] = self.id
        d.update({
            "scouting": self.scouting,
            "developing_potential": self.developing_potential,
            "unlocking_potential": self.unlocking_potential,
            "convincing_players": self.convincing_players,
            "in_game_management": self.in_game_management,
            "prestige": self.prestige,
            "unspent_skill_points": self.unspent_skill_points,
        })
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> "Manager":
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            scouting=data.get("scouting", 0),
            developing_potential=data.get("developing_potential", 0),
            unlocking_potential=data.get("unlocking_potential", 0),
            convincing_players=data.get("convincing_players", 0),
            in_game_management=data.get("in_game_management", 0),
            prestige=data.get("prestige", 50),
            unspent_skill_points=data.get("unspent_skill_points", 0),
        )
