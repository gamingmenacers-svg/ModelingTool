from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import trimesh

from ..models import RiggingResult


@dataclass(frozen=True)
class RiggingRequest:
    mesh: trimesh.Trimesh
    output_dir: Path
    reference_manifest: Path | None = None
    max_influences: int = 4
    rigid_bone: str | None = None
    asset_kind: str = "body"


class RiggingBackend(ABC):
    @abstractmethod
    def rig(self, request: RiggingRequest) -> RiggingResult:
        """Return an honest result including confidence and manual exceptions."""


class ManualRiggingBackend(RiggingBackend):
    def rig(self, request: RiggingRequest) -> RiggingResult:
        return RiggingResult(
            status="manual_reference_required",
            confidence=0.0,
            method="none",
            warnings=[
                "No weighted, legally usable reference surface was supplied, so automatic skinning was not attempted.",
                "The detected official human skeleton defines bones but does not by itself provide trustworthy clothing weights.",
                "Supply a close-fitting weighted template and test deformation in the Bannerlord Modding Kit.",
            ],
        )
