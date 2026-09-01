from bannerlord_model_forge.validator import validate_skeleton_manifest, validate_weight_rows


def levels(items):
    return {item.code: item.level for item in items}


def test_skeleton_indices_and_count_pass() -> None:
    result = levels(validate_skeleton_manifest(["root_0", "spine_1", "hand_2"]))
    assert result == {"bone_count": "pass", "bone_names": "pass"}


def test_skeleton_duplicate_indices_fail() -> None:
    result = levels(validate_skeleton_manifest(["root_0", "spine_0"]))
    assert result["bone_names"] == "error"


def test_skeleton_over_64_fails() -> None:
    result = levels(validate_skeleton_manifest([f"bone_{index}" for index in range(65)]))
    assert result["bone_count"] == "error"


def test_weight_rows_validate_limits_normalization_and_names() -> None:
    valid = levels(validate_weight_rows(["root_0", "tip_1"], [{"root_0": 0.25, "tip_1": 0.75}], 4))
    invalid = levels(validate_weight_rows(["root_0"], [{"other_1": 0.4}], 4))
    assert valid["weights"] == "pass"
    assert invalid["weights"] == "error"
