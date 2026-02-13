"""
Player DTO for GM Career Mode.
All attributes 0-99. Each trainable attribute has a _cap (ceiling); overall/potential are computed from these.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class Player:
    """A player on a team. Same position list at all levels; may have secondary_position at lower levels."""

    id: int | None = None
    team_id: int = 0
    position: str = ""
    secondary_position: str | None = None  # e.g. "P" for a K in HS
    name: str = ""
    potential: int = 0  # 0-99, cached computed from _cap attributes at position
    class_year: int = 1  # 1=Fr, 2=So, 3=Jr, 4=Sr
    # Physical (0-99 except where noted); no caps (non-trainable: height, weight, age, arm_length)
    height: int = 0
    weight: int = 0
    age: int = 0
    speed: int = 0
    speed_cap: int = 50
    acceleration: int = 0
    acceleration_cap: int = 50
    lateral_quickness: int = 0
    lateral_quickness_cap: int = 50
    vision: int = 0
    vision_cap: int = 50
    lower_body_strength: int = 0
    lower_body_strength_cap: int = 50
    upper_body_strength: int = 0
    upper_body_strength_cap: int = 50
    # Physical (inches / combine-style)
    arm_length: int = 32  # inches, e.g. 28-36 (no cap)
    vertical_jump: int = 50  # 0-99 explosiveness
    vertical_jump_cap: int = 50
    broad_jump: int = 50   # 0-99 lower-body explosiveness
    broad_jump_cap: int = 50
    # Position-specific (0-99)
    overall: int = 0  # cached computed from current attributes at position
    familiarity: int = 0
    familiarity_cap: int = 50
    kick_power: int = 0
    kick_power_cap: int = 50
    arm_strength: int = 0
    arm_strength_cap: int = 50
    run_block: int = 0
    run_block_cap: int = 50
    pass_rush: int = 0
    pass_rush_cap: int = 50
    pass_protection: int = 0
    pass_protection_cap: int = 50
    scrambling: int = 0
    scrambling_cap: int = 50
    # QB accuracy
    short_accuracy: int = 50
    short_accuracy_cap: int = 50
    mid_accuracy: int = 50
    mid_accuracy_cap: int = 50
    deep_accuracy: int = 50
    deep_accuracy_cap: int = 50
    throw_under_pressure: int = 50
    throw_under_pressure_cap: int = 50
    # Ball security & receiving
    ball_security: int = 50
    ball_security_cap: int = 50
    catching: int = 50
    catching_cap: int = 50
    route_running: int = 50
    route_running_cap: int = 50
    # Defense
    tackling: int = 50
    tackling_cap: int = 50
    coverage: int = 50
    coverage_cap: int = 50
    block_shedding: int = 50
    block_shedding_cap: int = 50
    pursuit: int = 50  # play recognition
    pursuit_cap: int = 50
    # Special teams
    kick_accuracy: int = 50
    kick_accuracy_cap: int = 50

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "team_id": self.team_id,
            "position": self.position,
            "name": self.name,
            "potential": self.potential,
            "class_year": self.class_year,
            "height": self.height,
            "weight": self.weight,
            "age": self.age,
            "speed": self.speed,
            "speed_cap": self.speed_cap,
            "acceleration": self.acceleration,
            "acceleration_cap": self.acceleration_cap,
            "lateral_quickness": self.lateral_quickness,
            "lateral_quickness_cap": self.lateral_quickness_cap,
            "vision": self.vision,
            "vision_cap": self.vision_cap,
            "lower_body_strength": self.lower_body_strength,
            "lower_body_strength_cap": self.lower_body_strength_cap,
            "upper_body_strength": self.upper_body_strength,
            "upper_body_strength_cap": self.upper_body_strength_cap,
            "arm_length": self.arm_length,
            "vertical_jump": self.vertical_jump,
            "vertical_jump_cap": self.vertical_jump_cap,
            "broad_jump": self.broad_jump,
            "broad_jump_cap": self.broad_jump_cap,
            "overall": self.overall,
            "familiarity": self.familiarity,
            "familiarity_cap": self.familiarity_cap,
            "kick_power": self.kick_power,
            "kick_power_cap": self.kick_power_cap,
            "arm_strength": self.arm_strength,
            "arm_strength_cap": self.arm_strength_cap,
            "run_block": self.run_block,
            "run_block_cap": self.run_block_cap,
            "pass_rush": self.pass_rush,
            "pass_rush_cap": self.pass_rush_cap,
            "pass_protection": self.pass_protection,
            "pass_protection_cap": self.pass_protection_cap,
            "scrambling": self.scrambling,
            "scrambling_cap": self.scrambling_cap,
            "short_accuracy": self.short_accuracy,
            "short_accuracy_cap": self.short_accuracy_cap,
            "mid_accuracy": self.mid_accuracy,
            "mid_accuracy_cap": self.mid_accuracy_cap,
            "deep_accuracy": self.deep_accuracy,
            "deep_accuracy_cap": self.deep_accuracy_cap,
            "throw_under_pressure": self.throw_under_pressure,
            "throw_under_pressure_cap": self.throw_under_pressure_cap,
            "ball_security": self.ball_security,
            "ball_security_cap": self.ball_security_cap,
            "catching": self.catching,
            "catching_cap": self.catching_cap,
            "route_running": self.route_running,
            "route_running_cap": self.route_running_cap,
            "tackling": self.tackling,
            "tackling_cap": self.tackling_cap,
            "coverage": self.coverage,
            "coverage_cap": self.coverage_cap,
            "block_shedding": self.block_shedding,
            "block_shedding_cap": self.block_shedding_cap,
            "pursuit": self.pursuit,
            "pursuit_cap": self.pursuit_cap,
            "kick_accuracy": self.kick_accuracy,
            "kick_accuracy_cap": self.kick_accuracy_cap,
        }
        if self.id is not None:
            d["id"] = self.id
        if self.secondary_position is not None:
            d["secondary_position"] = self.secondary_position
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Player":
        def _cap(key: str, default: int = 50) -> int:
            cap_key = f"{key}_cap"
            return data.get(cap_key, data.get(key, default))

        return cls(
            id=data.get("id"),
            team_id=data.get("team_id", 0),
            position=data.get("position", ""),
            secondary_position=data.get("secondary_position"),
            name=data.get("name", ""),
            potential=data.get("potential", 0),
            class_year=data.get("class_year", 1),
            height=data.get("height", 0),
            weight=data.get("weight", 0),
            age=data.get("age", 0),
            speed=data.get("speed", 0),
            speed_cap=_cap("speed"),
            acceleration=data.get("acceleration", 0),
            acceleration_cap=_cap("acceleration"),
            lateral_quickness=data.get("lateral_quickness", 0),
            lateral_quickness_cap=_cap("lateral_quickness"),
            vision=data.get("vision", 0),
            vision_cap=_cap("vision"),
            lower_body_strength=data.get("lower_body_strength", 0),
            lower_body_strength_cap=_cap("lower_body_strength"),
            upper_body_strength=data.get("upper_body_strength", 0),
            upper_body_strength_cap=_cap("upper_body_strength"),
            arm_length=data.get("arm_length", 32),
            vertical_jump=data.get("vertical_jump", 50),
            vertical_jump_cap=_cap("vertical_jump"),
            broad_jump=data.get("broad_jump", 50),
            broad_jump_cap=_cap("broad_jump"),
            overall=data.get("overall", 0),
            familiarity=data.get("familiarity", 0),
            familiarity_cap=_cap("familiarity"),
            kick_power=data.get("kick_power", 0),
            kick_power_cap=_cap("kick_power"),
            arm_strength=data.get("arm_strength", 0),
            arm_strength_cap=_cap("arm_strength"),
            run_block=data.get("run_block", 0),
            run_block_cap=_cap("run_block"),
            pass_rush=data.get("pass_rush", 0),
            pass_rush_cap=_cap("pass_rush"),
            pass_protection=data.get("pass_protection", 0),
            pass_protection_cap=_cap("pass_protection"),
            scrambling=data.get("scrambling", 0),
            scrambling_cap=_cap("scrambling"),
            short_accuracy=data.get("short_accuracy", 50),
            short_accuracy_cap=_cap("short_accuracy"),
            mid_accuracy=data.get("mid_accuracy", 50),
            mid_accuracy_cap=_cap("mid_accuracy"),
            deep_accuracy=data.get("deep_accuracy", 50),
            deep_accuracy_cap=_cap("deep_accuracy"),
            throw_under_pressure=data.get("throw_under_pressure", 50),
            throw_under_pressure_cap=_cap("throw_under_pressure"),
            ball_security=data.get("ball_security", 50),
            ball_security_cap=_cap("ball_security"),
            catching=data.get("catching", 50),
            catching_cap=_cap("catching"),
            route_running=data.get("route_running", 50),
            route_running_cap=_cap("route_running"),
            tackling=data.get("tackling", 50),
            tackling_cap=_cap("tackling"),
            coverage=data.get("coverage", 50),
            coverage_cap=_cap("coverage"),
            block_shedding=data.get("block_shedding", 50),
            block_shedding_cap=_cap("block_shedding"),
            pursuit=data.get("pursuit", 50),
            pursuit_cap=_cap("pursuit"),
            kick_accuracy=data.get("kick_accuracy", 50),
            kick_accuracy_cap=_cap("kick_accuracy"),
        )
