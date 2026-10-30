> Source snapshot: independent adapters, host, tests and notes only.
> Private `runtime/` content (captured editor artifacts, Google imagery, cases,
> signatures and screenshots) is excluded. Retained editor requires separately
> supplied artifacts. Local dependency paths require configuration on another machine.
> No API credentials or property data are shipped.

# Local roof editor lab

## Current state — October 30, 2026

This section supersedes older restrictions and unfinished-work notes below.
User authorized the remaining save/export, correction bridge and expanded fitting work.
No reconstruction algorithm or frozen evaluator was changed. Only production frontend
`RoofInspection.tsx` and new `RoofBuilderBridge.tsx` connect the tools.

- [x] Google-backed cases: server draft recovery, named checkpoints, outgoing-draft
  recovery, signed v2 export/import, source/hash/expiry checks, ground reference restore.
- [x] Generated model -> editable independent faces -> signed corrected case -> original
  app preview/download in its projected frame with absolute EGM96 elevations.
- [x] Height fitting: concave outlines, base roofs containing dormers/folds, independent
  faces; preview, fixed XY, validity checks and one Undo/Redo.
- [x] Pure geometry/cache tests, browser source-case workflow and actual production
  bridge component pass. Production frontend build passes. No new Google calls.

Use port 5191 for the editor; port 5173 for production app. In the production roof
reconstruction panel choose **Edit generated roof**, then **Open roof builder**.
Matching cached imagery and height reference must already exist. Edit faces, export
**test case**, then **Import corrected case** in the original app. Returned correction
is shown separately; original automated reconstruction is not overwritten.

Source cases use `runtime/source-cases/`, never the permanent synthetic browser library.
Signed files currently reopen only on the same local installation with matching,
unexpired cached source. Expiry never extends. Downloaded external copies require
manual deletion by `expiresAt`; the app refuses expired imports. Raw native JSON
export stays disabled for source sessions because it drops source/expiry metadata.
Manual synthetic v1 cases retain their existing browser library and JSON export.

Fitting keeps current face heading. On roofs with details, only base roof parameters
are fitted; dormer/fold slopes remain manual. Insufficient support or invalid resulting
geometry is refused. Tests establish workflow and known synthetic geometry, not full
house accuracy or surveyed truth. Continuous height mesh remains **Later** and is not
part of this completed checklist. Benchmark ingestion/DXF adapter remains separate.

Resume: do not repeat completed work or start optional features automatically. Preserve
private runtime and all unrelated production changes. Reuse caches. No new property
acquisition, Aurora account changes, deployment, vendor publication or entitlement
bypass. Existing explicit Kimberly retry approval persists; no new calls were needed.
GitHub source branch is `codex/local-roof-editor-lab`; private runtime remains excluded.

Checks: `python3 source-case-checks.py`, `node source-case-flow-checks.cjs`,
`node height-fit-checks.mjs`, production-venv Python `height-data-checks.py` and
`model-handoff-checks.py`, `node model-bridge-flow-checks.cjs`,
`node height-expanded-checks.cjs` (also `--plane`, `--details`). Browser source/bridge
checks require disposable `LAB_PORT=5193 python3 source-case-test-server.py`; all
provider acquisition requests are blocked by their test runners. Run browser checks
serially. Live server restarted after final Python changes; no user tabs reloaded.


October 28, 2026. This is an isolated experiment using the captured Aurora CAD
1.1876.0 client bundle and its datamodel WebAssembly, unchanged. The surrounding
adapters, local library, host and tests are new code. The default view now mounts
captured Site menu, roof insert controls and property panels through their
existing state and React providers. This is not the complete Aurora application.

## Outcome

The tested manual roof workflow runs without Aurora servers. In a separate,
credential-free browser, the original engine with local interaction adapters initializes, builds a roof from
pointer input, reconstructs it during an internal-edge drag, accepts a pitch
edit, serializes its native design and reopens it from local storage.

This establishes technical feasibility for the tested client workflow only.
It does not establish licensing or patent clearance, complete feature parity,
real-house accuracy, or recovery of server-side software.

## Open and run

The current local server is at http://127.0.0.1:5191.
Open http://127.0.0.1:5191/?demo=1 for the generated synthetic example.
Open `/` for an empty editor. Use `/?prototype=1` for the earlier minimal host.
The server binds only to loopback.

From this directory:

```sh
python3 setup.py /private/tmp/aurora-cad-1.1876.0
python3 server.py
```

Setup verifies and retains the supplied files in `runtime/vendor`, so subsequent
starts do not depend on the temporary capture directory. It makes no downloads.
Vendor files, synthetic native designs, screenshots and probe reports are ignored
by Git. No product files in `/Users/chris/code/solar-designer` were changed.

Hover Roof in the Site menu, choose a roof tool, click corners and close on the
visible first point. Double-click a roof to enter roof editing. Select an edge
and change pitch or height in the property panel. Insert controls appear at the
bottom while editing a roof. Fold placement now uses roof-surface picking in 3D
through a local adapter; plan-view placement keeps the native path.
Escape leaves the current tool.

Save locally stores a named example in this browser's local storage. New example
preserves the current nonempty roof before opening an empty editor. Choose a
saved example and use Reopen saved. Export JSON downloads the native combined
design format (`format_version`, `site_json`, `system_json`). Browser storage is
not a backup; export examples that need to be retained.

## Verified checklist

- [x] Original artifact bytes verified before serving; no vendor code patches.
- [x] Ten native engine loading stages complete with local adapters.
- [x] Synthetic four-corner footprint creates four sloping faces.
- [x] First corner projects back to the clicked screen position within one pixel.
- [x] Native 2D and 3D rendering.
- [x] Pointer drag of an internal edge changes contributing eave heights while
  preserving the outer footprint and four faces.
- [x] One native undo restores source elevations within `1e-10 m` (observed error
  about `9e-16 m` in the final synthetic run).
- [x] Native selection plus visible pitch inspector changes one source pitch
  from 20 to 30 degrees.
- [x] Named local save and reopen preserve IDs, footprint, pitches, heights and
  face counts at `1e-9 m` comparison precision. Native serialization rounds tiny
  floating-point elevation differences.
- [x] No browser page errors or native CAD error events in the final verification.
- [x] Tested workflow requests only local HTML/CSS/adapter code, the captured
  CAD bundle and its datamodel WASM. No Aurora requests, credentials, paid data
  calls, deployments or remote design edits.

Additional verified workflows are tracked in `progress.md`. Flat-roof drawing, standalone face drawing and an L footprint now have local
save/reopen checks. More complex footprints, obstruction tools and other Site
menu entries still need independent end-to-end tests. Visible menus
alone do not establish support. The local experiment does not claim all Aurora
commands work.

## Repeatable verification

```sh
node probe.cjs --verify
node probe.cjs --demo --ui-fields
node probe.cjs --demo --ui-dormers
node probe.cjs --demo --ui-fold
node probe.cjs --prototype --verify
```

The probe uses the desktop bundled Playwright installation and a new, headless
Chrome profile, not the user's signed-in browser. Its routing rejects every
request outside the local host. The page also has a restrictive Content Security
Policy. No payment, authentication, subscription or feature-entitlement check
was patched, forged or removed; the tested engine accepted synthetic local data
through its existing public integration interface.

Probe output is retained in `runtime/probe.json`, with a screenshot in
`runtime/preview.png`. The generated demo is `runtime/demo-design.json`.
Passing runs also retain `runtime/verified-<interface>-<test>.json`, including
verification time and host source hashes. Failed runs retain `failure.json` and
`failure.png`; a generic report alone is not evidence of a passing test. The demo
is replaced only after roundtrip verification passes. These are development
evidence, not independent roof-accuracy benchmarks.

## Artifact identity

| Captured artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `cad-bundle.js` | 8,706,421 | `065f6e39575ec8b5bc15ddac809aa7178285e0a90852ebe46a04c16249dcfedb` |
| `datamodel-api-js.wasm` | 2,208,762 | `315646e459591552df145f90177d0a4ecc2a06ecb2c7278b2a5694cf4ac47fa4` |

Core design algorithms are also embedded in the original bundle. The original
host interface accepts data-provider, save, store, geodata, Google Maps and
computation-service bindings. Only the required manual-data and save adapters
were supplied in this milestone. No fake remote job results are returned.

Prior static traces remain in the preserved repository branch's
`docs/aurora-roof-feature-matrix.md`; its historical REA IDs are not retained in
the current REA process. The source artifact hash matches that investigation.
Current runtime claims come from the local browser probe, not static inference.

## Required next work / resume

1. Follow the verified checklist and resume point in `progress.md`. Next manual
   coverage: fold height interaction, complex junctions, multiple dormers/folds,
   and mixed vertical/sloping fold tools. Extend support only after testing.
2. Define Google/cached-imagery geodata adapters, coordinate scale and height
   datum, then verify imagery alignment before using real houses. Do not make
   paid calls without the user's separate budget authorization.
3. Keep source-derived imagery and geometry under their original expiry and
   privacy constraints. The current permanent browser library is for manual
   synthetic examples; do not silently put expiring Google-derived data there.
4. Export a provenance-bearing test-case package and establish what reference
   comparisons the reconstruction evaluator can consume. Native JSON is not
   automatically a DXF or an independently measured physical reference.

Server-side AI, shading, irradiance jobs, component databases and remote DXF
generation have not been recovered or replaced. Google APIs cannot be assumed
to implement those Aurora-specific computations. Keep this lab separate from
production reconstruction and its frozen evaluation plan.

## Frontend integration boundary

Captured public frontend assets remain private under ignored `runtime/frontend`.
The local loader registers a fixed set of captured chunks and mounts selected
component closures. It does not start Aurora's account application. Generic
query-client classes support a local metric-units cache; unknown metadata queries
fail explicitly. No Aurora API proxy is supplied.

`ui-provenance.json`, `runtime-provenance.json`, the capture manifest and derived
asset manifest retain source identities and extraction ranges. Seven duplicate
module IDs have byte-distinct chunk variants; fixed registration order and runtime
checks cover the tested paths, not every possible component combination. The
server verifies retained artifact hashes before serving them. Bootstrap/runtime
instrumentation is separate from the unchanged CAD bundle and WASM.

Server-backed AI, imagery, shading and remote exports remain unavailable. Google
address/imagery integration is not wired. Keep this private lab separate from
production and obtain licensing and patent advice before reuse or distribution;
technical feasibility does not establish permission.

## Fold pointer adapter

`fold-placement.js` corrects the demonstrated ground-plane mismatch for oblique
fold placement without rewriting retained artifacts. Four camera directions on
one synthetic roof pass placement and save/reopen; empty-space clicks discard
stale previews, and the 2D path still passes. Direct hip/shed dormers also pass
initial-shape save/reopen. See `fold-placement-notes.md`
for runtime observations, REA coverage limits, checks and remaining risks.


## Mixed roof details (October 29)

The local surface adapter now ignores walls generated by the current fold
preview, fixing vertical-fold self-occlusion while preserving committed-wall
blocking. `interaction-cases.cjs` tests 45°/90° folds, two folds, mixed dormers,
fold-height line dragging and an exterior-wall occluder. All six pass finite
face/wall geometry, footprint, undo/redo and reopen checks at 1e-7 m numeric
precision. See `progress.md` for repeatable commands and precise limits.

`integration-contract.md` records the next reference-export and cached-geodata
boundary. Those adapters are not implemented. This isolated lab remains separate
from the production roof studio on port 5173.


## L-shaped hosts and deletion

Interaction cases accept --concave instead of --demo to draw and reopen an L host
before testing details. Sloping/vertical folds and mixed dormers pass. A bounded
committed-surface fallback handles a vertical preview removing its own live host
collider. Known hole-bearing faces are excluded; courtyard/imported geometry is
unverified. See fold-placement-notes.md for mechanism and limits.

Keyboard Delete of folds/dormers restores original geometry and supports undo/redo
and reopen. Reports capture source hashes before execution and reject runs if
sources change before completion. See progress.md for current evidence.


## Foreign-roof occlusion

`node probe.cjs --demo --case=foreign-roof-blocks` authors two disjoint synthetic
roofs and verifies the foreign roof is physically frontmost before testing
pointer/click rejection. Both roofs retain geometry after reopen. This case
records undoRedo=false and does not establish arbitrary occluder support.
No adapter change was needed; inactive roofs expose derived building-face hits.


## Portable test-case export

Use Export test case to download a roof-lab-case/v1 JSON package. It includes
native model bytes, checksum, local XYZ faces/walls, known holes and exporter/
engine identity metadata. Native bytes can be replayed by the local loader;
Open test case accepts matching manual packages after validation. Existing Export JSON remains available.

These are unregistered manual comparison cases, not surveyed truth or files
accepted by the current DXF benchmark. Source lineage and world registration are
explicitly unverified. See integration-contract.md for schema boundaries.

Verification: `node probe.cjs --demo --export-case`, or add --export-case to a
supported draw/interaction case. Tests download the file, verify checksum and
geometry, preserve analytic hole fixtures, reject invalid geometry, then replay
the exact native payload and compare restored geometry. No external service used.


## Opening manual test cases

Use Open test case to choose this lab's manual v1 package (up to 20 MB). Schema,
engine identity, native format/checksum and geometry are checked before existing
work changes. Current nonempty work is saved first; the imported example gets a
new local identity and retains a one-hop source reference through saves/re-exports.

Imported saved examples survive refresh on the home page. New example still opens
empty, and Reopen saved restores the imported model. Further committed edits use the tab-local draft journal described below.
Use Save locally for a named checkpoint. Checksums provide integrity,
not author authentication. Registered/imagery-derived packages remain unsupported.


## Safe reopening and switching examples

Reopening a different saved example first saves the current nonempty roof example.
Reopening the active saved version preserves changed current geometry/name as a
separate '(recovery)' entry, then loads the saved checkpoint. Select that recovery
entry to recover those edits. Repeated unchanged reopens do not create duplicates.
Saving a recovery retains its recovery/import metadata. This protects explicit
navigation. Tab-local drafts also protect refresh; complete version history is not implemented.


## Tab-local draft recovery

Committed manual edits and name changes are journaled after roughly 1.2 seconds
of idle time. Drawing/placement previews, held pointer gestures and invalid roofs
are deferred. Refresh restores the latest matching-engine draft, including Undo
back to the saved baseline and deletion of the final roof. Named library saves
remain separate checkpoints. Save locally clears the journal after saving; explicit
New/Open/Reopen navigation pauses it and clears it after preserving current work.

Drafts live in sessionStorage for this tab. They are not file backups, cross-tab
sync or complete version history. Closing the tab may lose the draft; edits made
less than the idle interval before refresh may not be included. Use Save locally
and Export test case for longer retention. Storage failures show a status message
and retry after 15 seconds. Unsupported/malformed or different-engine draft records
are ignored at startup. No external or imagery-derived data is enabled by this feature.

Run `node probe.cjs --demo --drafts` for browser recovery checks; append --drafts
to supported draw/import workflows. Current verification status is in CONTINUE.md.


## Whole-roof height and stories

Select the whole roof to expose Height to roof base and Stories. Height raises
roof faces and attached dormers while retaining footprint and pitch. Stories is
coupled to roof elevation; it is not a metadata-only field. Native history commits
these inputs asynchronously. Wait for the edit to commit before Undo/Redo.

Verified on pitched, L and combined dormer/fold hosts through Undo/Redo and reopen:
`node probe.cjs --demo --roof-properties --drafts`, or use --concave / a supported
mixed-detail case. Roof-type conversion is covered below. Whole-roof Move is covered below. Explode is covered below.

Idle drafts use the native read-only export path, preserving roof-editing mode
and Redo. The normal save-preparation path could change modes/history and is now
reserved for explicit save/export operations. Expanded --drafts checks confirm
mode/Redo retention and refreshed geometry across six workflows. This integration
is tied to the retained engine version; do not replace it without re-verification.


## Pitched and flat roof conversion

Select the whole roof, then choose its pitched or flat icon beside Roof type.
Rectangle and L roofs have verified conversion, Undo/Redo and local reopening in
both states. Their flat result is one horizontal face with the original footprint.
Undo restores the original pitched geometry; re-pitching is checked for valid
sloping geometry without promising all prior pitches are automatically restored.

Roofs containing dormers or folds cannot be flattened by this native operation.
The lab now displays that explanation in its status region and leaves the roof
unchanged. It does not remove details automatically. Native informational messages
are displayed as text; actionable toast buttons/dismissal UI remain unsupported.

Checks: `node probe.cjs --demo --roof-type`, `--concave --roof-type`,
`--demo --case=dormer-and-fold --roof-type`, and
`--demo --case=fold-sloped-3d --roof-type`. Plain flat draft recovery also passes
`node probe.cjs --flat --drafts`. These are synthetic interaction checks.


## Moving a whole roof

Leave roof editing with Select / Esc, select the whole roof, choose Move, then
drag inside a roof face. Press Escape when finished. Whole-roof Move stays active
after each drag; committed moves now save as idle tab drafts without leaving it.
Held pointer gestures still defer draft writes.

Verified on plain and dormer/fold roofs in 2D/3D, plus an L roof in 2D. Every
roof/wall/detail vertex translates uniformly, with pitch, height, topology and IDs
retained. Undo/Redo, unedited Move cancellation, direct draft refresh and normal
save/reopen pass. Rotation, multiple selected roofs and mid-drag cancellation
remain unverified.

Run `node probe.cjs --demo --roof-move`, `--concave --roof-move`, or
`--demo --case=dormer-and-fold --roof-move`. Add `--move-3d` for oblique checks.
These are synthetic interaction/persistence checks, not surveyed accuracy tests.


## Exploding a roof into independent faces

Select the whole roof outside roof editing, then click Explode. It immediately
replaces the SmartRoof, dormers and folds with independent roof planes using new
IDs. Source roof-face polygons are retained in tested cases; parametric editing
relationships are removed. Use Undo to restore the source during the current
session. Export test case first if you need to keep that source separately.

Native building groups and wall polygons can change after Explode. It is not a
lossless building-envelope export. Observed synthetic results:

| Case | Output planes | Exported building groups | Exported wall polygons |
| --- | ---: | --- | --- |
| Plain pitched | 4 | 1 → 4 | 4 → 14 |
| L roof | 6 | 1 → 6 | 6 → 24 |
| Dormer + fold | 7 | 1 → 5 | 8 → 25 |
| Flat roof | 1 | 1 → 1 | 4 → 4 |
| Vertical fold | 4 | 1 → 4 | 5 → 17 |

All five pass Undo/Redo, idle-draft recovery and saved reopening. Source/native
roof polygons remain unchanged at 1e-7 m comparison tolerance; the resulting
wall geometry remains stable after reload. These cases have no courtyard holes.
They do not establish equivalent volumes, surveyed accuracy or DXF compatibility.

Run `node probe.cjs --demo --roof-explode`, `--concave --roof-explode`,
`--flat --roof-explode`, `--demo --case=dormer-and-fold --roof-explode`, or
`--demo --case=fold-vertical-3d --roof-explode`.


## Editing an individual generated face

After Explode, click a face and edit Height to roof base or Pitch in its inspector.
Verified on plain, L, mixed dormer/fold and flat source examples. Only the selected
source plane changes; other source planes retain their geometry. Generated native
building intersections/walls can still change as planes are edited.

Undo/Redo, tab draft refresh and Save/reopen retain edited geometry and displayed
height/pitch values. Inspector values can be rounded; entered height is an
absolute target. Independent-plane outline dragging is covered below.

Run `node probe.cjs --demo --roof-explode --plane-edit`; substitute --concave,
--flat, or add --case=dormer-and-fold with --demo for the other verified sources.


## Manual authoring help and outline reshaping

Open How to model in the header for the drawing/editing/details/Move/save/export
workflow. Selecting an independent face also displays an outline-editing hint.
Save current work before refreshing an existing tab to load these UI additions.

Select an independent face and drag an outline edge or white corner node directly.
No separate edit mode is needed. Native controls already provide this behavior;
the new host guidance makes it easier to discover. Tested handles reshape only
the selected source plane while retaining pitch and other source planes.

Seven source/handle combinations pass Undo/Redo, validity, draft refresh and saved
reopening: plain/L/dormer-fold edge and corner, plus flat corner. Run
`node probe.cjs --demo --roof-explode --plane-boundary`; add --corner for a vertex.
Use --concave, --flat --corner, or --demo --case=dormer-and-fold for other cases.
These are bounded synthetic checks; they do not establish every junction, courtyard
or dimension-editing workflow. Current development remains manual test-case work.


## Precise SmartRoof edges and corners

Double-click a SmartRoof to enter roof editing. Select an edge and edit its native
Length field to set a dimension in meters. Select a white corner for the new Roof
corner inspector. Enter a Plan angle and press Apply angle. The selected corner
stays fixed while one adjacent corner moves; the checkbox chooses the other side.
The smaller between-edge angle is used, including at concave outline corners.

Angle display rounds to two decimals. Fractional entries are retained in geometry;
pressing Apply without editing does not round the model or add history. Undo/Redo,
tab draft recovery and saved reopening are verified on plain, concave and detailed
roofs. Angle reads from live coordinates so Undo does not leave stale inspector
values. Existing native geometry code handles the edit.

Save current work and refresh an existing tab to load these host controls.
Run `node probe.cjs --demo --corner-angle`, `--concave --inner-corner --corner-angle`,
or `--demo --case=dormer-and-fold --corner-angle` for focused checks. Corner removal and midpoint insertion are covered below. Open-outline redrawing is not integrated.


## Removing a SmartRoof corner

While editing a SmartRoof, select a white corner and choose Remove corner in its
inspector. The selected corner disappears and its neighbors are joined, keeping
the outline closed. A surviving corner stays selected. Undo restores the removed
corner. Removal disables when three corners remain.

This host control reuses native ring-editing code. It is different from native
node deletion, which can reopen an outline for redrawing. Midpoint insertion is covered below. Outline edits rebuild roof geometry.
Corner-count controls disable on roofs with dormers or folds; finish the outline
first. Open-outline redrawing is not integrated.

Plain and L examples pass Undo/Redo, tab draft refresh and saved reopening.
Save work and refresh an existing tab to load the new control. Run
`node probe.cjs --demo --remove-corner` or `--concave --remove-corner` for checks.

## Adding a SmartRoof corner

While editing a SmartRoof, select one perimeter edge, then Add corner at midpoint.
The new white corner is selected. Drag it into place. The split edges inherit the
original pitch and height; the native engine rebuilds roof faces. Undo removes
the insertion or reverses the later drag separately.

Finish the outline before adding dormers or folds. Both Add corner and Remove
corner disable on roofs with those details. A mixed-detail reshape left the
native roof unconstructed, so these host commands now prevent that workflow;
they do not silently discard details. Existing angle and native detail controls
remain available. To change corner count, remove attached details first.

Plain and L roofs are the supported insertion fixtures. Focused checks use
`node probe.cjs --demo --add-corner` and `--concave --add-corner`. The detailed
fixture `--demo --case=dormer-and-fold --add-corner` checks the guard instead.
This host binding depends on ring primitives in the pinned native engine; it
adds no independent roof solver. Save work before refreshing to load controls.

## Setting an edge length

Edit the SmartRoof and select a perimeter edge. In the Length section, choose
which endpoint stays fixed, enter meters, then click outside the input to apply.
The circle in each icon marks the fixed end; the arrow marks the moving end.
Endpoint choices now have accessible names and hover labels. First/second refer
to the native edge's endpoint order, not screen left/right after rotating view.

Only one endpoint moves along the original edge direction. Other corners stay
fixed, so adjoining edge lengths and corner angles can change. This does not
resize an entire rectangular footprint. Undo/Redo restores the edit. Display
rounds to two decimals; explicit fractional values remain in native geometry.
Focusing and leaving an untouched input does not round the model or add history.

## Portable case names and worked manual example

Export test case now includes the example name and uses a readable name plus
case ID for its downloaded filename. Open test case restores that name. Original
v1 files without a name still open as Imported test case. Names support up to
500 characters; filename characters are normalized separately. Names are labels,
not authenticated provenance or part of the native geometry checksum.

A synthetic worked example lives at `runtime/manual-outline-first.roofcase.json`.
Open it with Open test case. It was drawn from blank, dimensioned through Length,
given a midpoint corner and reshaped by dragging, then given a gable dormer and a
sloping fold. Named save/reopen, file export, New example, file import and imported
save/refresh preserve its geometry. This is a local manual comparison example,
not a registered real house or a DXF benchmark reference.

Reproduce with `node probe.cjs --manual-case`. The probe uses a fresh isolated
browser and replaces that private runtime sample, not examples in your browser.
Finish the outline before adding dormers or folds. Corner-count controls remain
disabled afterward. Save your current work before refreshing to load updates.

## Fast Hip, Gable and Shed starters

Select the whole rectangular roof outside roof editing. Roof starter appears above
the native properties. Choose Hip, Gable or Shed, enter pitch, then Apply roof
starter. Turn starter 90° switches the gable ridge axis or cycles shed direction.
Turning keeps pitch; peak height can change with the span.
The form contains proposed preset settings; native properties/geometry show the
current roof after Undo or reopening. Hip has no directional turn.

Starters support closed rectangular outlines with four corners and equal
edge heights, before dormers or folds. They disable for other footprints and
roofs with details. Flat rectangles can be converted directly with a starter.
Existing footprint, source edges and edge heights stay fixed. All pitched faces
receive the chosen angle; gable/shed boundary edges use native vertical mode.
This is a bulk binding of native pitch settings, not a new reconstruction solver.
Undo/Redo handles each application or turn as one step. Enter pitch above 0° and
at most 80°. Applying unchanged settings does not add history.

Finish starters and outline edits before adding details. These controls do not
preserve mixed pre-existing face pitches: applying a starter replaces them with
the selected uniform pitch. Save a checkpoint first if you need that version.


The top Fit button now includes full roof height, dormers, folds and walls in
3D framing. It preserves native ground-based orbit and may leave extra margin.
Native 2D fitting remains in use. This host fix covers the top Fit button; internal
SDK focus shortcuts retain their original behavior. Preserve current work before
refreshing to load updates.

## Exact rectangular footprint dimensions

Select the whole SmartRoof rectangle outside roof editing, then use Footprint
size under Roof starter. Enter
Width and Depth in meters and choose Resize rectangle. Width follows the first
outline edge; depth follows its adjoining edge. Center and orientation stay fixed.
Source edge heights and pitches stay fixed; peak height can change with the span.
This resizes all four corners together. Native Length still edits one endpoint.

Use dimensions from 0.1 to 1000 m, before dormers/folds. Same rectangle/equal-height
restrictions as starters apply. Display rounds to millimeters. Untouched fields
retain exact underlying dimensions; Apply without edits does not quantize data
or add history. Each resize is one Undo/Redo step. Native CAD rebuilds the roof.

Worked preset examples are also available at
`runtime/manual-gable-details.roofcase.json` and
`runtime/manual-shed-details.roofcase.json`. Each starts from a rectangle, applies
the named starter, then adds a dormer and sloping fold before save/export/import.
The shed example places both details on one roof face. These are synthetic,
unregistered comparison models. Prior regenerated gable example is preserved in
`runtime/manual-example-history/`.


Synthetic background calibration (developer-only): run
`node input-manifest-checks.mjs`, then `node synthetic-underlay-probe.cjs` and
`node synthetic-underlay-probe.cjs --rotated` serially with the local server running.
Uses a pinned generated PNG in an isolated browser; proves native 2D/3D registration,
pixel-center controls, scale, rotation and removal without changing manual cases.
No real-image import or address integration is exposed. External-source lifetime
and storage gates remain in background-input-plan.md. Own CSP permits local Blob
fetches for the native decoder; no remote source is enabled.


### Google imagery preview for requested address

Open `http://127.0.0.1:5191/?google=kimberly` in a separate tab, or choose
**Address imagery**. This single-address preview uses Google Solar RGB for
[local test property]. Acquisition is explicit CLI only:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/chris/code/solar-designer/.venv/bin/python google-imagery.py
```

The existing server-side key stays outside browser code. The acquisition command
reuses its unexpired, checksum-matching local image; no acquisition occurs on page
reads, refresh, server startup, or heartbeat. Current implementation does not search
arbitrary addresses. It uses a read-only local parcel lookup, one Building Insights
request, one Data Layers request and one RGB download, without automatic retries.
No DSM/mask download or reconstruction runs in this step.

Raster is reprojected from its declared CRS into a local meter frame centered on
the matched building. Native image registration preserves north-up pixel-center
coordinates. Source capture date is October 17, 2023; this is not a current survey.
Source dates, original/derived hashes and transforms live in private ignored
`runtime/google-kimberly/manifest.json`, with imagery and preview capture alongside.
Routes and a 60-second server watcher purge expired owned files; startup checks
expiry, and stopped servers purge on next start. Browser exits the source session
on expiry, including tab resume. Source API permissions/attribution references:
https://developers.google.com/maps/documentation/solar/policies and
https://cloud.google.com/maps-platform/terms/maps-service-terms#20.-solar-api .

This is a **temporary manual-editing preview**, not the completed integration.
Saving, file import/export, clipboard copy/cut and drafts are disabled; edits reset
on refresh/New. Existing manual library and drafts are not loaded or modified.
Permanent source-aware cases and transfer from the other tool remain unfinished.
Actual live check: `node google-preview-check.cjs` (local cache reads only).
Synthetic lifecycle/trace checks: `node imagery-session-checks.cjs` (no Google calls).


### Find address and export formats

Use **Find address**, enter street/city/state/postal code, then Search. Select a
property with Load imagery, then Open image editor. Current editor remains open.
Local property records supply coordinates first. Other addresses use Google Geocoding
API, which must be enabled and permitted for the configured server key (or use
GOOGLE_GEOCODING_API_KEY). Solar API alone accepts coordinates, not address text.
Reference: https://developers.google.com/maps/documentation/geocoding/guides-v3/requests-geocoding .
Search and imagery calls may be billed; no request runs while typing or on heartbeat.
Solar imagery coverage varies by location; only precise geocodes are accepted.

**Export engine JSON** downloads raw native engine data. **Export test case** downloads
an editable package with native data, roof/wall geometry, metadata and checksums.
**Open test case** validates and reopens the latter package; it does not open an aerial
image or raw engine JSON. Existing manual work is preserved before loading a package.
These controls remain disabled in temporary Google source sessions. General source-
aware export is unfinished. Old single-address CLI instructions above are historical;
use Find address for explicit acquisition now. Live cache remains reusable.


Current scope is Phoenix-area properties in loaded local parcel data. Find address
is local-only: no Google Geocoding fallback on missing records or database errors.
Older fallback/Geocoding setup notes above are historical. Solar API acquisition stays
explicit after property selection; existing imagery is reused. Missing records show
coverage guidance; this is not a guarantee of complete metro-area address coverage.


### Height data and roof fit

In a Google image editor tab, expand Height data and choose Load heights. This
explicitly requests Google DSM/mask data if an unexpired matching cache is absent;
it may incur charges. No acquisition occurs on refresh or heartbeat. Source date
must match existing image date; source expiry is preserved, never renewed.

Show heights overlays sampled surface elevations as colored 3D points (not a raw
LiDAR survey). Ground elevation is estimated from non-roof DSM pixels and can be
adjusted under Height reference. Verify it before relying on modeled heights.

Select one whole four-corner SmartRoof without dormers/folds, then Preview roof fit.
Preview shows proposed eave heights/slopes and residuals without changing the model.
Apply fit commits one native edit; Undo restores it. Cancel leaves model unchanged.
The retained inspector's Fit to LIDAR button opens this same independent preview.
Standalone roof faces and complex/detailed roofs are not supported by this first fit.
XY outline/edge directions stay fixed; it does not discover missing faces or prove
physical accuracy. Samples near face boundaries are excluded; a roof mask and robust
regression reject unsupported/noisy fits. Ground-reference or geometry changes require
another preview. Google-derived saving/export remains disabled in temporary sessions.

Checks (synthetic only, no API requests):
`node height-fit-checks.mjs`, production venv Python `height-data-checks.py`, and
`node height-tools-checks.cjs` (or `--flat`). Live acquisition currently awaits explicit
user approval after automatic approval review rejected the external DSM/mask request.


Live Kimberly height integration is now verified after explicit acquisition approval.
Original mask nodata0 is handled as valid non-roof zero; acquired rasters cache before
processing. Display and one planar-patch fit/Undo/Redo pass using cached Google DSM.
This is not whole-house accuracy validation. Google supplies raster height map; current
view shows sampled XYZ points, not a continuous height mesh or original LiDAR returns.
Earlier pending-approval notices above are historical; necessary Kimberly runs approved.
