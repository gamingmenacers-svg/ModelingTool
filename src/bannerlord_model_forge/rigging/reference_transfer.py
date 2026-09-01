from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..models import RiggingResult
from .base import RiggingBackend, RiggingRequest


def _nearest_indices(source: np.ndarray, reference: np.ndarray, chunk_size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    indices: list[np.ndarray] = []
    distances: list[np.ndarray] = []
    for start in range(0, len(source), chunk_size):
        block = source[start : start + chunk_size]
        delta = block[:, None, :] - reference[None, :, :]
        squared = np.einsum("ijk,ijk->ij", delta, delta)
        nearest = squared.argmin(axis=1)
        indices.append(nearest)
        distances.append(np.sqrt(squared[np.arange(len(block)), nearest]))
    return np.concatenate(indices), np.concatenate(distances)


def normalize_and_limit(weights: dict[str, float], max_influences: int) -> dict[str, float]:
    positive = [(name, float(value)) for name, value in weights.items() if float(value) > 0]
    positive.sort(key=lambda item: (-item[1], item[0]))
    chosen = positive[:max_influences]
    total = sum(value for _, value in chosen)
    if total <= 0:
        return {}
    return {name: round(value / total, 8) for name, value in chosen}


class ReferenceWeightTransferBackend(RiggingBackend):
    """Nearest-reference-vertex transfer for already aligned, close-fitting garments.

    This deliberately does not claim to solve skeleton placement. It transfers a
    user-supplied/licensed weight field and reports geometric confidence.
    """

    def rig(self, request: RiggingRequest) -> RiggingResult:
        manifest_path = request.reference_manifest
        if manifest_path is None or not manifest_path.is_file():
            from .base import ManualRiggingBackend

            return ManualRiggingBackend().rig(request)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        reference_vertices = np.asarray(data.get("vertices", []), dtype=float)
        reference_weights = data.get("weights", [])
        bones = [str(name) for name in data.get("bones", [])]
        if reference_vertices.ndim != 2 or reference_vertices.shape[1:] != (3,):
            raise ValueError("Reference manifest vertices must be an N x 3 array.")
        if len(reference_vertices) != len(reference_weights):
            raise ValueError("Reference vertices and weight rows must have equal length.")
        if not len(reference_vertices) or not bones:
            raise ValueError("Reference manifest must contain vertices, weights, and bones.")

        target_vertices = np.asarray(request.mesh.vertices, dtype=float)
        nearest, distances = _nearest_indices(target_vertices, reference_vertices)
        transferred = [
            normalize_and_limit(reference_weights[int(index)], request.max_influences)
            for index in nearest
        ]
        diagonal = max(float(np.linalg.norm(reference_vertices.max(axis=0) - reference_vertices.min(axis=0))), 1e-12)
        p95 = float(np.percentile(distances, 95)) / diagonal
        confidence = max(0.0, min(1.0, 1.0 - p95 / 0.08))
        status = "weights_transferred" if confidence >= 0.55 else "review_required"
        warnings = [
            "Nearest-reference transfer is reliable only when source and reference are aligned and close-fitting.",
            "Weights still require deformation and clipping tests in the Bannerlord Modding Kit.",
        ]
        if any(not row for row in transferred):
            warnings.append("At least one target vertex received no positive bone influence.")
            confidence *= 0.5

        request.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = request.output_dir / "skin_weights.json"
        payload = {
            "schema": 1,
            "method": "nearest_reference_vertex",
            "bones": bones,
            "max_influences": request.max_influences,
            "weights": transferred,
            "quality": {
                "mean_distance": float(distances.mean()),
                "p95_distance": float(np.percentile(distances, 95)),
                "reference_diagonal": diagonal,
            },
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return RiggingResult(
            status=status,
            confidence=round(confidence, 3),
            method="nearest_reference_vertex",
            warnings=warnings,
            weights_path=output_path,
        )
