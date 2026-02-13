"""
League structure and naming constants for GM Career Mode.
Same position list across all levels; roster sizes vary by level.
"""
from typing import Dict

# Roster sizes: HS 30, College 40, Pro 53
ROSTER_SIZE_HIGH_SCHOOL = 30
ROSTER_SIZE_COLLEGE = 40
ROSTER_SIZE_PROFESSIONAL = 53

ROSTER_SIZES: Dict[str, int] = {
    "high_school": ROSTER_SIZE_HIGH_SCHOOL,
    "college": ROSTER_SIZE_COLLEGE,
    "professional": ROSTER_SIZE_PROFESSIONAL,
}

# Positions (same at all levels; at lower levels players may have secondary_position)
POSITIONS = [
    "QB", "RB", "FB", "WR", "TE",
    "LT", "LG", "C", "RG", "RT",  # OL
    "DE", "DT", "NT", "OLB", "ILB", "CB", "S",
    "K", "P", "LS",
]

# Position groups for depth chart (Offense / Defense / Special Teams)
POSITIONS_OFFENSE = ["QB", "RB", "FB", "WR", "TE", "LT", "LG", "C", "RG", "RT"]
POSITIONS_DEFENSE = ["DE", "DT", "NT", "OLB", "ILB", "CB", "S"]
POSITIONS_SPECIAL_TEAMS = ["K", "P", "LS"]

# Formation layout: 2D grid of position names (same position can repeat for left/right)
# Offense: 1 QB, 1 RB, 5 OL, 1 TE, 3 WR — WR/TE/OL on same line; QB and RB behind center
FORMATION_OFFENSE = [
    ["WR", "WR", "TE", "LT", "LG", "C", "RG", "RT", "WR"],   # row 1: 3 WR + TE + 5 OL
    ["", "", "", "", "QB", "", "", "", ""],                   # row 2: QB behind center
    ["", "", "", "", "RB", "", "", "", ""],                   # row 3: 1 RB
]
# Defense: 4-3 — 2 CB, 4 DL, 1 MLB (ILB), 2 OLB, 2 S
FORMATION_DEFENSE = [
    ["CB", "S", "S", "CB"],                       # secondary
    ["OLB", "ILB", "OLB"],                        # LBs (ILB shown as MLB in UI)
    ["DE", "DT", "NT", "DE"],                     # 4 linemen
]
FORMATION_SPECIAL = [["K", "P", "LS"]]
# Display label for formation (e.g. ILB -> MLB in 4-3 view)
FORMATION_DEFENSE_LABELS: Dict[str, str] = {"ILB": "MLB"}

CLASS_LABELS = {1: "Fr", 2: "So", 3: "Jr", 4: "Sr"}

# Age-appropriate height (inches) and weight (lbs) for high school — no 300+ lb 14-year-olds
# (age -> (height_lo, height_hi, weight_lo, weight_hi))
HS_AGE_HEIGHT_WEIGHT: Dict[int, tuple[int, int, int, int]] = {
    14: (64, 70, 140, 220),
    15: (65, 71, 150, 240),
    16: (66, 72, 160, 260),
    17: (67, 73, 170, 280),
    18: (68, 74, 180, 300),
}

# Arm length is stored in inches; scale to 0-99 for position-fit formula: (inches - LO) / (HI - LO) * 99
ARM_LENGTH_INCHES_RANGE: tuple[int, int] = (28, 36)

# Trainable attributes: each has a current value and a _cap (ceiling). Non-trainable: height, weight, age, arm_length.
TRAINABLE_ATTRIBUTES: tuple[str, ...] = (
    "speed", "acceleration", "lateral_quickness", "vision",
    "lower_body_strength", "upper_body_strength",
    "vertical_jump", "broad_jump",
    "kick_power", "arm_strength", "run_block", "pass_rush", "pass_protection", "scrambling",
    "short_accuracy", "mid_accuracy", "deep_accuracy", "throw_under_pressure",
    "ball_security", "catching", "route_running",
    "tackling", "coverage", "block_shedding", "pursuit",
    "kick_accuracy", "familiarity",
)

# Practice focus options: (key, display label). Each focus has position/attribute-specific impacts below.
OFFENSE_PRACTICE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("strength_conditioning", "Strength & Conditioning"),
    ("pass_game", "Pass Game"),
    ("run_game", "Run Game"),
    ("screen_quick", "Screen & Quick Game"),
    ("red_zone", "Red Zone"),
    ("play_action", "Play Action"),
    ("two_minute", "Two-Minute / Tempo"),
    ("balanced", "Balanced"),
)
DEFENSE_PRACTICE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("strength_conditioning", "Strength & Conditioning"),
    ("pass_rush", "Pass Rush"),
    ("takeaways", "Take-aways"),
    ("zone_coverage", "Zone Coverage"),
    ("man_coverage", "Man Coverage"),
    ("stopping_rush", "Stopping the Rush"),
    ("blitz_packages", "Blitz Packages"),
    ("third_down", "Third Down"),
    ("balanced", "Balanced"),
)

# For each focus key: list of (attribute, positions_tuple, rate). Only positions in the tuple get that attribute.
# Rate is 1.0 primary, 0.5–0.8 secondary. Engine looks up by unit (offense vs defense).
_OL = ("LT", "LG", "C", "RG", "RT")
_QB = ("QB",)
_RB_FB = ("RB", "FB")
_WR_TE = ("WR", "TE")
_SKILL = ("QB", "RB", "FB", "WR", "TE")
_OFF = ("QB", "RB", "FB", "WR", "TE", "LT", "LG", "C", "RG", "RT")
_DL = ("DE", "DT", "NT")
_LB = ("OLB", "ILB")
_DB = ("CB", "S")
_DEF = ("DE", "DT", "NT", "OLB", "ILB", "CB", "S")

OFFENSE_PRACTICE_ATTRIBUTES: Dict[str, list[tuple[str, tuple[str, ...], float]]] = {
    "strength_conditioning": [
        ("speed", _OFF, 1.0),
        ("acceleration", _OFF, 1.0),
        ("lateral_quickness", _OFF, 1.0),
        ("lower_body_strength", _OFF, 1.0),
        ("upper_body_strength", _OFF, 1.0),
        ("vertical_jump", _OFF, 0.8),
        ("broad_jump", _OFF, 0.8),
    ],
    "pass_game": [
        ("short_accuracy", _QB, 1.0),
        ("mid_accuracy", _QB, 1.0),
        ("deep_accuracy", _QB, 1.0),
        ("throw_under_pressure", _QB, 1.0),
        ("arm_strength", _QB, 0.9),
        ("vision", _QB, 0.7),
        ("catching", _WR_TE + ("RB",), 1.0),
        ("route_running", _WR_TE, 1.0),
        ("pass_protection", _OL, 1.0),
        ("familiarity", _OFF, 0.5),
    ],
    "run_game": [
        ("run_block", _OL + ("FB", "TE"), 1.0),
        ("ball_security", _RB_FB + ("WR", "TE"), 1.0),
        ("vision", _RB_FB + _QB, 0.9),
        ("lower_body_strength", _OL + _RB_FB, 0.8),
        ("scrambling", _QB, 0.8),
        ("familiarity", _OFF, 0.5),
    ],
    "screen_quick": [
        ("short_accuracy", _QB, 1.0),
        ("lateral_quickness", _SKILL, 1.0),
        ("catching", _WR_TE + ("RB",), 1.0),
        ("route_running", _WR_TE, 0.8),
        ("run_block", _OL, 0.7),
        ("vision", _QB + ("RB",), 0.6),
    ],
    "red_zone": [
        ("short_accuracy", _QB, 1.0),
        ("throw_under_pressure", _QB, 0.9),
        ("run_block", _OL + ("FB", "TE"), 0.9),
        ("ball_security", _RB_FB, 0.9),
        ("catching", _WR_TE + ("RB",), 0.9),
        ("vertical_jump", _WR_TE, 0.6),
    ],
    "play_action": [
        ("mid_accuracy", _QB, 1.0),
        ("deep_accuracy", _QB, 0.9),
        ("vision", _QB, 1.0),
        ("run_block", _OL, 0.9),
        ("route_running", _WR_TE, 0.8),
        ("familiarity", _OFF, 0.5),
    ],
    "two_minute": [
        ("short_accuracy", _QB, 1.0),
        ("catching", _WR_TE + ("RB",), 0.9),
        ("speed", _SKILL, 0.8),
        ("acceleration", _SKILL, 0.8),
        ("pass_protection", _OL, 0.7),
        ("familiarity", _OFF, 0.6),
    ],
    "balanced": [
        ("speed", _OFF, 0.6),
        ("acceleration", _OFF, 0.6),
        ("short_accuracy", _QB, 0.6),
        ("mid_accuracy", _QB, 0.6),
        ("catching", _WR_TE + ("RB",), 0.6),
        ("route_running", _WR_TE, 0.6),
        ("run_block", _OL + ("FB", "TE"), 0.6),
        ("pass_protection", _OL, 0.6),
        ("ball_security", _RB_FB, 0.5),
        ("familiarity", _OFF, 0.5),
    ],
}

DEFENSE_PRACTICE_ATTRIBUTES: Dict[str, list[tuple[str, tuple[str, ...], float]]] = {
    "strength_conditioning": [
        ("speed", _DEF, 1.0),
        ("acceleration", _DEF, 1.0),
        ("lateral_quickness", _DEF, 1.0),
        ("lower_body_strength", _DEF, 1.0),
        ("upper_body_strength", _DEF, 1.0),
        ("vertical_jump", _DEF, 0.8),
        ("broad_jump", _DEF, 0.8),
    ],
    "pass_rush": [
        ("pass_rush", _DL + ("OLB",), 1.0),
        ("block_shedding", _DL + _LB, 1.0),
        ("speed", ("DE", "OLB"), 0.8),
        ("acceleration", ("DE", "OLB"), 0.8),
        ("upper_body_strength", _DL, 0.7),
        ("lower_body_strength", _DL, 0.7),
    ],
    "takeaways": [
        ("coverage", _DB + _LB, 1.0),
        ("tackling", _DEF, 1.0),
        ("pursuit", _DEF, 1.0),
        ("vision", _DB + ("ILB",), 0.8),
        ("vertical_jump", _DB, 0.5),
    ],
    "zone_coverage": [
        ("coverage", _DB + _LB, 1.0),
        ("vision", _DB + ("ILB",), 1.0),
        ("pursuit", _DEF, 0.8),
        ("tackling", _DB + _LB, 0.7),
    ],
    "man_coverage": [
        ("coverage", _DB, 1.0),
        ("speed", _DB, 0.9),
        ("acceleration", _DB, 0.9),
        ("lateral_quickness", _DB, 1.0),
        ("tackling", _DB, 0.6),
    ],
    "stopping_rush": [
        ("tackling", _DEF, 1.0),
        ("block_shedding", _DL + _LB, 1.0),
        ("lower_body_strength", _DL + ("ILB", "NT"), 0.9),
        ("upper_body_strength", _DL, 0.8),
        ("pursuit", _LB + _DB, 0.8),
    ],
    "blitz_packages": [
        ("pass_rush", _LB + ("DE",), 1.0),
        ("speed", ("OLB", "ILB", "S"), 0.9),
        ("pursuit", _LB, 0.9),
        ("block_shedding", _LB, 0.8),
        ("tackling", _LB + _DB, 0.6),
    ],
    "third_down": [
        ("pass_rush", _DL + ("OLB",), 0.9),
        ("coverage", _DB + _LB, 0.9),
        ("block_shedding", _DL + _LB, 0.7),
        ("pursuit", _DEF, 0.7),
        ("vision", _DB + ("ILB",), 0.6),
    ],
    "balanced": [
        ("pass_rush", _DL + ("OLB",), 0.5),
        ("coverage", _DB + _LB, 0.5),
        ("tackling", _DEF, 0.5),
        ("block_shedding", _DL + _LB, 0.5),
        ("pursuit", _DEF, 0.5),
        ("speed", _DEF, 0.4),
        ("lower_body_strength", _DL + ("ILB", "NT"), 0.4),
    ],
}

PRACTICE_FOCUS_DEFAULT = "balanced"
OFFENSE_FOCUS_KEYS = tuple(k for k, _ in OFFENSE_PRACTICE_OPTIONS)
DEFENSE_FOCUS_KEYS = tuple(k for k, _ in DEFENSE_PRACTICE_OPTIONS)

# Build fit: acceptable weight-per-inch (lbs/in) range per position. Used to scale potential so
# players with wrong body types (e.g. 274 lb WR) get low potential at that position.
# Ranges are (wpi_min, wpi_max); typical: WR/CB ~2.0-2.4, RB ~2.2-2.6, OL/DL ~3.2-4.2.
POSITION_WPI_RANGE: Dict[str, tuple[float, float]] = {
    "QB": (2.2, 2.9),
    "RB": (2.1, 2.7),
    "FB": (2.7, 3.7),
    "WR": (1.8, 2.5),
    "TE": (2.5, 3.4),
    "LT": (3.0, 4.3),
    "LG": (3.0, 4.3),
    "C": (2.9, 4.2),
    "RG": (3.0, 4.3),
    "RT": (3.0, 4.3),
    "DE": (2.7, 3.6),
    "DT": (3.0, 4.1),
    "NT": (3.2, 4.5),
    "OLB": (2.3, 3.1),
    "ILB": (2.5, 3.3),
    "CB": (1.8, 2.5),
    "S": (1.9, 2.7),
    "K": (1.9, 2.7),
    "P": (1.9, 2.7),
    "LS": (2.7, 3.7),
}

# Position potential: which attributes matter for "fit" at that position. Weights sum to 1.0.
# arm_length is in inches (28-36); scaled to 0-99 in position-fit logic. No overall_base.
POSITION_POTENTIAL_WEIGHTS: Dict[str, Dict[str, float]] = {
    "QB": {"arm_strength": 0.18, "vision": 0.14, "scrambling": 0.12, "short_accuracy": 0.10, "mid_accuracy": 0.10, "deep_accuracy": 0.08, "throw_under_pressure": 0.08, "speed": 0.08, "acceleration": 0.08, "upper_body_strength": 0.04, "lower_body_strength": 0.04},
    "RB": {"speed": 0.16, "acceleration": 0.16, "vision": 0.12, "lower_body_strength": 0.12, "ball_security": 0.10, "catching": 0.08, "vertical_jump": 0.06, "lateral_quickness": 0.10, "upper_body_strength": 0.04},
    "FB": {"lower_body_strength": 0.20, "run_block": 0.20, "upper_body_strength": 0.14, "ball_security": 0.08, "arm_length": 0.06, "speed": 0.10, "vision": 0.10},
    "WR": {"speed": 0.16, "acceleration": 0.16, "catching": 0.14, "route_running": 0.12, "lateral_quickness": 0.12, "vision": 0.08, "vertical_jump": 0.06, "upper_body_strength": 0.04, "lower_body_strength": 0.04},
    "TE": {"upper_body_strength": 0.14, "run_block": 0.14, "catching": 0.14, "route_running": 0.08, "pass_protection": 0.08, "arm_length": 0.06, "speed": 0.10, "vision": 0.10, "lower_body_strength": 0.08},
    "LT": {"pass_protection": 0.22, "run_block": 0.22, "arm_length": 0.14, "lower_body_strength": 0.14, "upper_body_strength": 0.14},
    "LG": {"run_block": 0.22, "pass_protection": 0.22, "arm_length": 0.14, "lower_body_strength": 0.14, "upper_body_strength": 0.14},
    "C": {"run_block": 0.22, "pass_protection": 0.22, "arm_length": 0.12, "lower_body_strength": 0.12, "upper_body_strength": 0.12, "vision": 0.08},
    "RG": {"run_block": 0.22, "pass_protection": 0.22, "arm_length": 0.14, "lower_body_strength": 0.14, "upper_body_strength": 0.14},
    "RT": {"pass_protection": 0.22, "run_block": 0.22, "arm_length": 0.14, "lower_body_strength": 0.14, "upper_body_strength": 0.14},
    "DE": {"pass_rush": 0.18, "arm_length": 0.12, "block_shedding": 0.12, "lower_body_strength": 0.14, "upper_body_strength": 0.14, "speed": 0.10, "acceleration": 0.10},
    "DT": {"lower_body_strength": 0.16, "upper_body_strength": 0.16, "pass_rush": 0.18, "block_shedding": 0.10, "tackling": 0.10, "pursuit": 0.10, "vision": 0.08, "arm_length": 0.08},
    "NT": {"lower_body_strength": 0.28, "upper_body_strength": 0.22, "pass_rush": 0.08, "block_shedding": 0.08, "tackling": 0.12, "pursuit": 0.10, "vision": 0.06, "arm_length": 0.06},
    "OLB": {"speed": 0.14, "pass_rush": 0.14, "tackling": 0.12, "block_shedding": 0.10, "pursuit": 0.10, "lateral_quickness": 0.10, "lower_body_strength": 0.10, "upper_body_strength": 0.10, "vision": 0.06},
    "ILB": {"vision": 0.16, "tackling": 0.14, "pursuit": 0.12, "block_shedding": 0.10, "lower_body_strength": 0.12, "upper_body_strength": 0.10, "speed": 0.10, "lateral_quickness": 0.10},
    "CB": {"speed": 0.18, "acceleration": 0.18, "coverage": 0.16, "lateral_quickness": 0.14, "tackling": 0.08, "vertical_jump": 0.04, "vision": 0.06, "upper_body_strength": 0.04},
    "S": {"speed": 0.14, "vision": 0.14, "coverage": 0.14, "tackling": 0.12, "pursuit": 0.10, "lateral_quickness": 0.10, "vertical_jump": 0.04, "upper_body_strength": 0.04, "lower_body_strength": 0.04},
    "K": {"kick_power": 0.36, "kick_accuracy": 0.32, "speed": 0.16, "acceleration": 0.16},
    "P": {"kick_power": 0.32, "kick_accuracy": 0.28, "speed": 0.20, "acceleration": 0.20},
    "LS": {"upper_body_strength": 0.18, "lower_body_strength": 0.18, "arm_strength": 0.16, "vision": 0.16, "tackling": 0.10, "lateral_quickness": 0.10, "speed": 0.06, "arm_length": 0.06},
}

# Roster position counts per level (must sum to ROSTER_SIZE_*)
# High school 30, college 40, pro 53
ROSTER_POSITION_COUNTS: Dict[str, list[tuple[str, int]]] = {
    "high_school": [
        ("QB", 2), ("RB", 2), ("FB", 1), ("WR", 3), ("TE", 2),
        ("LT", 1), ("LG", 1), ("C", 1), ("RG", 1), ("RT", 1),
        ("DE", 2), ("DT", 1), ("NT", 1), ("OLB", 2), ("ILB", 2), ("CB", 2), ("S", 2),
        ("K", 1), ("P", 1), ("LS", 1),
    ],
    "college": [
        ("QB", 3), ("RB", 3), ("FB", 1), ("WR", 4), ("TE", 2),
        ("LT", 2), ("LG", 1), ("C", 2), ("RG", 1), ("RT", 2),
        ("DE", 3), ("DT", 2), ("NT", 1), ("OLB", 3), ("ILB", 2), ("CB", 3), ("S", 3),
        ("K", 1), ("P", 1), ("LS", 1),
    ],
    "professional": [
        ("QB", 3), ("RB", 5), ("FB", 1), ("WR", 6), ("TE", 3),
        ("LT", 2), ("LG", 2), ("C", 2), ("RG", 2), ("RT", 2),
        ("DE", 4), ("DT", 3), ("NT", 1), ("OLB", 4), ("ILB", 3), ("CB", 4), ("S", 4),
        ("K", 1), ("P", 1), ("LS", 1),
    ],
}

# Order to fill high-school roster slots: most important positions first, specialists last
HS_POSITION_FILL_ORDER: list[tuple[str, int]] = [
    ("QB", 2), ("RB", 2), ("C", 1), ("DE", 2), ("WR", 3), ("CB", 2),
    ("FB", 1), ("TE", 2), ("LT", 1), ("LG", 1), ("RG", 1), ("RT", 1),
    ("DT", 1), ("NT", 1), ("OLB", 2), ("ILB", 2), ("S", 2),
    ("K", 1), ("P", 1), ("LS", 1),
]

# High school: 10 divisions named after US regions
HIGH_SCHOOL_DIVISION_NAMES = [
    "Northeast",
    "Southeast",
    "Midwest",
    "Texas",
    "Great Plains",
    "Mountain West",
    "Pacific Northwest",
    "California",
    "Southwest",
    "Sun Belt",
]

# College: D1, D2, D3
COLLEGE_DIVISION_NAMES = ["D1", "D2", "D3"]

# Pro: single division
PRO_DIVISION_NAMES = ["NFL"]

# Procedural team names: [City] [Mascot]
CITIES = [
    "Lincoln", "Springfield", "Riverside", "Franklin", "Clinton",
    "Madison", "Arlington", "Georgetown", "Salem", "Manchester",
    "Aurora", "Dover", "Lexington", "Cleveland", "Jackson",
    "Columbus", "Huntington", "Charleston", "Richmond", "Portland",
    "Oakland", "Phoenix", "Denver", "Seattle", "Austin",
    "Nashville", "Memphis", "Atlanta", "Miami", "Dallas",
    "Tulsa", "Birmingham", "Louisville", "Indianapolis", "Milwaukee",
    "Detroit", "Chicago", "Minneapolis", "Kansas City", "St. Louis",
    "New Orleans", "Tampa", "Orlando", "Charlotte", "Raleigh",
    "Pittsburgh", "Philadelphia", "Boston", "Buffalo", "Baltimore",
]

# Player name generation: [First] [Last]
FIRST_NAMES = [
    "James", "Michael", "Robert", "David", "William", "John", "Chris", "Marcus", "Anthony", "Daniel",
    "Matthew", "Joshua", "Andrew", "Joseph", "Ryan", "Brandon", "Tyler", "Kevin", "Brian", "Jason",
    "Derek", "Jordan", "Aaron", "Adam", "Zach", "Jake", "Nick", "Sam", "Ben", "Luke",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Wilson", "Moore",
    "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson", "Robinson", "Clark",
    "Lewis", "Lee", "Walker", "Hall", "Allen", "Young", "King", "Wright", "Scott", "Green",
]

MASCOTS = [
    "Eagles", "Tigers", "Bears", "Wolves", "Panthers",
    "Lions", "Hawks", "Falcons", "Cougars", "Wildcats",
    "Bulldogs", "Mustangs", "Broncos", "Ravens", "Cardinals",
    "Warriors", "Titans", "Spartans", "Vikings", "Knights",
    "Thunder", "Storm", "Blaze", "Crusaders", "Raiders",
    "Rangers", "Rebels", "Trojans", "Hornets", "Jaguars",
]
