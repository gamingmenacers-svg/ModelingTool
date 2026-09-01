from __future__ import annotations

import json

from ..models import RiggingResult
from .base import RiggingBackend, RiggingRequest


class WeaponRiggingBackend(RiggingBackend):
    """Prepare ordinary rigid weapons or an explicit one-bone exceptional bind."""

    def rig(self, request: RiggingRequest) -> RiggingResult:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        center = ((request.mesh.bounds[0] + request.mesh.bounds[1]) / 2.0).tolist()
        setup_path = request.output_dir / "weapon_setup.json"
        setup = {
            "schema": 1,
            "mode": "one_bone_skin" if request.rigid_bone else "rigid_item",
            "dimensions_model_units": request.mesh.extents.tolist(),
            "bounds_center_model_units": center,
            "length_centimetres_if_units_are_metres": float(max(request.mesh.extents) * 100.0),
            "bannerlord_notes": [
                "Confirm the mesh pivot/origin and grip alignment in the Modding Kit.",
                "Configure weapon class, length, mass, damage, holster, and collision/body through your module XML and Resource Browser.",
                "Crafting pieces should have numeric-center pivots and sit at world origin per TaleWorlds documentation.",
            ],
        }
        setup_path.write_text(json.dumps(setup, indent=2), encoding="utf-8")
        if not request.rigid_bone:
            return RiggingResult(
                status="rigid_asset_no_skinning",
                confidence=0.85,
                method="bannerlord_rigid_item",
                warnings=[
                    "Ordinary Bannerlord weapons are rigid meshes configured and attached by the item/crafting workflow; humanoid deformation weights are normally inappropriate.",
                    "Grip/origin, holster alignment, physics body, and attacks must still be tested in the Modding Kit.",
                ],
                metadata_path=setup_path,
            )
        weights_path = request.output_dir / "skin_weights.json"
        weights = {
            "schema": 1,
            "method": "rigid_one_bone",
            "bones": [request.rigid_bone],
            "max_influences": 1,
            "weights": [{request.rigid_bone: 1.0} for _ in request.mesh.vertices],
        }
        weights_path.write_text(json.dumps(weights, indent=2), encoding="utf-8")
        return RiggingResult(
            status="rigid_weights_generated",
            confidence=0.9,
            method="rigid_one_bone",
            warnings=[
                "Use this exceptional one-bone bind only when your chosen weapon template actually expects a skinned/animated mesh.",
                "The bone name came from the user; compatibility cannot be proven without the target skeleton and an animation test.",
            ],
            weights_path=weights_path,
            metadata_path=setup_path,
        )
