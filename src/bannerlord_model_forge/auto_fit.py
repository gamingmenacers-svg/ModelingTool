from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh


@dataclass(frozen=True)
class FitProfile:
    """A conservative Bannerlord bind-pose envelope, expressed in body heights."""

    centre: tuple[float, float, float]
    extents: tuple[float, float, float]
    primary_axis: int
    top_bottom_ratio: float = 1.0
    rigid: bool = False


@dataclass(frozen=True)
class AutoFitResult:
    transform: np.ndarray
    scale: float
    confidence: float
    target_centre: tuple[float, float, float]
    target_extents: tuple[float, float, float]
    placement: str
    note: str


# These are fitting envelopes, not engine limits. They scale from the exact local
# skeleton height so the operation remains deterministic if the source rig is
# re-exported with different units.
FIT_PROFILES: dict[str, FitProfile] = {
    "helmet": FitProfile((0.0, 0.00, 0.925), (0.20, 0.20, 0.23), 2, 0.72),
    "body": FitProfile((0.0, -0.015, 0.655), (0.50, 0.28, 0.53), 2, 1.22),
    "shoulders": FitProfile((0.0, -0.020, 0.775), (0.58, 0.27, 0.24), 0, 1.04),
    "gloves": FitProfile((0.0, -0.010, 0.615), (0.84, 0.18, 0.24), 0, 0.92),
    "cape": FitProfile((0.0, -0.090, 0.610), (0.48, 0.14, 0.69), 2, 0.55),
    "skirt": FitProfile((0.0, -0.010, 0.390), (0.39, 0.27, 0.49), 2, 0.62),
    "boots": FitProfile((0.0, -0.005, 0.185), (0.30, 0.25, 0.37), 2, 1.12),
    "shield": FitProfile((0.0, 0.0, 0.0), (0.48, 0.10, 0.58), 2, 1.0, True),
    "weapon": FitProfile((0.0, 0.0, 0.0), (0.08, 0.08, 0.75), 2, 1.0, True),
}


FIT_BONE_PATTERNS: dict[str, tuple[str, ...]] = {
    "helmet": ("neck", "head", "spine2"),
    "body": ("pelvis", "spine", "neck", "clavicle", "upperarm", "thigh"),
    "shoulders": ("spine2", "neck", "clavicle", "upperarm"),
    "gloves": ("upperarm", "foretwist", "hand", "finger"),
    "cape": ("spine", "neck", "clavicle", "upperarm"),
    "skirt": ("pelvis", "spine", "thigh", "calf"),
    "boots": ("thigh", "calf", "foot", "toe"),
}


FIT_BONE_RADII: tuple[tuple[str, float], ...] = (
    ("head", 0.070),
    ("neck", 0.047),
    ("clavicle", 0.060),
    ("upperarm", 0.050),
    ("foretwist", 0.043),
    ("hand", 0.050),
    ("finger", 0.025),
    ("pelvis", 0.115),
    ("spine2", 0.125),
    ("spine1", 0.130),
    ("spine", 0.115),
    ("thigh", 0.067),
    ("calf", 0.052),
    ("foot", 0.050),
    ("toe", 0.038),
)


def _robust_bounds(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(points) < 40:
        return points.min(axis=0), points.max(axis=0)
    return np.quantile(points, 0.01, axis=0), np.quantile(points, 0.99, axis=0)


def _skeleton_frame(path: Path) -> tuple[np.ndarray, float, list[dict[str, object]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = list(payload.get("bones", []))
    points = np.asarray(
        [value for record in records for value in (record.get("head"), record.get("tail")) if value],
        dtype=float,
    )
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 2:
        raise ValueError("The Bannerlord skeleton cache does not contain usable rest-pose points.")
    minimum, maximum = points.min(axis=0), points.max(axis=0)
    height = float(maximum[2] - minimum[2])
    if height <= 1e-8:
        raise ValueError("The Bannerlord skeleton cache has no measurable Z-up height.")
    # Bone orientation handles make the total Y bounds asymmetrical. The root
    # (the human pelvis in the official rig) is the stable body centreline.
    root = next((record for record in records if not record.get("parent") and record.get("head")), None)
    root_head = np.asarray(root["head"], dtype=float) if root else (minimum + maximum) * 0.5
    return np.asarray([root_head[0], root_head[1], minimum[2]], dtype=float), height, records


def _fit_segments(
    records: list[dict[str, object]], preset_key: str, skeleton_height: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    patterns = FIT_BONE_PATTERNS.get(preset_key, ())
    heads_by_name = {
        str(record.get("name", "")): np.asarray(record["head"], dtype=float)
        for record in records
        if record.get("head") is not None
    }
    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    radii: list[float] = []
    for record in records:
        name = str(record.get("name", ""))
        if patterns and not any(pattern in name.lower() for pattern in patterns):
            continue
        head_value = record.get("head")
        tail_value = record.get("tail")
        if head_value is None or tail_value is None:
            continue
        head = np.asarray(head_value, dtype=float)
        parent = heads_by_name.get(str(record.get("parent", "")))
        pairs.append((parent if parent is not None else head, head if parent is not None else np.asarray(tail_value, dtype=float)))
        radius_ratio = next((radius for pattern, radius in FIT_BONE_RADII if pattern in name.lower()), 0.045)
        radii.append(radius_ratio * skeleton_height)
    if not pairs:
        empty = np.empty((0, 3), dtype=float)
        return empty, empty, np.empty((0,), dtype=float)
    return np.asarray([pair[0] for pair in pairs]), np.asarray([pair[1] for pair in pairs]), np.asarray(radii)


def _mean_segment_distance(
    points: np.ndarray, heads: np.ndarray, tails: np.ndarray, radii: np.ndarray
) -> float:
    if not len(heads):
        return 0.0
    segment = tails - heads
    denominator = np.einsum("ij,ij->i", segment, segment)
    denominator[denominator < 1e-12] = 1e-12
    relative = points[:, None, :] - heads[None, :, :]
    amount = np.einsum("nbi,bi->nb", relative, segment) / denominator[None, :]
    amount = np.clip(amount, 0.0, 1.0)
    closest = heads[None, :, :] + amount[:, :, None] * segment[None, :, :]
    centreline_distance = np.linalg.norm(points[:, None, :] - closest, axis=2)
    nearest = np.abs(centreline_distance - radii[None, :]).min(axis=1)
    return float(np.mean(np.clip(nearest, 0.0, np.percentile(nearest, 90))))


def _profile_for_placement(profile: FitProfile, placement: str) -> FitProfile:
    placement = placement.lower()
    if placement not in {"auto", "centre", "left", "right"}:
        raise ValueError(f"Unknown placement: {placement}")
    if placement not in {"left", "right"}:
        return profile
    sign = -1.0 if placement == "left" else 1.0
    if profile is FIT_PROFILES["shoulders"]:
        return FitProfile((0.22 * sign, profile.centre[1], profile.centre[2]), (0.28, 0.25, 0.25), 0, profile.top_bottom_ratio)
    if profile is FIT_PROFILES["gloves"]:
        return FitProfile((0.37 * sign, profile.centre[1], profile.centre[2]), (0.17, 0.16, 0.25), 2, profile.top_bottom_ratio)
    if profile is FIT_PROFILES["boots"]:
        return FitProfile((0.075 * sign, profile.centre[1], profile.centre[2]), (0.15, 0.23, 0.38), 2, profile.top_bottom_ratio)
    return profile


def _section_ratio(points: np.ndarray) -> float:
    minimum, maximum = _robust_bounds(points)
    span = max(float(maximum[2] - minimum[2]), 1e-9)
    lower = points[points[:, 2] <= minimum[2] + span * 0.28]
    upper = points[points[:, 2] >= maximum[2] - span * 0.28]
    if len(lower) < 3 or len(upper) < 3:
        return 1.0

    def section_width(values: np.ndarray) -> float:
        lo, hi = _robust_bounds(values)
        return max(float((hi[0] - lo[0]) * (hi[1] - lo[1])), 1e-9)

    return section_width(upper) / section_width(lower)


def auto_fit_to_bannerlord(
    mesh: trimesh.Trimesh,
    skeleton_data: Path,
    preset_key: str,
    placement: str = "auto",
) -> AutoFitResult:
    """Orient, uniformly scale, and place one piece against the official rest rig.

    The solver considers every right-handed assignment of the mesh PCA axes. It
    matches the selected slot envelope, uses the top/bottom silhouette to resolve
    upside-down candidates, and always writes one reversible 4x4 transform.
    """

    if preset_key not in FIT_PROFILES:
        raise ValueError(f"No auto-fit profile exists for {preset_key!r}.")
    vertices = np.asarray(mesh.vertices, dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) < 4:
        raise ValueError("Auto-fit requires a mesh with at least four 3D vertices.")
    if not np.isfinite(vertices).all():
        raise ValueError("Auto-fit cannot process non-finite vertex coordinates.")

    origin, skeleton_height, skeleton_records = _skeleton_frame(skeleton_data)
    base_profile = FIT_PROFILES[preset_key]
    profile = _profile_for_placement(base_profile, placement)
    target_centre = origin + np.asarray(profile.centre, dtype=float) * skeleton_height
    target_extents = np.asarray(profile.extents, dtype=float) * skeleton_height

    source_min, source_max = _robust_bounds(vertices)
    source_centre = (source_min + source_max) * 0.5
    centred = vertices - source_centre
    pca_sample = centred if len(centred) <= 100_000 else centred[:: max(1, len(centred) // 100_000)]
    score_sample = centred if len(centred) <= 6_000 else centred[:: max(1, len(centred) // 6_000)]
    covariance = np.cov(pca_sample, rowvar=False)
    _eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvectors = eigenvectors[:, ::-1]
    segment_heads, segment_tails, segment_radii = _fit_segments(
        skeleton_records, preset_key, skeleton_height
    )

    candidates: list[tuple[float, np.ndarray, np.ndarray]] = []
    for permutation in itertools.permutations(range(3)):
        for signs in itertools.product((-1.0, 1.0), repeat=3):
            rotation = np.vstack(
                [signs[axis] * eigenvectors[:, permutation[axis]] for axis in range(3)]
            )
            if np.linalg.det(rotation) < 0.0:
                continue
            oriented = score_sample @ rotation.T
            lower, upper = _robust_bounds(oriented)
            extents = np.maximum(upper - lower, 1e-9)
            log_ratio = np.log(extents / np.maximum(target_extents, 1e-9))
            aspect_error = float(np.mean((log_ratio - log_ratio.mean()) ** 2))
            silhouette_error = abs(float(np.log(max(_section_ratio(oriented), 1e-9) / profile.top_bottom_ratio)))
            candidate_scale = (
                1.0
                if profile.rigid
                else float(target_extents[profile.primary_axis] / max(extents[profile.primary_axis], 1e-9))
            )
            placed = oriented * candidate_scale + target_centre
            bone_error = _mean_segment_distance(
                placed, segment_heads, segment_tails, segment_radii
            ) / skeleton_height
            # Resolve otherwise identical sign candidates by preferring the
            # smallest rotation from the authored orientation.
            rotation_cost = max(0.0, 3.0 - float(np.trace(rotation)))
            # Capsule-surface fit is the strongest semantic signal available
            # from the official rig: it distinguishes boots-at-the-head from
            # boots-at-the-feet even when both candidates have identical bounds.
            score = aspect_error + silhouette_error * 0.040 + bone_error * 18.0 + rotation_cost * 1e-5
            candidates.append((score, rotation, extents))
    if not candidates:
        raise RuntimeError("Auto-fit could not produce a right-handed orientation candidate.")
    candidates.sort(key=lambda value: value[0])
    best_score, rotation, oriented_extents = candidates[0]

    if profile.rigid:
        scale = 1.0
        note = "Centred at the documented rigid-item origin; size was preserved."
    else:
        axis = profile.primary_axis
        scale = float(target_extents[axis] / max(oriented_extents[axis], 1e-9))
        scale = float(np.clip(scale, 1e-5, 1e5))
        note = "Uniformly sized to the selected Bannerlord equipment-slot envelope."

    linear = rotation * scale
    translation = target_centre - linear @ source_centre
    transform = np.eye(4, dtype=float)
    transform[:3, :3] = linear
    transform[:3, 3] = translation

    second_distinct = next(
        (candidate[0] for candidate in candidates[1:] if not np.allclose(candidate[1], rotation)),
        best_score + 1.0,
    )
    separation = max(0.0, float(second_distinct - best_score))
    confidence = float(np.clip(0.88 - best_score * 0.35 + min(separation, 0.25), 0.20, 0.92))
    if placement == "auto" and preset_key in {"shoulders", "gloves", "boots"}:
        note += " Left/right is ambiguous; choose a side when fitting a single piece."
        confidence = min(confidence, 0.62)

    return AutoFitResult(
        transform=transform,
        scale=scale,
        confidence=round(confidence, 3),
        target_centre=tuple(float(value) for value in target_centre),
        target_extents=tuple(float(value) for value in target_extents),
        placement=placement,
        note=note,
    )
