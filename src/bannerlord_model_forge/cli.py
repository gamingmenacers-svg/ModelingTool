from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import PRESETS, project_root
from .game_install import inspect_game_install
from .pipeline import run_pipeline
from .sample import create_sample


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmf", description="Prepare a model non-destructively for Bannerlord review."
    )
    parser.add_argument("source", nargs="?", type=Path, help="OBJ, GLB/GLTF, PLY, STL, or FBX model")
    parser.add_argument("--preset", choices=PRESETS, default="body")
    parser.add_argument("--target", type=int, help="Override the preset triangle target")
    parser.add_argument("--output-root", type=Path, help="Generated output root")
    parser.add_argument("--reference", type=Path, help="Licensed weighted-reference JSON manifest")
    parser.add_argument("--weapon-bone", help="Exceptional rigid one-bone skin; ordinary weapons should omit this")
    parser.add_argument("--weapon-skeleton", type=Path, help="Skeleton FBX for the exceptional one-bone weapon skin")
    parser.add_argument("--sample", action="store_true", help="Generate and process the original training model")
    parser.add_argument("--inspect-game", action="store_true", help="Print read-only local install information and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.inspect_game:
        print(json.dumps(inspect_game_install().to_dict(), indent=2))
        return 0
    source = args.source
    if args.sample:
        source = create_sample(project_root() / "work" / "samples" / "training_armour.glb")
    if source is None:
        print("error: provide a source model or use --sample", file=sys.stderr)
        return 2
    try:
        result = run_pipeline(
            source=source,
            preset_key=args.preset,
            triangle_target=args.target,
            output_root=args.output_root,
            reference_manifest=args.reference,
            weapon_bone=args.weapon_bone,
            weapon_skeleton=args.weapon_skeleton,
            progress=lambda message: print(f"[forge] {message}"),
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "before_triangles": result.before.triangles,
                "after_triangles": result.after.triangles,
                "lod_triangles": [item.triangles for item in result.lod_stats],
                "visible_loss": result.quality.visible_loss,
                "rigging_status": result.rigging.status,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
