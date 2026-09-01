from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from ..models import RiggingResult
from .base import RiggingBackend, RiggingRequest


def _distance_to_segments(points: np.ndarray, heads: np.ndarray, tails: np.ndarray) -> np.ndarray:
    segment = tails - heads
    denominator = np.einsum("ij,ij->i", segment, segment)
    denominator[denominator == 0] = 1e-12
    relative = points[:, None, :] - heads[None, :, :]
    amount = np.einsum("nbi,bi->nb", relative, segment) / denominator[None, :]
    amount = np.clip(amount, 0.0, 1.0)
    closest = heads[None, :, :] + amount[:, :, None] * segment[None, :, :]
    return np.linalg.norm(points[:, None, :] - closest, axis=2)


class SkeletonProximityRiggingBackend(RiggingBackend):
    """Low-confidence geometric fallback for aligned armour and an explicit skeleton."""

    def __init__(self, skeleton_data: Path, focus_patterns: tuple[str, ...]) -> None:
        self.skeleton_data = skeleton_data
        self.focus_patterns = tuple(pattern.lower() for pattern in focus_patterns)

    def rig(self, request: RiggingRequest) -> RiggingResult:
        data = json.loads(self.skeleton_data.read_text(encoding="utf-8"))
        records = list(data.get("bones", []))
        indexed = [record for record in records if re.search(r"_\d+$", str(record.get("name", "")))]
        focused = [
            record
            for record in indexed
            if not self.focus_patterns
            or any(pattern in str(record.get("name", "")).lower() for pattern in self.focus_patterns)
        ]
        if not focused:
            raise ValueError("No Bannerlord bones matched this armour-piece region.")
        heads = np.asarray([record["head"] for record in focused], dtype=float)
        tails = np.asarray([record["tail"] for record in focused], dtype=float)
        names = [str(record["name"]) for record in focused]
        vertices = np.asarray(request.mesh.vertices, dtype=float)
        influence_count = min(request.max_influences, len(focused))
        rows: list[dict[str, float]] = []
        nearest_distances: list[np.ndarray] = []
        chunk_size = 1024
        for start in range(0, len(vertices), chunk_size):
            distances = _distance_to_segments(vertices[start : start + chunk_size], heads, tails)
            order = np.argsort(distances, axis=1)[:, :influence_count]
            chosen = np.take_along_axis(distances, order, axis=1)
            scale = max(float(np.median(chosen[:, 0])), 1e-5)
            raw = np.exp(-chosen / (scale * 1.35))
            normalized = raw / np.maximum(raw.sum(axis=1, keepdims=True), 1e-12)
            for indices, values in zip(order, normalized):
                rows.append(
                    {
                        names[int(index)]: round(float(value), 8)
                        for index, value in zip(indices, values)
                        if float(value) > 1e-8
                    }
                )
            nearest_distances.append(chosen[:, 0])
        nearest = np.concatenate(nearest_distances)
        all_points = np.asarray(
            [point for record in indexed for point in (record["head"], record["tail"])],
            dtype=float,
        )
        skeleton_height = max(float(np.ptp(all_points, axis=0).max()), 1e-9)
        p95_ratio = float(np.percentile(nearest, 95)) / skeleton_height
        confidence = max(0.05, min(0.55, 0.55 - p95_ratio))
        request.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = request.output_dir / "skin_weights.json"
        payload = {
            "schema": 1,
            "method": "piece_specific_bone_proximity",
            "provisional": True,
            "asset_kind": request.asset_kind,
            "bones": [str(record["name"]) for record in indexed],
            "focused_bones": names,
            "max_influences": request.max_influences,
            "weights": rows,
            "quality": {
                "mean_nearest_bone_distance": float(nearest.mean()),
                "p95_nearest_bone_distance": float(np.percentile(nearest, 95)),
                "p95_distance_over_skeleton_height": p95_ratio,
            },
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return RiggingResult(
            status="provisional_auto_weights",
            confidence=round(confidence, 3),
            method="piece_specific_bone_proximity",
            warnings=[
                "These are provisional geometric weights, not reference-transferred production weights.",
                "Use the Rig Inspector heatmap and a close-fitting licensed reference before trusting deformation.",
                "Animation pose tests are mandatory; low confidence or visible separation requires manual correction.",
            ],
            weights_path=output_path,
        )
