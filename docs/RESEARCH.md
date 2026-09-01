# Bannerlord asset-pipeline research

Research date: 2026-09-01.

## Local, read-only findings

Expected root:

`C:\Program Files (x86)\Steam\steamapps\common\Mount & Blade II Bannerlord`

- Installation found; `package_info.txt` reports `PC@v1.3.4`.
- Shipping launcher found under `bin\Win64_Shipping_Client`.
- Modding Kit editor build found under `bin\Win64_Shipping_wEditor`.
- Official `modding_resources\skeletons\human_skeleton.fbx` found.
- Native module asset packages found. They were not opened, copied, extracted, or modified.
- Blender was not found on `PATH` or in its standard Program Files directory during the initial audit.

The application reproduces only these allowlisted existence/version checks. It does not crawl or ingest game assets.

## Authoritative constraints used

TaleWorlds' official [Asset Naming Conventions](https://moddocs.bannerlord.com/asset-management/asset-types/asset_naming_conventions/) document establishes:

- geometry sources such as FBX are imported and grouped by mesh name;
- LODs use `.lodN` (or `_lodN`) suffixes;
- a mesh uses one material and multi-material geometry becomes submeshes;
- materials referenced by geometry are not created automatically;
- physics meshes use the `bo_` prefix;
- split skeleton/mesh workflows require matching hierarchies;
- hard-coded bone suffix indices start at zero, are unique, and stay below the bone count.

The official [Animations](https://moddocs.bannerlord.com/asset-management/asset-types/animations/) page documents a maximum supported bone count of 64 and recommends exporting skeleton plus mesh for first-time rig setup.

The official [Meshes](https://moddocs.bannerlord.com/asset-management/asset-types/meshes/) page describes MetaMesh LOD grouping and default LOD distances of 15, 22.5, 30, 50, 70, 130, and 210 metres. It does not prescribe universal triangle budgets, so this project's targets remain configurable policy.

The official [Material Editor](https://moddocs.bannerlord.com/editor/resource-editors/material_editor/) page requires the Skinning vertex-layout option for skinned meshes, describes the metallic PBR texture channels, and exposes recompute-tangent handling.

The official [Adding and Overriding Assets](https://moddocs.bannerlord.com/asset-management/asset-types/overriding_assets/) page documents `Assets`, `AssetSources`, `AssetPackages`, `EmAssetPackages`, `DsAssetPackages`, and `RuntimeDataCache`; packed client assets are generated through the supported editor workflow.

The official [Asset Management](https://moddocs.bannerlord.com/asset-management/) FAQ says the Modding Kit must match the game version and be installed on the same drive. The Resource Browser/editor is therefore the final source of truth for import acceptance.

The official [Weapon Smithing & Crafting Pieces](https://moddocs.bannerlord.com/asset-management/weapon_smithing/) page says weapon-part pivots should be at the numeric center and parts positioned at world origin, with dimensions and behavior configured in crafting XML. This supports a distinct rigid weapon path rather than applying humanoid skinning to every weapon.

## Evidence vs policy

| Rule | Status |
| --- | --- |
| `.lodN` naming | Officially documented |
| One material per mesh/submesh | Officially documented |
| Bone suffix index rules | Officially documented |
| 64-bone ceiling | Officially documented |
| Weapon-part centered pivot/world origin | Officially documented |
| Default triangle targets | Project policy; configurable |
| Four influences per vertex | MVP interoperability policy; not asserted as engine law |
| Metre scale heuristic | Project assumption; warning only |
| Automatic clipping safety | Not established; requires animation tests |
