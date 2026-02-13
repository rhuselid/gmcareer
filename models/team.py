"""
Team DTO for GM Career Mode.
Teams have name, prestige, facility grade; college has NIL budget, pro has budget.
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class Team:
    """A team in a division (high school, college, or professional)."""

    id: int | None = None
    division_id: int = 0
    name: str = ""
    prestige: int = 0  # 0-99
    facility_grade: int = 0  # 0-99
    nil_budget: int | None = None  # college only
    budget: int | None = None  # pro only

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "division_id": self.division_id,
            "name": self.name,
            "prestige": self.prestige,
            "facility_grade": self.facility_grade,
        }
        if self.id is not None:
            d["id"] = self.id
        if self.nil_budget is not None:
            d["nil_budget"] = self.nil_budget
        if self.budget is not None:
            d["budget"] = self.budget
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Team":
        return cls(
            id=data.get("id"),
            division_id=data.get("division_id", 0),
            name=data.get("name", ""),
            prestige=data.get("prestige", 0),
            facility_grade=data.get("facility_grade", 0),
            nil_budget=data.get("nil_budget"),
            budget=data.get("budget"),
        )
