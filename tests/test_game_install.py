from pathlib import Path

from bannerlord_model_forge.game_install import inspect_game_install


def test_read_only_install_detection(tmp_path: Path) -> None:
    (tmp_path / "bin" / "Win64_Shipping_wEditor").mkdir(parents=True)
    skeleton = tmp_path / "modding_resources" / "skeletons" / "human_skeleton.fbx"
    skeleton.parent.mkdir(parents=True)
    skeleton.write_bytes(b"reference")
    package = tmp_path / "package_info.txt"
    package.write_text("Environment: PC@v9.8.7\n", encoding="utf-8")
    before = package.read_bytes()

    result = inspect_game_install(tmp_path)

    assert result.version == "v9.8.7"
    assert result.editor_found
    assert result.human_skeleton_found
    assert package.read_bytes() == before
