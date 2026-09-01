from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


PRESETS: dict[str, Preset] = {
    "helmet": Preset("helmet", "Helmet", 20_000, (0.55, 0.28, 0.12), (0.18, 0.55)),
    "body": Preset(
        "body", "Body armour / clothing", 50_000, (0.55, 0.28, 0.12), (0.65, 2.20)
    ),
    "gloves": Preset("gloves", "Gloves", 12_000, (0.50, 0.24, 0.10), (0.12, 0.55)),
    "boots": Preset("boots", "Boots", 16_000, (0.50, 0.24, 0.10), (0.20, 0.85)),
    "weapon": Preset("weapon", "Weapon", 18_000, (0.50, 0.22, 0.09), (0.20, 3.50)),
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_output_root() -> Path:
    return project_root() / "output"
