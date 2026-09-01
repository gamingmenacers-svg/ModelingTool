# Bannerlord Model Forge

Bannerlord Model Forge is a focused Windows armour workstation for Mount & Blade II: Bannerlord. It displays generated models in an orbitable Rig Inspector, overlays the locally installed Bannerlord skeleton, prepares piece-specific geometry and weights, builds LODs, exports FBX, and produces a plain-English handoff report without requiring Blender knowledge.

It is intentionally honest about the hard part: arbitrary armour cannot be rigged reliably from a bare skeleton alone. The MVP transfers weights only from a close-fitting weighted reference you are legally allowed to use, reports confidence, and sends uncertain results to a manual Modding Kit review. Ordinary weapons use a rigid item workflow; exceptional one-bone weapon skinning is opt-in.

## Safety guarantees

- Your selected model is opened read-only and never overwritten.
- The Bannerlord install is inspected read-only at `C:\Program Files (x86)\Steam\steamapps\common\Mount & Blade II Bannerlord`.
- No game asset is copied, extracted, bundled, or redistributed.
- Every generated file is placed under this project's `output` folder.
- The app does not install a mod or write into `Program Files`.

## Start the desktop app

You need Windows, Python 3.11 or newer, and an internet connection for first-time dependency setup.

1. Open PowerShell in this project folder.
2. Run:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\scripts\Setup.ps1
   .\scripts\Start.ps1
   ```

3. Drop a model into the large box, or click **Use training sample**.
4. Choose the exact piece: helmet, torso clothing/armour, pauldrons, gloves/bracers, cape, skirt/tassets, boots/greaves, shield, or weapon.
5. Click **Analyze and prepare**.
6. Click **Open result folder** and start with `validation_report.md`.

### Double-clickable Windows executable

A packaged copy can be launched directly as `outputs\Bannerlord Model Forge.exe`; it does not require a terminal or a separate Python installation. Double-click the file, then drag a model into the window. Generated results appear in an `output` folder beside the executable.

To rebuild the executable after changing the source code:

```powershell
.\scripts\Build-Exe.ps1
```

Advanced settings are hidden by default. They expose the triangle target, an armour reference-weight manifest, and an exceptional rigid bone for a weapon template that truly expects skinning.

## Rig Inspector

The right side of the app is an interactive model and rig viewport:

- drag with the left mouse button to orbit;
- use the mouse wheel to zoom;
- switch between front, side, and three-quarter views;
- toggle wireframe and skeleton visibility;
- see the relevant bone region highlighted for the selected armour piece;
- select any weighted bone to display a per-vertex weight heatmap.

The app uses Bannerlord's locally installed human skeleton read-only. It generates visual overlay data and renders, but never copies or redistributes the FBX itself.

Rigging has three deliberately distinct confidence tiers:

1. **Reference-transferred weights:** preferred. A close-fitting licensed template supplies proven weights and its exact skeleton.
2. **Provisional piece-specific auto-weights:** when no reference exists, the app uses only bones relevant to the selected piece and calculates geometric bone-proximity weights. It exports a clearly named provisional skinned FBX and exposes every weight in the heatmap.
3. **Manual exception:** used when no trustworthy skeleton/alignment is available or diagnostics fail.

Provisional auto-weights are useful for a first visual fit, not a production-quality guarantee. Their confidence is capped and animation tests remain mandatory.

## What works without Blender

OBJ, GLB/GLTF, PLY, and STL can be inspected, cleaned, simplified, previewed, validated, and exported directly. The app generates:

- a prepared GLB and OBJ;
- decreasing `.lod1`, `.lod2`, and `.lod3` OBJ meshes when possible;
- a GLB review scene containing the named LODs;
- before/after preview PNGs;
- `validation_report.md` and `validation_report.json`;
- armour weights when a valid weighted-reference manifest is supplied;
- provisional piece-specific auto-weights and a provisional skinned FBX when the local Bannerlord skeleton and Blender are available;
- `weapon_setup.json` for the rigid weapon path; and
- a rigid weapon FBX when Blender is available, or a skinned armour/exceptional-weapon FBX when both weights and a matching skeleton are supplied.

FBX input needs Blender. If it is missing, install it with:

```powershell
.\scripts\Install-Blender.ps1
```

Restart the app afterward. The Blender bridge converts FBX into an isolated intermediate GLB; it never changes the FBX.

## Command-line use

Run the full generated sample:

```powershell
.\.venv\Scripts\bmf.exe --sample --preset body --target 1800
```

Process armour:

```powershell
.\.venv\Scripts\bmf.exe "D:\Models\my_armour.glb" --preset body
```

Process an ordinary rigid weapon:

```powershell
.\.venv\Scripts\bmf.exe "D:\Models\my_sword.obj" --preset weapon
```

Create exceptional one-bone weapon weights only when a known target template requires them:

```powershell
.\.venv\Scripts\bmf.exe "D:\Models\animated_weapon.glb" --preset weapon --weapon-bone "weapon_0" --weapon-skeleton "D:\References\weapon_rig.fbx"
```

Print the read-only game detection result:

```powershell
.\.venv\Scripts\bmf.exe --inspect-game
```

## Armour rigging reference format

The first testable backend accepts JSON containing an aligned reference surface and per-vertex weights:

```json
{
  "skeleton_fbx": "D:/References/my_legal_template_skeleton.fbx",
  "bones": ["root_0", "spine_1"],
  "vertices": [[0, 0, 0], [0, 0, 1]],
  "weights": [
    {"root_0": 1.0},
    {"spine_1": 0.8, "root_0": 0.2}
  ]
}
```

The app copies neither the manifest nor a game skeleton. It writes a new normalized `skin_weights.json` in the job output, limits influences to four, and scores confidence from reference distance. When `skeleton_fbx` is present and Blender is available, it also binds those groups to the supplied armature and exports a skinned FBX. Nearest-vertex transfer is only a defensible first version for aligned, close-fitting geometry; animation tests remain mandatory.

The installed Modding Kit includes an official `modding_resources\skeletons\human_skeleton.fbx`. The app detects it in place, but the skeleton contains no garment-specific quality guarantee. A future licensed reference bundle must include provenance, skeleton, surface, weights, and test poses.

## Final Bannerlord handoff

The MVP output is an interchange/staging bundle, not a claim of in-game readiness. For a real mod:

1. Review silhouette loss in both preview images.
2. Resolve every error and warning in the validation report.
3. For armour, obtain a legal weighted reference and verify deformation/clipping. For weapons, confirm centered origin/grip, scale, holster, and collision/body setup.
4. Export a correctly skinned FBX through the Blender backend or another trusted DCC workflow.
5. Put sources only in your own writable module staging area.
6. Use the matching Bannerlord Modding Kit Resource Browser to import the FBX, create matching materials, enable Skinning for armour, recompute tangents when needed, and compile/package the assets.
7. Test crouching, mounted poses, combat animations, extreme body shapes, weapon attacks, and holstering before release.

TaleWorlds' importer is the final authority. See [docs/RESEARCH.md](docs/RESEARCH.md) for verified constraints and sources, [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) for scope/assumptions, and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for backend tradeoffs.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Tests cover deterministic mesh processing, non-destructive source handling, LOD/output generation, skeleton validation, armour weight transfer, and rigid/one-bone weapon paths.

## Current limitations

- Native FBX parsing is deliberately not attempted; it routes through Blender.
- Reference-transferred skinned FBX export requires a matching skeleton path in the reference bundle; the app will not invent one.
- Proximity auto-weights are a reviewable fallback, not a replacement for a close-fitting weighted armour template.
- The viewport is a focused inspection/weighting workspace, not a general-purpose modelling replacement for every Blender operation.
- UV presence is checked, but overlap, texel density, tangent-space compatibility, and texture packing need deeper tooling.
- Quality loss is an efficient sampled approximation, not a rendered perceptual metric.
- Static geometry cannot prove animation clipping safety.
- Materials, cloth simulation, collision bodies, and module item/crafting XML still need Modding Kit decisions.
