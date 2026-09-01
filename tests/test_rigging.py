import json
from pathlib import Path

import numpy as np
import trimesh

from bannerlord_model_forge.rigging.base import RiggingRequest
from bannerlord_model_forge.rigging.reference_transfer import (
    ReferenceWeightTransferBackend,
    normalize_and_limit,
)
from bannerlord_model_forge.rigging.weapon import WeaponRiggingBackend


def test_normalize_and_limit_is_deterministic() -> None:
    result = normalize_and_limit({"c": 0.1, "a": 0.6, "b": 0.2, "d": 0.05, "e": 0.05}, 4)
    assert list(result) == ["a", "b", "c", "d"]
    assert abs(sum(result.values()) - 1.0) < 1e-7


def test_reference_transfer_outputs_normalized_weights(tmp_path: Path) -> None:
    mesh = trimesh.Trimesh(
        vertices=np.asarray([[0.01, 0, 0], [0.99, 0, 0]]),
        faces=np.asarray([[0, 1, 1]]),
        process=False,
    )
    manifest = tmp_path / "reference.json"
    manifest.write_text(
        json.dumps(
            {
                "bones": ["root_0", "tip_1"],
                "vertices": [[0, 0, 0], [1, 0, 0]],
                "weights": [{"root_0": 1}, {"tip_1": 0.75, "root_0": 0.25}],
            }
        ),
        encoding="utf-8",
    )

    result = ReferenceWeightTransferBackend().rig(
        RiggingRequest(mesh, tmp_path / "out", reference_manifest=manifest)
    )

    assert result.status == "weights_transferred"
    assert result.confidence > 0.8
    payload = json.loads(result.weights_path.read_text(encoding="utf-8"))
    assert payload["weights"][0] == {"root_0": 1.0}
    assert abs(sum(payload["weights"][1].values()) - 1.0) < 1e-7


def test_weapon_default_is_rigid_and_optional_bone_is_one_weight(tmp_path: Path) -> None:
    mesh = trimesh.creation.box()
    backend = WeaponRiggingBackend()
    rigid = backend.rig(RiggingRequest(mesh, tmp_path / "rigid"))
    skinned = backend.rig(RiggingRequest(mesh, tmp_path / "skinned", rigid_bone="weapon_0"))

    assert rigid.status == "rigid_asset_no_skinning"
    assert rigid.metadata_path.is_file()
    assert skinned.status == "rigid_weights_generated"
    payload = json.loads(skinned.weights_path.read_text(encoding="utf-8"))
    assert payload["max_influences"] == 1
    assert all(row == {"weapon_0": 1.0} for row in payload["weights"])
