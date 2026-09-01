from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MeshStats:
    vertices: int
    triangles: int
    components: int
    material_count: int
    bounds_min: list[float]
    bounds_max: list[float]
    dimensions: list[float]
    bounds_center: list[float]
    watertight: bool
    winding_consistent: bool
    has_vertex_normals: bool
    has_uv: bool
    has_tangents: bool
    texture_references: list[str] = field(default_factory=list)
    source_geometry_count: int = 1
    transform_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationItem:
    code: str
    level: str
    title: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class QualityMetrics:
    nearest_vertex_rms_percent_diagonal: float
    nearest_vertex_max_percent_diagonal: float
    mean_normal_change_degrees: float | None
    visible_loss: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiggingResult:
    status: str
    confidence: float
    method: str
    warnings: list[str] = field(default_factory=list)
    weights_path: Path | None = None
    metadata_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["weights_path"] = str(self.weights_path) if self.weights_path else None
        data["metadata_path"] = str(self.metadata_path) if self.metadata_path else None
        return data


@dataclass
class PipelineResult:
    source: Path
    preset_key: str
    output_dir: Path
    before: MeshStats
    after: MeshStats
    lod_stats: list[MeshStats]
    quality: QualityMetrics
    validation: list[ValidationItem]
    rigging: RiggingResult
    artifacts: dict[str, Path]
