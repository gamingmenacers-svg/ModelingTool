# Bannerlord Model Forge — full-suite roadmap

Research and architecture revision: 2026-09-03.

## Product promise

Forge accepts an FBX from an arbitrary DCC or marketplace, preserves the source, and carries each selected object through a visible, reversible pipeline toward a Bannerlord module. “Any FBX” means the intake layer diagnoses the file and gives the user a recoverable route forward. It does not mean that software can infer missing UV artwork, hidden body clearance, a weapon's intended grip, or good cloth topology with certainty.

The one-click path is allowed to end in one of three truthful states:

1. **Game-ready:** imported and compiled by the matching TaleWorlds Modding Kit, published into `AssetPackages`, and passed the required in-engine test set.
2. **Editor-ready:** correct staged FBX, material textures, names, weights, LODs, collision/cloth metadata, and module XML exist; supported Modding Kit import/publish is still required.
3. **Review required:** an automated result exists but one or more confidence gates need a human decision. The problem area is selected and visualized in the viewport.

## End-to-end workflow

| Stage | Automation | Blocking evidence |
| --- | --- | --- |
| Intake | Import FBX/GLB/OBJ, retain object/material hierarchy and embedded images, fingerprint source | At least one finite triangle mesh; importer diagnostics recorded |
| Separate | Outliner, viewport picking, connected-piece split, multi-select, delete/restore, semantic slot suggestion | Exactly the intended export piece or declared group is active |
| Normalize | PCA plus axis hypotheses, Z-up conversion, unit inference, slot envelope fit, left/right placement, origin/pivot policy | Model visibly aligns with the exact local Bannerlord rest skeleton; transform is reversible |
| Repair | Degenerates, duplicate faces/vertices, normals, winding, UV/tangent audit, optional remesh/retopo | No corrupt geometry; silhouette error remains below policy |
| Materials | Detect albedo/normal/metal/rough/AO, convert roughness to gloss, pack M/G/AO into Bannerlord specular RGB, assign documented suffixes | Every exported submesh has one declared `pbr_metallic` material and complete channel provenance |
| Fit | Body/slot clearance, cage or surface projection, symmetry, thickness preservation, adjacent-slot preview | Static intersections and implausible offsets are below policy |
| Rig | Weighted-reference barycentric transfer first; voxel/geodesic heat fallback; piece-specific bone filtering; rigid weapon/shield path | Known bone hierarchy, normalized/pruned influences, zero unweighted vertices, acceptable confidence |
| Paint | Bone heatmap, brush/add/subtract/smooth, lasso, mirror, lock bones, normalize/prune | Manual changes are undoable and validation updates live |
| Pose | Bannerlord action test set, linear-blend preview, clipping/volume-loss/weight-gradient analysis | Required slot poses reviewed; severe intersections and detached regions blocked |
| Cloth | Vertex-alpha paint, fixed-anchor validation, lower-poly simulation mesh generation, capsule/body preview | Alpha/anchor continuity, render/simulation clearance, and collision tests pass |
| Collision | Generate/edit `bo_` shapes, weapon/shield body selection, visual collision overlay | Named body exists and matches item behavior |
| LOD | Generate decreasing LODs, transfer weights/materials, preserve seams/hard edges, `.lodN` naming | Monotonic triangle reduction and per-LOD deformation/material checks pass |
| Package | Stage `SubModule.xml`, `AssetSources`, `Assets`, `ModuleData`, item/crafting XML, dependency/version metadata | IDs are unique, paths resolve, XML validates, source provenance recorded |
| Compile/test | Drive the supported Resource Browser workflow, create materials, set vertex layout, publish, launch test harness | TPAC/`AssetPackages` exists and automated screenshots/log checks complete |

## Rigging engines

The suite should choose the strongest available method per piece, not expose one misleading “AI rig” algorithm.

### 1. Reference-surface transfer — production default

- Ship no proprietary TaleWorlds body or armour data.
- Accept user-owned or redistributable reference bundles with provenance, exact skeleton, rest mesh, skin weights, body variant, allowed slots, and validation poses.
- Align by named landmarks, then transfer from closest triangle using barycentric weights rather than closest vertex.
- Add geodesic-aware smoothing, bone locks, left/right symmetry, influence pruning, and boundary preservation.

### 2. Volumetric/geodesic weights — fallback

- Voxelize the garment and rig, solve heat diffusion or geodesic distance through the volume, then project weights back to the surface.
- Restrict candidate bones by equipment slot.
- Use this for a strong first pass, but cap confidence until pose tests pass.

### 3. Rigid attachment — weapons and shields

- Preserve size unless the user supplies a physical target length.
- Centre crafting-piece pivots at numeric centre/world origin where the official workflow requires it.
- Provide hand/grip and holster sockets as explicit transforms; do not apply humanoid deformation weights by default.

### 4. Manual correction

- Weight painting and transform editing are part of the product, not an external escape hatch.
- Every automatic decision needs undo, before/after, confidence, and a reason.

## Official engine contract encoded by Forge

- Meshes in one geometry source are grouped by name; LODs use `.lodN` or `_lodN`.
- A mesh has one material. Multi-material polygons import as numbered submeshes, and materials are not automatically created from FBX definitions.
- New material content should use `pbr_metallic`. Packed specular channels are R metallic, G glossiness, B ambient occlusion, A translucency where relevant.
- Skinned materials enable Bump Map and Skinning; Skinning Precise is reserved for meshes where small important polygons justify it.
- Geometry/skeleton split files require matching bone hierarchies and unique zero-based `_<index>` bone suffixes. The documented skeleton limit is 64 bones.
- Bannerlord uses Z-up for animation export. Ignored imported skeleton roots use `_notused`.
- Cloth vertex alpha controls maximum movement. Zero-alpha vertices remain skinned anchors. Dense, double-sided, or layered render meshes should use a separate tightly fitting simulation mesh.
- Editable module sources live in `AssetSources`; derived editable assets in `Assets`; gameplay XML in `ModuleData`; published client content in `AssetPackages`.
- A source file merely placed in `AssetSources` is not published content. It must be imported and the module published through the supported editor workflow.

## Delivery increments

### 0.2 — trustworthy intake and alignment

- Reversible auto-fit against the exact local rig, including left/right placement.
- Unit/orientation/offset report and candidate comparison.
- Dynamic engine-readiness gates and machine-readable Modding Kit handoff manifest.
- Complete PBR texture inventory with visible channel previews.

### 0.3 — material compiler

- Extract embedded and adjacent textures from FBX.
- Semantic map detection with confidence and manual overrides.
- Normal-map convention switch, roughness-to-gloss conversion, M/G/AO packing, suffix rename, and lossless master copies.
- Live Bannerlord-style PBR viewport rather than base-colour-only shading.

### 0.4 — production weight transfer

- Versioned legal reference-bundle schema and importer.
- Landmark/cage fit, closest-triangle barycentric transfer, mirror/normalize/prune/smooth.
- GPU weight paint tools and per-bone locks.

### 0.5 — deformation lab

- Rest/idle/run/crouch/mount/attack/block pose suites loaded from user-local legal resources.
- Skinned animation preview, clipping heatmap, volume loss, discontinuity detection, and saved approvals.

### 0.6 — cloth, collision, and LOD lab

- Alpha painting and anchor diagnostics, simulation proxy generator, capsule editor, `bo_` collision helpers.
- Seam-aware LODs with weight/material transfer and per-LOD validation.

### 0.7 — module builder

- Guided item/armour/crafting XML generation, SubModule/project manifests, dependencies, localization stubs, unique ID checks.
- Staging remains outside the game directory until the user selects an owned module destination.

### 1.0 — supported editor bridge

- Version-matched Modding Kit launch/import/publish assistant, with resumable steps and screenshots/log capture.
- In-game test module and final evidence bundle.
- The suite may show **Game-ready** only after compile and test evidence exists.

## Acceptance standard

A release candidate must pass a corpus that covers centimetre/metre/millimetre FBX units; Y-up/Z-up and upside-down files; embedded, relative, and missing textures; multi-material and disconnected sets; already-skinned and unskinned meshes; helmets, torso armour, asymmetrical pauldrons, gloves, boots, skirts/capes, shields, and modular weapons. Golden tests compare transforms, texture channels, names, weight normalization, LOD monotonicity, XML schemas, non-destructive source hashes, and reproducible output.
