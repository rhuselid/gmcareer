"""
Division DTO for GM Career Mode.
Divisions belong to a level (high_school, college, professional).
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class Division:
    """A division within a league level (e.g. Region 1, D1, NFL)."""

    id: int | None = None
    name: str = ""
    level: str = ""  # high_school | college | professional

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"name": self.name, "level": self.level}
        if self.id is not None:
            d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Division":
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            level=data.get("level", ""),
        )
