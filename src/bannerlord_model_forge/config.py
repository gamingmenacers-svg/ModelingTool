from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


GAME_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Mount & Blade II Bannerlord"
)


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    triangle_target: int
    lod_ratios: tuple[float, ...]
    expected_height_m: tuple[float, float]
    rig_mode: str = "deform"
    skeleton_region: str = "full_body"
    guidance: str = "Transfer weights from a close-fitting licensed reference and test poses."


PRESETS: dict[str, Preset] = {
    "helmet": Preset(
        "helmet", "Helmet", 20_000, (0.55, 0.28, 0.12), (0.18, 0.55),
        skeleton_region="head_neck",
        guidance="Check head/neck clearance, eye line, hair, and extreme head rotation.",
    ),
    "body": Preset(
        "body", "Body armour / clothing", 50_000, (0.55, 0.28, 0.12), (0.65, 2.20),
        skeleton_region="torso_full_body",
        guidance="Prioritize shoulders, spine, waist, hips, armpits, and mounted/crouched poses.",
    ),
    "shoulders": Preset(
        "shoulders", "Pauldrons / shoulder armour", 18_000, (0.52, 0.25, 0.10), (0.12, 0.75),
        skeleton_region="shoulders_upper_arms",
        guidance="Test arm raise, two-handed attacks, shield poses, and pauldron/torso overlap.",
    ),
    "gloves": Preset(
        "gloves", "Gloves / bracers", 12_000, (0.50, 0.24, 0.10), (0.12, 0.55),
        skeleton_region="hands_forearms",
        guidance="Inspect wrist bending, finger coverage, weapon grips, and left/right symmetry.",
    ),
    "cape": Preset(
        "cape", "Cape / mantle", 24_000, (0.50, 0.23, 0.09), (0.40, 2.20),
        rig_mode="cloth",
        skeleton_region="neck_shoulders_back",
        guidance="Weight the fixed shoulder/neck zone, then configure vertex alpha and cloth collision in the Modding Kit.",
    ),
    "skirt": Preset(
        "skirt", "Skirt / tassets", 24_000, (0.50, 0.23, 0.09), (0.30, 1.35),
        rig_mode="cloth",
        skeleton_region="pelvis_legs",
        guidance="Test pelvis/leg weights, crouching, riding, steps, and optional cloth simulation anchors.",
    ),
    "boots": Preset(
        "boots", "Boots / greaves", 16_000, (0.50, 0.24, 0.10), (0.20, 0.85),
        skeleton_region="feet_lower_legs",
        guidance="Inspect ankle flex, knee clearance, foot contact, and left/right symmetry.",
    ),
    "shield": Preset(
        "shield", "Shield", 18_000, (0.50, 0.22, 0.09), (0.25, 1.80),
        rig_mode="rigid",
        skeleton_region="hand_attachment",
        guidance="Confirm grip/origin, hand alignment, collision body, holster, and block animations.",
    ),
    "weapon": Preset(
        "weapon", "Weapon", 18_000, (0.50, 0.22, 0.09), (0.20, 3.50),
        rig_mode="rigid",
        skeleton_region="hand_attachment",
        guidance="Confirm grip/origin, hand alignment, collision body, holster, and attack animations.",
    ),
}


BONE_REGION_PATTERNS: dict[str, tuple[str, ...]] = {
    "full_body": (),
    "head_neck": ("neck", "head", "spine2"),
    "torso_full_body": ("pelvis", "spine", "neck", "clavicle", "upperarm", "thigh"),
    "shoulders_upper_arms": ("spine2", "neck", "clavicle", "upperarm"),
    "hands_forearms": ("upperarm", "foretwist", "hand", "finger"),
    "neck_shoulders_back": ("spine", "neck", "clavicle", "upperarm"),
    "pelvis_legs": ("pelvis", "spine", "thigh", "calf"),
    "feet_lower_legs": ("thigh", "calf", "foot", "toe"),
    "hand_attachment": ("foretwist", "hand", "finger"),
}


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def default_output_root() -> Path:
    return project_root() / "output"
