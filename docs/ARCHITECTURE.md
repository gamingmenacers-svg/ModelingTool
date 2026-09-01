# Architecture and backend tradeoffs

## Chosen stack

The MVP uses Python 3.11+, Tk/TkDND for the Windows desktop UI, `trimesh`/NumPy for geometry, `fast-simplification` for quadric decimation, and Pillow for dependency-light previews. Core processing is UI-independent and available from `bmf`, which makes it deterministic and testable.

## Why Blender remains optional but important

Blender is mature at FBX import/export, armatures, data transfer, modifiers, and background automation. It is the safest practical backend for the later fully assembled skinned-FBX stage. Its downsides are a large installation, version-sensitive Python API, startup cost, and GPL process-boundary/licensing considerations. The app therefore calls a user-installed Blender as a separate process and does not embed or redistribute Blender.

The Blender bridge converts FBX to GLB in an isolated output job. Native formats never require Blender. It can export rigid weapon FBX directly and can bind a tested weight sidecar to an explicitly supplied skeleton FBX. The latter remains provisional until deformation poses are tested; it never invents armature transforms.

## Evaluated non-Blender options

| Option | Strength | Limitation / decision |
| --- | --- | --- |
| `trimesh` + `fast-simplification` | MIT-compatible, lightweight, deterministic mesh analysis and QEM simplification | Does not provide a production FBX/skeletal authoring pipeline; selected for the core vertical slice |
| Assimp / `pyassimp` | Broad importer, permissive BSD core | Windows native packaging and FBX fidelity vary; unsuitable as the only beginner-safe rig/export path |
| Open3D | Strong geometry algorithms | Large dependency and limited skeletal/FBX authoring; unnecessary for MVP |
| MeshLab / PyMeshLab | Mature cleanup and remeshing | GPL integration/distribution and skeletal limitations; not selected |
| Autodesk FBX SDK | Native FBX support | Proprietary SDK terms and no automatic rigging solution; not selected |
| Direct TPAC writers | Could bypass editor | Unofficial/reverse-engineered and risks compatibility/IP mistakes; explicitly rejected |

## Rigging interface

`RiggingBackend` isolates rigging policy from import/optimization. The first concrete armour backend transfers normalized weights from a user-supplied/licensed, aligned reference surface via deterministic nearest-vertex matching. Confidence falls with the 95th-percentile reference distance. It does not hallucinate skeleton transforms.

The weapon backend defaults to a rigid Bannerlord item record. An explicit one-bone weight map exists only for exceptional animated/skinned weapon templates. Both paths force Modding Kit testing.

## Future production stages

1. Define a documented reference bundle format containing license/provenance, skeleton FBX, reference surface, weights, scale, and allowed asset categories.
2. Add alignment landmarks and cage/surface barycentric transfer, not just nearest vertices.
3. Automate Blender deformation poses and render clipping/weight-heatmaps.
4. Extend the existing skinned-FBX bridge with deterministic deformation-pose acceptance tests and LOD weight transfer.
5. Stage a user-owned module template outside `Program Files`, then let the user import it through the matching Modding Kit.
