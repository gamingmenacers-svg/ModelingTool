# Bannerlord Model Forge — product and technical specification

## Product promise

Bannerlord Model Forge is a Windows desktop assistant for people who have a generated 3D armour, clothing, or weapon model but do not know Blender, retopology, rigging, or weight painting. It must turn an opaque art task into a guided pipeline with evidence, warnings, and a reversible manual exception path.

The application is non-destructive. It reads the selected model and an allowlisted subset of the local Bannerlord installation, then writes only beneath this project's `output` folder (or an explicitly selected test output root). It never installs into `Program Files`, changes a module, or overwrites the source model.

## MVP user journey

1. Drop an OBJ, GLB/GLTF, FBX, PLY, or STL file, or use the generated training model.
2. Choose Helmet, Body armour/clothing, Pauldrons, Gloves/bracers, Cape, Skirt/tassets, Boots/greaves, Shield, or Weapon. Advanced controls stay hidden.
3. Select **Analyze and prepare**.
4. Orbit and zoom the model in the Rig Inspector, toggle its Bannerlord skeleton and wireframe, inspect piece-relevant bones and weight heatmaps, then review before/after statistics, images, LODs, JSON, and the plain-English report.
5. If armour has no licensed weighted reference, receive an explicit reference-required result instead of invented weights. If the asset is an ordinary weapon, receive a rigid-item setup record; one-bone skinning is an explicit exceptional option.
6. Complete FBX/material/physics/item configuration and animation tests through the Bannerlord Modding Kit.

## Functional scope

- Native import: OBJ, GLB/GLTF, PLY, and STL through `trimesh`.
- Optional FBX import: isolated headless Blender conversion. Missing Blender produces actionable setup guidance.
- Analysis: triangle/vertex/component/material counts, bounds, dimensions, transforms, winding, watertightness, normals, UV presence, and discoverable texture references.
- Deterministic cleanup: degenerate/duplicate face removal, unreferenced-vertex removal, precision-bounded vertex merging, and normal repair.
- Optimization: quadric-error simplification to a configurable policy target.
- LODs: decreasing configurable ratios and Bannerlord `.lodN` names.
- Quality report: deterministic sampled geometric deviation, normal change estimate, and low/moderate/high visible-loss classification.
- Armour rigging: prefer a legally usable close-fitting reference weight field; otherwise create explicitly provisional, piece-filtered bone-proximity weights against the locally installed skeleton. Cap/normalize influences, expose heatmaps and distance-derived confidence, and export a clearly named provisional skinned FBX for visual tests.
- Weapon preparation: default to Bannerlord's rigid item/crafting workflow; validate scale and centered origin. Optionally emit a one-bone weight map only when the user names a target bone for an exceptional skinned weapon.
- Output: GLB review bundle, OBJ base/LOD files, preview PNGs, rigging/setup JSON, validation Markdown/JSON, rigid weapon FBX when Blender is available, and skinned FBX when a matching legal skeleton and weight reference are supplied.

## Explicit non-goals for the MVP

- No extraction, decompilation, copying, or redistribution of proprietary game assets.
- No claim that provisional geometric weights make an arbitrary generated garment production-ready.
- No automatic install into a Bannerlord module.
- No TPAC writing. TaleWorlds' supported Modding Kit remains the authoritative compiler/importer.
- No automatic material recreation, collision authoring, cloth simulation, item XML balancing, or animation acceptance testing.
- No proof of clipping safety from a static mesh.

## Assumptions

- Model units are treated as metres for scale heuristics, but this is a warning-level assumption and never silently rescales the asset.
- Triangle targets are conservative product policy defaults, not documented hard engine limits.
- Four weights per vertex is the MVP interoperability policy for transferred weight maps, not claimed as a verified Bannerlord engine maximum.
- The official Modding Kit's `human_skeleton.fbx`, when present, may be referenced read-only on the user's machine. It is never copied or committed.
- A skeleton alone is insufficient for high-quality clothing weights; a close-fitting weighted surface is required.
- Ordinary melee/ranged weapon meshes are rigid item assets. “Rigging a weapon” normally means correct origin/grip/holster/body/item setup rather than humanoid deformation skinning.

## Acceptance criteria

- A generated sample completes end to end without changing the source hash or game directory.
- The prepared triangle count is at or below the requested target when simplification is required.
- LOD triangle counts strictly decrease and artifact names use `.lodN`.
- Reports and previews exist and agree with programmatic statistics.
- Synthetic reference-transfer tests prove weight normalization, maximum influence enforcement, and confidence behavior.
- Weapon tests prove ordinary rigid setup output and explicit one-bone output.
- Missing Blender is reported without blocking native formats.
