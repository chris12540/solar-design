# Local editor progress and resume point

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


Updated October 29, 2026. This checklist covers the isolated local lab only.
Production reconstruction, benchmark branches and the paused heartbeat are unchanged.

## Completed

- [x] Default interface mounts captured Site menu, roof insert controls and
  selected roof, perimeter-edge, face, dormer and fold property views.
- [x] Flat roof: one horizontal face; standalone sloping face: one 20° face.
  Both survive local save/reopen with identical source geometry at 1e-9 m.
- [x] L-shaped footprint retains six corners and six faces after reopening;
  sum of projected face areas matches footprint within 1e-6 m². This is an
  aggregate area check, not proof of non-overlap or physical accuracy.
- [x] Perimeter-line drag changes footprint; undo restores original footprint,
  redo restores dragged geometry, and subsequent save/reopen passes.
- [x] Fold pitch input changes to 10° and derived slope refreshes to 2.1/12.
  Fold-boundary dragging now changes derived height, with footprint preserved
  and undo/redo/reopen checks. No numeric height field is provided by this panel.
- [x] Existing minimal interface remains available with `?prototype=1`.
- [x] Stable toolbar renders preserve hover menus while native selection updates.
- [x] Property selection follows selected supported object rather than a stale tab.
- [x] Local metric-unit metadata resolves without an Aurora API connection.
  Unknown queries fail explicitly.
- [x] Draw a four-corner pitched roof through visible Roof menu: four faces.
- [x] Drag an internal line: source elevations change, footprint remains fixed.
- [x] Internal-line redo restores dragged geometry at 1e-9 m comparison precision.
- [x] One undo restores heights within `1e-10 m`; observed error `8.88e-16 m`.
- [x] Original numeric pitch input changes native model to 28 degrees; derived
  slope updates to 6.4/12. Height input changes source edge to 3.5 m.
- [x] Direct gable, hip and shed dormer placement; each shape-control sequence
  passes hip/shed/gable with 3/1/2 faces. Final gable geometry after each sequence
  survives save/reopen at 1e-9 m precision. Direct hip and shed shapes also
  survive save/reopen before any shape changes (`--placement-only`).
- [x] Vertical-fold preview no longer blocks its own pointer via a generated
  wall; only current-preview-owned walls are skipped. Committed exterior-wall
  blocking has an explicit synthetic negative case.
- [x] Sloping (45°) and vertical (90°) folds pass 3D placement, undo/redo and reopen.
- [x] Two sloping folds retain six parent faces; a gable and hip dormer coexist.
  Undo removes only the last detail; redo restores it; reopen retains geometry.
- [x] Edited fold (10° pitch) and generated roof faces survive local save/reopen
  at 1e-9 m precision.
- [x] Place flat fold in plan view: one fold, zero pitch, five roof faces.
- [x] Moving from a valid 3D fold preview to empty canvas and clicking discards
  the preview and restores four original faces; stale preview is not committed.
- [x] Local fold-surface adapter fixes ground-plane pointer mismatch in 3D.
  Placement and save/reopen pass at horizontal camera angles 30°, 120°, 210°
  and 300° (35° elevation) on the synthetic host. Source artifact bytes unchanged.
  See `fold-placement-notes.md` for cause, evidence and adapter boundary.
- [x] Named save/reopen preserves source geometry at `1e-9 m` comparison precision.
- [x] Preserve passing per-workflow reports with timestamp and host source hashes.
  Promote generated demo only after all roundtrip assertions pass.

Every passing workflow checks page/native errors, unknown metadata queries and
external request attempts. All were empty in these synthetic runs. Browser route
blocking and local-only CSP remain enabled.

## Known limits

- Original 3D fold mismatch is fixed for the tested case through a local adapter.
  Broader roof geometries, separate-building occluders and mixed detail types
  remain unverified. Sloping/vertical fold tools and an exterior-wall occluder
  now have synthetic checks. Adapter uses version-specific private client interfaces.
- Direct initial placement now covers all three dormer shapes on one synthetic
  host. Broader host geometries and orientations remain unverified.
- Existence of other menus/property views is not verification of their behavior.
- Original full account application, remote AI, shading, imagery and DXF services
  are not running. No paid APIs, Aurora design requests or remote edits occurred.
- Cases are manual/synthetic. These checks establish interaction and persistence,
  not physical accuracy, independent truth, licensing or patent clearance.

## Required next work

1. Continue beyond verified cases: complex junctions, combined dormers and folds
   on one host, detail movement/deletion and keyboard cancellation.
   Flat/single-face drawing, L footprint, perimeter drag and redo now have
   synthetic checks. Fix demonstrated adapter defects; do not infer support
   from a visible button.
2. Extend fold surface-picking coverage to multiple roofs, separate-building
   occluders and complex host geometries. Four angled views of one
   synthetic roof now pass; do not infer full 3D parity.
3. Specify geodata coordinate scale, vertical datum and imagery alignment. Wire
   cached inputs first; paid Google calls need separate budget authorization.
   Respect source expiry/privacy before persisting derived real-house data.
4. Define reference-case export with provenance and evaluator-compatible geometry.
   Native design JSON alone is not DXF or measured ground truth.

## Reproduction

Run from this directory with the local server already listening on port 5191:

```sh
node probe.cjs --verify
node probe.cjs --demo --ui-fields
node probe.cjs --demo --ui-dormers
node probe.cjs --demo --ui-dormers --dormer=hip
node probe.cjs --demo --ui-dormers --dormer=shed
node probe.cjs --demo --ui-dormers --dormer=hip --placement-only
node probe.cjs --demo --ui-dormers --dormer=shed --placement-only
node probe.cjs --demo --ui-fold
node probe.cjs --demo --ui-fold-3d --angle=30
node probe.cjs --demo --ui-fold-3d --outside-fold
node probe.cjs --flat
node probe.cjs --single-face
node probe.cjs --concave
node probe.cjs --verify --perimeter
node probe.cjs --demo --ui-fold-fields
node probe.cjs --demo --case=fold-sloped-3d
node probe.cjs --demo --case=fold-vertical-3d
node probe.cjs --demo --case=two-folds
node probe.cjs --demo --case=two-dormers
node probe.cjs --demo --case=fold-height-drag
node probe.cjs --demo --case=committed-wall-blocks
node probe.cjs --prototype --verify
```

Passing evidence: `runtime/verified-*.json`. Most recent generic screenshot/report:
`runtime/preview.png`, `runtime/probe.json`. Failed attempts remain separately in
`runtime/failure.*`; their existence does not negate a later passing report.
Retained captured artifact and extraction identities are in `runtime/frontend`.
Do not distribute captured vendor assets with source or test-case exports.

## Latest verification milestone

October 28: nine workflows passed against that revision of `fold-placement.js`: 3D fold
placement/reopen at angles 30/120/210/300, outside-click rejection, 2D edited-fold
reopen, standard roof drag/undo/redo/reopen, initial hip reopen and initial shed
reopen. All have empty external-attempt, CSP-block, page-error, native-error and
unknown-metadata-query lists. Reports retain host and adapter hashes. Historical
failure files remain evidence of earlier attempts, not current failures.


## October 29 verification milestone

All six `--case` workflows pass with roof-face and wall-node geometry included:
sloping/vertical 3D folds, two folds, gable+hip dormers, fold-height dragging and
committed exterior-wall occlusion. Numeric geometry tolerance is 1e-7 m; source
IDs and structural shape are exact. Each checks undo/redo, retained footprint,
finite geometry and save/reopen. Flat-fold regressions at 30/210° plus outside-
click rejection also pass against the current adapter. No external attempts,
CSP blocks, native/page errors or unknown metadata queries in these nine runs.

The height-drag example changes fold height from approximately 4.306659 m to
3.746663 m and preserves the perimeter. This verifies interaction, not physical
accuracy. Earlier hidden cut-wall points were rejected as invalid occlusion
fixtures; the passing negative case establishes that an exterior wall is the
frontmost surface before checking rejection.

Reference/geodata interfaces remain unimplemented. `integration-contract.md`
records the current benchmark's DXF requirement, coordinate/lineage requirements
and expiry-aware storage prerequisite. Production files were read only.


## October 29 continuation: combined details and cancellation

Three additional synthetic workflows pass: gable dormer plus sloping fold on one
host; Escape cancellation of a second fold; Escape cancellation of a second
dormer. Combined-detail undo restores the pre-fold geometry and retains the
dormer. Cancellation restores the complete committed geometry and adds no extra
undo step. Redo and save/reopen retain face/wall geometry at 1e-7 m precision.
All three have no external attempts, CSP blocks, page/native errors or unknown
metadata queries. These extend coverage; no new adapter defect was found.

Commands: `node probe.cjs --demo --case=dormer-and-fold`, `--case=cancel-fold`,
and `--case=cancel-dormer` (each requires `--demo`). Next required coverage:
complex hosts/junctions, detail movement/deletion, and separate-building occluders.


## Latest continuation: deletion and L-shaped hosts

Keyboard Delete of a selected fold or dormer restores the original roof. Undo
recovers the deleted detail; redo removes it again; resulting state survives
save/reopen. New --concave + --case support freshly draws/reopens an L host before
running details, and retains -concave reports separately from rectangular cases.

L-host sloping folds and mixed gable/hip dormers pass. L-host vertical placement
initially failed because its live host-face collider disappeared behind the new
preview wall. A bounded committed-surface fallback fixes the demonstrated case;
see fold-placement-notes.md and the before-fix trace. Baseline projected-area
checks refer to the initial L roof, not physical accuracy of its detailed model.

Source hashes are now captured before execution and rechecked before accepting
verification, preventing reports from being marked passing if code changes during
a run. No new paid calls, Aurora requests or production modifications occurred.


## Complex-host regression completed

Nine current-adapter workflows pass: L-host mixed dormers, sloping/vertical folds;
rectangular fold/dormer Delete; committed-wall blocking; rectangular vertical
fold; opposite-view flat fold; outside-click rejection. L-vertical diagnostic
repeat records two committed-surface fallback reads. All have empty page/native
errors, external attempts, CSP blocks and unknown metadata queries. Face/wall
geometry survives undo/redo and reopen at 1e-7 m.

Use --concave --case=<case> instead of --demo for L hosts; reports have -concave
suffix. Adapter changed; native artifacts and production files remain unchanged.
Unknown hole metadata, courtyards and separate-building occluders remain unverified.


## Dormer movement verified

Pointer drag translates a gable dormer in 2D (~1.538579 m), 3D (~1.689601 m),
and on an L host (~1.538579 m). Every vertex follows one XYZ displacement;
vertex count, shape, pitch and parent footprint remain unchanged. Undo restores
the original position, redo restores movement, and reopen retains geometry at
1e-7 m. Three reports have no external attempts, native/page errors, CSP blocks
or unknown metadata queries. No adapter defect found or production change made.

Commands: `--demo --case=move-dormer`, `--demo --case=move-dormer-3d`, and
`--concave --case=move-dormer` with node probe.cjs. Separate-building occlusion
and additional complex junctions remain required coverage.


## Disjoint foreign-roof occlusion verified

--demo --case=foreign-roof-blocks builds a second flat roof through the visible
UI and confirms disjoint footprints. Local fixture height is chosen to intercept
a ray toward the edited host. The front physical hit is face.building inside the
foreign roof's rectangular bounds; adapter returns no host pointer and rejects
the click. Both roofs' complete geometry remains unchanged and survives reopen
at 1e-7 m. Report explicitly records undoRedo=false: fixture construction history
was not part of this test. Foreign front-hit coordinates and bounds are retained.

No page/native errors, external attempts, CSP blocks or unknown metadata queries.
Early fixture attempts needed proper isolation-context switching and recognition
of derived building faces; these were not demonstrated adapter defects. Adapter
and production code remain unchanged. This is one rectangular, disjoint-roof
occluder configuration; arbitrary buildings, overhangs and views remain unverified.


## Portable manual test-case export implemented

Export test case downloads roof-lab-case/v1 containing exact native JSON and its
SHA-256, local building-face/wall geometry with hole metadata, anonymous identity,
startup-pinned engine identities and running-exporter algorithm fingerprint.
Packages explicitly remain unvalidated/unregistered and benchmarkCompatible=false.
The geometry view does not silently claim occlusion, surveyed accuracy or DXF
compatibility; remaining native objects are retained in the raw model.

Five real-download and restoration workflows pass: basic roof, dormer+fold, L host,
standalone face and the preserved prototype's draw/drag/undo/redo flow. Tests check
checksum and geometry, analytic hole preservation, rejection of invalid indices/
nonfinite coordinates, unknown-hole flags and replay of the exact native payload.
Restored source/face/wall geometry matches at 1e-7 m. No external attempts, native/
page errors or CSP blocks. At the export milestone, import UI and benchmark adapter were pending; manual import is now covered below.


## Manual package opening completed

Open test case accepts matching manual v1 packages after policy/schema, engine,
native format/checksum and geometry checks. Validation precedes storage writes;
current work is saved before replacement. Imports get fresh local IDs and retain
one-hop source provenance. Saved active cases restore on home refresh; New example
still opens empty and the local library can reopen imported cases.

Five workflows pass (basic, mixed details, L host, standalone face, prototype).
Each rejects six corrupted/incompatible file classes without scene/library changes,
preserves an edited current model, restores imported geometry, retains provenance
through Save/refresh/re-export and passes New example/Reopen saved. Face/wall
geometry comparisons use 1e-7 m. No native/page errors, external attempts, CSP
blocks or unknown metadata queries. This does not add background autosave or
registered/imagery-derived package support. Benchmark adapter remains pending.


## Saved-example navigation recovery

Reopen saved now saves outgoing nonempty roof work when switching examples. For
an active-version revert, changed geometry/name is retained in a separate recovery
entry before loading the checkpoint. Save preserves recovery and import metadata.
Recovery tests restore checkpoint/recovery, edit the recovery, switch away/back,
verify latest state and check unchanged reloads do not add duplicate records.

Basic, mixed details, L host, standalone plane, prototype and imported-provenance
flows pass. One test initially edited an undefined plane-edge height; helpers now
edit the plane's real height and reject nonfinite fixture heights. This was a
fixture defect, not evidence of corrupted product geometry. Standalone import also passes with the corrected genuine plane-height edit. Background autosave remains out
of scope for this milestone; unsaved refresh/crash recovery is not promised.


## Navigation recovery verified

Six recovery workflows pass against current code: basic, mixed detail, L roof,
standalone plane, prototype and imported provenance. Tests cover active-checkpoint
revert with a recovery copy, no-op repeated reopens without duplicates, restoring
recovery, further unsaved edits while switching away/back and metadata retention.
Standalone file import additionally passes with a genuine plane-height edit.
No native/page errors, external attempts, CSP blocks or unknown metadata queries.
No background autosave or full historical-version retention is implied.


## Tab-local idle drafts verified

Added tab-drafts.js and app integration. Committed manual edits/name changes
journal after about 1.2 seconds idle. Preview modes, invalid roofs and held pointer
gestures defer writes. Refresh recovers matching-engine native format 3 drafts,
including Undo back to a saved baseline and deletion of the last roof. Named
library checkpoints remain separate. Explicit Save clears the journal; navigation
pauses pending work to prevent stale draft resurrection.

Six current-source browser workflows pass: pitched, L roof, standalone plane,
import plus navigation recovery, prototype with line drag, and dormer/fold host.
All assert refresh geometry, saved-checkpoint separation, Undo baseline, preview
and held-pointer exclusion, Save clearing, empty-scene recovery and provenance
retention. Import also retains existing rejection/navigation/recovery coverage.
No native/page errors, external attempts, CSP blocks or unknown metadata queries.
Two earlier failures came from insufficient reload/setup waits; harness now allows
full initialization and uses native Edit roof if double-click only selects.

This supersedes earlier 'no background autosave' milestone notes. It is a tab-local
journal, not disk backup or full history. No closing-tab retention is promised.
No source-derived imagery, production, native vendor bytes or paid APIs changed.
No active test remains; see CONTINUE.md for next required control audit.

## Whole-roof property audit and draft serializer correction (completed)

Visible native roof inspector exposes height, stories, roof type, Move and Explode.
New --roof-properties checks height edits as uniform XYZ roof-face/dormer elevation
changes with footprint and pitch preserved; stories is coupled to roof elevation,
not metadata-only. Height/stories Undo/Redo and local reopen now pass for pitched,
L-host and combined dormer/fold cases at 1e-7 m geometry tolerance.

Initial 500ms history assertion was premature; native edits commit asynchronously.
Tests now await the exact recentVersion transition. Experimental setter wrapper
was removed; frontend-ui.js matches its prior hash exactly.

A real draft bug was found separately: getJsonToSave() calls serializeForSave(),
which can leave roof editing and create a save-preparation history entry. Idle
journaling now uses native makeDesignJsonToSave() on already-committed valid roofs.
Expanded draft tests require edit mode to stay unchanged and Redo to remain usable
after an idle Undo snapshot, then compare refreshed geometry. All six current-source workflows pass: pitched, L, dormer/fold, standalone,
import/navigation and prototype. Native/page errors, external attempts, CSP blocks
and unknown metadata queries are empty. No active test remains.

Static provenance: REA parent ev_e92eee039042b4a39d6bb9ef8d2e2bcde36484cc390ebf68f3926a1f3b637c61
analyses two exact method excerpts, with 32 semantic unknowns. This is not a full
engine trace or runtime proof. Runtime browser checks establish behavior.


## Roof-type conversion and native notification bridge

Rectangle and L roofs now have visible pitched/flat conversion checks, including
unchanged footprint, valid finite geometry, one horizontal flat face, pitched
elevation variation, Undo/Redo and separate save/reopen in both states. Their
face counts are 4/1/4 and 6/1/6. No conversion algorithm change was needed.

A detailed fixture exposed missing host notifications: native flatten() refuses
roofs containing dormers or folds, but the informational toast was not displayed.
app.js now routes notify messages into visible aria-live status and evidence.
Mixed dormer/fold and fold-only fixtures verify the exact visible refusal, no
geometry/history change and subsequent save/reopen. Native guard stays intact.

Five current-source workflows pass: rectangle conversion + drafts, L conversion,
dormer/fold refusal, fold refusal and plain flat-roof drafts. Expanded draft
coverage still retains edit mode and Redo and recovers empty scenes. Native/page
errors, external attempts, CSP blocks and unknown metadata queries are empty.
No active tests remain. No vendor or production modifications, paid APIs or remote
operations. Next required control: whole-roof Move, then Explode.


## Whole-roof Move verified and journal extended

Five workflows pass: plain 2D/3D, L 2D, and dormer/fold 2D/3D. Normal whole-roof
selection followed by visible Move and face-interior dragging translates the
entire footprint, all roof/wall vertices and attached details uniformly in XY.
Z coordinates, pitches/heights, topology and IDs remain unchanged. Undo/Redo,
abandoning an unedited Move and normal save/reopen pass at 1e-7 m tolerance.
Initial tests incorrectly entered Move from roof isolation or targeted edges;
normal selection and a roof-face drag work without native adapter changes.

Move remains active after dragging. Its committed edits previously missed idle
drafts until exiting the mode. app.js now admits Move to the draft-ready modes
while retaining released-pointer, native-commit, validity and idle checks. All
five tests preserve active Move during journal writes, then refresh directly from
that mode and recover the moved geometry without explicit Save. Native/page
errors, external attempts, CSP blocks and unknown metadata queries are empty.

No active tests remain; no native/vendor or production changes. Does not establish
rotation, multi-roof Move or cancelling an in-progress drag. Next: Explode semantics.


## Explode semantics and recovery verified

Five synthetic cases pass: plain, L, dormer/fold, flat and vertical fold. Visible
Explode immediately replaces parametric roof/detail objects with independent
roof.plane objects using new IDs. Source face coordinates and native exported
roof rings remain unchanged at 1e-7 m; current samples have no courtyard holes.
Native provided hole rings are checked without claiming general hole support.

Undo restores the source objects; Redo restores planes. Idle draft refresh and
explicit Save/reopen preserve both plane geometry and resulting native exported
face/wall/hole rings. Success notification is visible. All current-source checks
have empty native/page errors, external attempts, CSP blocks and metadata misses.

Building-envelope representation is not retained: native building grouping and
wall polygons change. Plain walls 4→14, L 6→24, mixed 8→25, flat 4→4, vertical
fold 5→17. Mixed/vertical each lose one exact original wall-ring match while new
rings are added. No wall-union, volume or physical accuracy claim follows.
No adapter/product/vendor changes were required. No active test remains.
Next: independent editing of generated planes with isolation/history/recovery.


## Independent generated-face editing verified

Four source workflows (plain, L, mixed dormer/fold, flat) pass real pointer
selection followed by visible height/pitch edits on one generated roof.plane.
Other source planes remain unchanged. Height translates the selected vertices;
pitch changes that face's geometry. Native revision commits, per-edit Undo/Redo,
draft refresh, explicit Save/reopen and displayed field retention pass at 1e-7 m.

An initial detailed fixture incorrectly treated rounded inspector height as exact
native height. Tests now use the entered absolute target minus actual native
height. No native adapter defect was found. Current checks have empty native/page
errors, external attempts, CSP blocks and metadata misses. No product, vendor,
production or paid API changes. No active tests remain. Next: independent-plane
boundary/vertex pointer editing. Goal remains manual test-case authoring.


## Manual authoring guidance and outline controls

Implemented visible How to model guide in header and contextual outline-editing
hint for selected independent faces. Updated title to Roof test-case builder.
Guide covers established manual workflow and Explode/save/export consequences.
This is host usability work; no new roof geometry algorithm was implemented.

Existing native edge and corner drags now pass seven workflows: plain/L/mixed
sources for both handle kinds and flat source for corner. Each reshapes the
selected outline, keeps source pitch, retains stationary vertices and leaves all
other source planes unchanged. Validity, Undo/Redo, idle draft refresh and saved
reopen pass at 1e-7 m. Native/page errors, external attempts, CSP blocks and
metadata misses are empty. Guide opening and layout were visually verified.

No active tests remain. User's actual browser was not refreshed or edited.
Next: practical manual workflow, numeric edge lengths and vertex insertion/removal;
fix actual missing host bindings. Avoid conflating test coverage with new features.


## Roof-corner angle authoring implemented

Implemented missing local inspector for selected node.perimeter. New Plan angle
input, Apply and opposite-moving-neighbor choice call native angle action. Selected
corner stays fixed. Existing Length field was found and retained; edge hint and
manual guide now expose both workflows. This is functional host integration.

Native cached angle was stale after Undo in a reproduced case. Inspector now
measures live plan coordinates, reflects Undo/Redo, and avoids applying rounded
unchanged values. Fractional entry remains in geometry despite rounded display.
Three focused workflows pass: plain convex, L concave, and detailed convex, both
moving sides. Real pointer selection, native length, geometry/angle measurement,
validity, source pitch/height, range/no-op history, Undo/Redo, draft and saved
recovery pass. No native/page errors, external attempts, CSP blocks or metadata
misses. Visual layout checked. No active tests remain. Native/vendor and production
code unchanged. Next: native vertex insertion/removal workflow and missing bindings.


## Closed-outline corner removal added

Added Remove corner button to SmartRoof corner inspector, reusing native
closePerimeter(node) and native commit. Remaining neighbor is selected. Command
joins adjoining edges and keeps outline closed; last three corners are protected
by disabled control and explanation. Native direct deletion instead opens outline.

Plain 4→3 and L 6→5 cases pass real pointer selection, valid closed roof, remaining
positions, Undo/Redo, draft refresh and saved reopening. Plain verifies minimum
three-corner guard after reload. Fractional angle editing also passes regression.
Native/page errors, external attempts, CSP blocks and metadata misses are empty.
Generated wall order can change after topology Undo; comparisons sort by source
ID and still compare coordinates. Initial ordering mismatch was not geometry loss.

UI visually inspected. Native/vendor and production code unchanged; no active
tests remain. Corner addition/redraw and arbitrary attached-detail consequences
remain unverified. Next: native insertion/redraw human workflow and safe cancellation.


## Midpoint corner insertion added; detailed-roof guard

Added local Add corner at midpoint to SmartRoof edge inspector. Button selects
the new corner for dragging. Native ring primitives split the source edge, carry
pitch/height to both replacements and rebuild faces; no solver/vendor changes.
Plain 4→5 and L 6→7 flows pass real pointer insertion/reshaping, native validity
and construction, original face-plane and projected-area checks before dragging,
separate insertion/drag Undo/Redo, idle-draft refresh and saved reopening. UI
visually inspected; Length remains available.

Mixed dormer/fold insertion + reshaping exposed native unconstructed state;
reproduced with readiness diagnostics. Drafts correctly refused it. Exact failing
step remains unisolated. Add/Remove corner now disable on roofs with dormers or
folds and explain outline-first workflow; no details are silently discarded.
Guard test preserves original geometry. Plain removal/minimum-three regression
also passes. Four final reports match current source hashes; no page/native errors,
external attempts, CSP blocks or metadata misses. No active test remains.

README and CONTINUE record controls, restriction, evidence and resume point.
Next: actual perimeter Length changes and both moving-side choices in practical
manual case. Keep production reconstruction and source-expiry boundaries intact.
User tab untouched. No paid API calls, remote edits, vendor changes or commits.


## Precision Length workflow and accessibility completed

Existing native Length control now has a host-supplied accessible name and
explanation. Icon endpoint choices have descriptive accessible/hover labels.
No edit handlers, vendor assets or native geometry were replaced. Native
anchorLeft keeps edge.nodes[1] fixed; anchorRight keeps edge.nodes[0] fixed.
Names describe native endpoint order rather than camera left/right.

Three focused checks pass: plain, L and dormer/fold hosts. Real pointer edge
selection, both named choices, fractional target, single endpoint motion along
original edge, other corners fixed, source pitch/height, native validity and
construction, Undo/Redo/display, untouched-blur geometry/history, drafts and
saved reopening pass. Current hashes verified; no errors, metadata misses, CSP
blocks or external attempts. Visual layout checked; no active tests remain.

This is native capability verification plus small host accessibility/guidance,
not a new geometry feature. Next: practical combined outline-first authoring flow
through details, named save, export and reimport; fix demonstrated integration
gaps. Existing detailed-roof corner-count guard stays. User tab and production
untouched; no paid calls, remote edits, vendor changes, deployment or commits.


## Worked manual case and portable names completed

Combined blank→Length→midpoint insertion/drag→gable dormer/sloping fold→named
checkpoint/reopen→export→New example→file import→Save/refresh now passes native
full-geometry comparison at 1e-7 m. Actual missing host feature fixed: portable
files now carry example names and readable filenames, and import restores names.
Optional name is backward compatible with original unnamed v1 packages. Name is
cosmetic metadata; geometry checksum remains native-payload-only. Native assets
and solver unchanged.

Worked private synthetic package: runtime/manual-outline-first.roofcase.json;
3D visual capture: runtime/manual-outline-first.png. Fresh browser file-open and
visual check passed. No user-browser data was changed. This is unregistered
manual comparison geometry, not real-house accuracy evidence or benchmark DXF.

Combined-flow and existing import/preservation regressions pass on current source
hashes with no page/native errors, metadata misses, CSP blocks or external
attempts. First filename assertion exposed repeated slug hyphens; normalized and
reran successfully. No active tests remain. README/CONTINUE record workflow,
package names and next step: native gable starter/preset convenience for manual
roof authoring. Keep native geometry, outline-first detail restriction and
production/source-expiry boundaries. No deployment, commits or paid calls.


## Hip/Gable/Shed starter controls added

New whole-roof card sets native edge pitch configurations for Hip, Gable and Shed,
with pitch input and 90° direction control. One native commit per application;
no new solver or vendor edits. Supports closed rectangles with equal edge heights
and no details, including native flat roofs. Flat encoding is all vertical (90°)
source edges, not zero pitches; direct conversions were verified and documented.

Plain/flat sources pass all shapes, both gable axes and four shed directions,
actual ridge/face checks, source footprint/heights, atomic Undo/Redo, no-op and
invalid inputs, final-gable draft/save recovery. L and detailed guards preserve
geometry. Four final reports match current hashes; no native/page errors,
metadata misses, CSP blocks or external attempts. Visual card layout checked.

New visual defect found: native Fit clips tall shed after settled animation.
Reproduced and recorded exact projected vertex bounds in runtime/analysis/fit,
with private screenshot and own diagnostic script. Geometry remains valid.
Manual zoom is workaround; height-aware host Fit is next required fix, then
practical details-after-presets flow. User tab unchanged; no active tests remain.
README/CONTINUE updated. No paid calls, production edits, deployment or commits.


## Tall-roof Fit fixed in host

Own top Fit button now frames full 3D bounds about native ground-level orbit
pivot, accounting for actual viewport aspect/FOV and camera radius conversion.
Uses native camera animation; native 2D fitting stays unchanged. Scene inclusion
keeps native focus types and adds computed roof details/walls. No vendor edits,
geometry commits, selection changes or model/history writes. Empty scene is safe.

Tall shed, dormer/fold, two-roof and empty flows pass final source hashes. Actual
projected vertices/depth stay contained through 3D/2D, explicit 3D orbit, wheel
zoom/refit and portrait/wide resize. Geometry/history/mode/selection preserved.
Earlier zoom timeout was a fixture still in orthographic mode, not a host defect;
corrected and retested. No errors, metadata misses, CSP blocks or external calls.

Visual before/after retained; fixed shed fits original viewport. REA bounded exact
callback evidence and source offsets retained; static partial coverage is not a
full native trace. Ground-based conservative framing leaves margin; internal SDK
focus shortcuts remain native. No active tests remain. README/CONTINUE updated.
Next: practical dormer/fold authoring after Gable/Shed starters. User tab untouched;
no production changes, paid calls, deployment or commits.


## Exact footprint dimensions and starter-detail compositions

Gable and Shed now have verified worked manual flows from blank through starter,
dormer/fold, named save/export/import. Shed uses separated positions on its single
face. Examples saved privately; final Gable regression passed after UI changes.
No new native placement code was required.

Actual new feature: Footprint size Width/Depth controls under Roof starter.
Resizes four source corners in native edge basis as one commit, keeping center,
orientation, IDs and source pitch/height. Native CAD builds faces. Untouched-axis
precision retained despite rounded display; no-op adds no history. Range 0.1–1000 m;
rectangle/equal-height/before-details eligibility enforced.

Rotated Gable, flat, detailed/L guards, draft and saved recovery pass; final
composed Gable authoring regression passes. Five final reports match current
source hashes. No errors, metadata misses, CSP blocks or external attempts.
Simultaneous 24×14 m resize visually verified with 3D Fit. User tab untouched;
no active tests remain. README/CONTINUE and worked examples updated; prior Gable
example preserved in private history. No native, production or paid-call changes.

Next: source-free manifest/calibration and expiry-aware cached-background plan
for manual tracing, under integration-contract.md. No real cache ingestion until
expiry/permissions/transforms and every persistence/export path enforce contract.

## Source-free background contract groundwork

Implemented independent manifest validator and affine/expiry/permission/hash
checks. 31 deterministic checks pass with frozen source hashes; synthetic 16×12 m
grid generated. Explicit original times, earliest expiry, async recheck, aligned
rasters and numerical calibration covered. This is not image decoding, source
rights authentication, CRS verification or end-to-end storage enforcement.

Read production cache code only; no DB, pickle or actual imagery use. Observed
native worldfile/resource/texture collection signatures without invoking loading.
Bounded REA excerpt evidence retained. Native registration/activation still
unverified. No editor integration or real imagery support claimed. New plan and
CONTINUE give synthetic-only underlay next step and required real-source gates.
No user tab, production, native assets, paid/API or deployment changes. No active
tests remain; keep heartbeat active for remaining integration work.


## Synthetic native underlay calibration completed

Own `synthetic-underlay-probe.cjs` registers immutable generated PNG bytes through
native orthoTextureCollection, with `custom` source and `useMapView=false` unchanged.
Native worldfile consumes geographic pixel corners; manifest uses editor-meter
pixel centers. Degree-per-meter factors come from native getDefaultWorldfile;
adapter explicitly subtracts the half-pixel basis offset. No vendor code patched.

Final unrotated 34834 and 90° rotated 19041 pass three independent controls within
1e-6 m, native origin/basis/center, 16×12 m extent, loaded/active state, removal and
unchanged native design/history/browser storage. Both capture 2D and 3D renders;
rotated 2D visually inspected (corner colors and grid orientation agree). Reports:
runtime/input-contract/underlay-probe{,-rotated}.json, with frozen own source hashes.
No external requests, page/native errors, CSP blocks or notifications. No claim of
GPU resource disposal, arbitrary provider refresh or surveyed-world registration.

Probe accepts only the pinned generated PNG SHA
b43ac96da9eb85eba8a8244552bf3aad6a9a34f87f67661dd4a1556163b01900,
64×48 RGB pixels and synthetic/generated-locally source declarations. Metadata-only
external mocks remain tests, never loaded imagery. input-manifest-checks.mjs now
generates PNG and still passes 31 checks; old SVG retained. Hash pin prevents
accidental fixture substitution, not hostile script changes or false lineage.

Initial native Blob fetch failed under own CSP. Preserved failure:
runtime/input-contract/underlay-csp-blocked.json. Own server.py now permits
`connect-src 'self' blob:`; no remote origin enabled. PNG fetch/decode then passed.
This failure did not establish an SVG decoder limitation. Native artifacts unchanged.
Old server session 67308/PID 69403 stopped only after identity verification; current
server session 68237/PID 3470 listens on 5191. No user tab reloaded or edited.
No active probes remain. No production edits, real imagery reads, API/account
calls, paid acquisition, auth bypass, deployment, commits or vendor publication.

Completed checklist:
- [x] Pinned generated bytes and native image registration.
- [x] Pixel-center/corner conversion, exact scale/center and 90° rotation.
- [x] Actual native 2D/3D renders, empty-host frame stability and removal.
- [x] Native design/history/manual storage unchanged; source hashes frozen.
- [x] Contract checks regenerated; server identity and resume point recorded.

Next required work: opt-in built-in synthetic calibration background lifecycle.
Use independent adapter code, explicit transient status and no real input picker.
Verify trace coordinates and removal/New/recovery behavior; never serialize Blob
URLs as saved case dependencies. Native texture disposal must be established before
claiming resource cleanup. Keep expiry-aware external storage/import/export gates
in background-input-plan.md: real imagery is still disabled. Do not turn this proof
into automatic reconstruction or claim user-facing imagery support. Existing manual
case/library/export remains permanent synthetic-only. New tests only for changed
behavior; do not rerun broad completed roof matrices.


## Google address imagery connected; temporary session only

User explicitly authorized Google API acquisition for [local test property], and requested an end-to-end demo tonight. This overrides earlier
no-paid-acquisition boundary only for this requested property; it does not authorize
background acquisition, retries on page reads or other addresses. Production repo
remains read-only. Do not let heartbeat reacquire Google data.

Initial Insights attempts failed HTTP 403 / API_KEY_IP_ADDRESS_BLOCKED. User updated
key's allowed IP list; current outbound IP observed as [local outbound IP]. After propagation,
authorized acquisition succeeded: one successful Building Insights, one Data Layers,
one RGB download; no DSM/mask downloads or reconstruction. Raster 808×809 after local
meter reprojection; source capture date 2023-10-17, no source-match warnings. Failed
403 attempts downloaded no imagery. Key never logged or returned to browser.

New own code: google-imagery.py (explicit acquisition/cache reuse), imagery-session.js
(source registration/expiry), google-preview-check.cjs, imagery-session-checks.cjs;
server routes /google-imagery.json and .png, plus own module allowlist. Source UI:
/?google=kimberly, Address imagery link opens a separate tab. Existing user tab was
not reloaded or edited. Native vendor artifacts unchanged. No production changes.

Private source directory runtime/google-kimberly contains manifest.json, image.png
and preview.png only; all share source expiry. Current exact expiry comes from its
manifest (2026-11-29T02:08:15.859500+00:00), never rebase from file time. Native world
stays artificial local origin; raster uses declared local AEQD meters, with true
building origin/CRS recorded separately. No claim of surveyed-world accuracy or
verified elevation datum; no DSM acquired. Visible attribution in same viewport.

This session intentionally cannot persist source-derived models. No manual library,
active ID or draft read/write, save handler refuses persistence, own save API/shortcut
blocked, file import/export and clipboard copy/cut disabled. New exits without copying
source geometry into manual cases; refresh resets transient edits. Unexpired PNG
hash and decoded dimensions checked. Manifest/source routes enforce original fetched
+ maximum 30-day expiry. Server cleanup every60s/startup/request removes owned source
files including preview; when stopped, purge on next start. Browser rechecks on tab
resume and exits at expiry. Permanent source-aware cases remain unfinished, not
silently implemented through v1 exports. UI says temporary and edits reset.

Checks completed:
- Live preview 30432 loaded actual cached imagery, one active native texture, visible
  attribution, empty browser storage, no external requests/page/native/CSP errors.
  Actual screenshot in expiry-bound source directory visually inspected: matched
  center house appears under origin marker. Native rendering is dimmer than raw RGB.
- Synthetic source session final 64467 passes exact 16×12m registration; pointer-drawn
  12×8m rectangle coordinates within 5cm (observed <1e-6m); save/export blocked,
  manual storage/draft sentinels unchanged, New removes imagery and expiry exits.
  Report runtime/input-contract/source-session-checks.json pins final sources.
- Four isolated server lifetime cases pass: fresh30d, oversized31d rejection/purge,
  expired rejection/purge, future acquisition rejection/purge. No real cache modified.
- Earlier trace timing failure stabilized with explicit native camera pose/settle.
  A later New navigation test was interrupted by server restart; rerun64467 passed
  serially on stable server. Do not run/restart overlapping browser probes.

Current server session51092 on5191 has final server.py. Manual regression38903 still
running at time of this note; poll before claiming success. Prior --demo --verify
44783 failed harness first-corner assertion while browser tests overlapped; do not
claim it passed. Standard --verify on empty editor is appropriate regression.

Next required work: source-aware persistent correction packages, then first generated-
model→editable-face handoff. User asked whether other tool could use this as accuracy
layer; answer: not connected yet, manual correction is feasible, no automatic accuracy
claim. Target limited demo tonight, not full automatic reconstruction. Preserve frozen
production evaluator. Inspect actual reconstruction face/height/frame schema and native
standalone-face format, define independent adapter and test known synthetic plane inputs
before real-derived transfers. No rewrite, no new vision training, no vendor patching,
no silent arbitrary-face conversion into SmartRoof. Real source data and every derivative
must retain expiry. Keep work limited to lab unless user explicitly requests production
integration changes. Reuse acquired image; do not spend on additional calls.


Final check38903 passed standard `node probe.cjs --verify`: manual drawing, four
faces, internal-line drag, footprint preservation, Undo (max height error <9e-16m)
and native save/reopen roundtrip equality. No page/native/CSP errors or external
attempts. No active tests remain. Current server session51092 serves final sources.
Address preview opening queued by open_in_codex for this chat; direct URL remains
http://127.0.0.1:5191/?google=kimberly . Existing user tab/work preserved. Source acquisition remains explicit, never heartbeat.


## Address lookup implemented; external geocoding access pending

Added Find address dialog, explicit Search, selected-property Load imagery and Open
image editor link (separate tab). Search reads local parcel records read-only, splits
and normalizes address tokens, and deduplicates multiple datasets by parcel ID. When
no local result exists, uses Google Geocoding API with server key fallback. Searches
run on submit only, never keystrokes. Loading imagery is a separate explicit POST;
existing property cache reused. No background or heartbeat acquisition authorized.

Own new files: address-lookup.js, address-imagery.py, address-lookup-checks.cjs.
google-imagery.py is now reusable acquire(target,cache), with no hardcoded address;
its CLI refuses acquisition and directs users to the lookup UI. Worker selects the
legacy cached image only when its origin lies inside selected parcel. Other sources
have stable 32-hex IDs and separate runtime/google-addresses/<id> directories. Native
source sessions accept those IDs and pass source query to manifest/image routes.
Server source paths are validated; same-origin JSON POSTs required; search selections
are unguessable, memory-only, expire after15m; one acquisition at a time. API keys and
provider URLs remain server-side. Original source dates and30d maximum preserved.
Google-geocoded locations require a precise rooftop/interpolated result without
partial_match; nearest Solar building must be within25m. Local parcel selections
instead require building center inside actual parcel. These checks are not a survey.

Export controls clarified: Export engine JSON = raw native model only. Export test
case = package with native model, resolved roof/wall geometry, metadata/checksums.
Open test case validates/reopens that package, not raw engine JSON or imagery. Titles
and How to model explain difference. Google source sessions still block persistence
and export; this task does not claim source-aware test packages are finished.

Verification:
-22547 real local search→deduplicated one result→Load imagery→existing cache→separate
 native editor passed. Actual source manifest unchanged (no new image acquisition).
 Invalid/expired selection IDs and source traversal reject; mocked Geocoding denial
 appears actionable. No native/page errors, external browser requests or CSP errors.
 Report: runtime/input-contract/address-lookup-checks.json (frozen sources).
-32019 synthetic --dynamic source ID passes16×12m calibration, pointer tracing,
 save/export denial, manual-library/draft isolation, New and expiry navigation.
-6 source-free lookup tests pass: no Google lookup when local match, one fallback
 on no match, fallback on local DB failure, approximate/partial geocodes filtered,
 zero results and denied access handled. No network in these unit checks.

One explicit Google Geocoding capability test for existing requested address returned
GEOCODING_REQUEST_DENIED. Solar API itself already works. User asked why another
API: Geocoding translates address text into coordinates; Solar accepts coordinates.
Local parcels provide coordinates already, so no Geocoding needed for those homes.
General addresses outside local dataset need an address-to-coordinate provider.
Do not retry Google until user confirms access/config change. Geocoding currently
uses GOOGLE_GEOCODING_API_KEY, else GOOGLE_MAPS_API_KEY, else GOOGLE_SOLAR_API_KEY.
No new imagery was acquired in this pass. User has NOT confirmed enabling Geocoding.

Current live server session29247 on5191, original lab directory. No active probes.
Existing user tabs were not reloaded or edited; new UI appears in fresh/reloaded tabs.
Published GitHub snapshot6fa0d91 precedes this change; do not claim newer lookup code
has been pushed. Preserve worktree and private runtime boundaries when syncing.
Next: resolve whether user wants broader address coverage/enables geocoder, verify
that route only after config change, then source-aware export/persistent packages.
No changes to production reconstruction/evaluator or vendor artifacts.


## Phoenix scope: address search now local-only

User clarified Phoenix properties only. Active lookup no longer falls back to Google
Geocoding, including no-match and local DB failure. Uses loaded Phoenix-area parcel
records; this is not a claim of complete Phoenix coverage or a Phoenix-city boundary
restriction (existing Glendale case remains supported). Unknown addresses show local
coverage message. DB failure gets a distinct unavailable message. Solar imagery still
loads explicitly after selecting a known parcel, with cache reuse/expiry unchanged.
Dormant google_search helper is not wired into search. Do not enable/retry Geocoding
or ask user to enable it for current scope. Three mocked backend cases (match, no match,
DB failure) verify no Google lookup calls. Full address-check rerun pending; see latest completion below for outcome. Current server session71364 on5191.
Existing user browser tabs not reloaded; save/avoid refreshing unsaved source edits.

Local-only full flow41297 passed: real local parcel lookup, deduplication, unchanged
existing imagery reuse, separate editor tab, source export blocking, unknown-address
coverage message and invalid token rejection. No external browser attempts/errors.
No active probes remain; source-hash report updated. Server71364 remains running.


## Height display / selected roof fit implementation

User asked to implement Google DSM height display and roof fitting. New own code:
height-data.py, height-fit.mjs, height-tools.js, height-data-checks.py,
height-fit-checks.mjs, height-tools-checks.cjs. Added server height-acquire POST,
height metadata/binary GET routes; worker dispatch; source-only Height data panel;
retained SmartRoof Fit to LIDAR button opens own preview when heights loaded. No
vendor methods patched or elevation getter replaced. Standalone native face fitting
remains disabled. No production reconstruction/evaluator changes.

Backend: explicit one DataLayers request + DSM/mask downloads, same RGB origin,
local CRS/pixel-center registration, bilinear DSM / nearest mask,5× subsampling
(~0.5m), Float32LE heights plus mask. Ground estimate = non-roof20th percentile
within25m. Unknown mask255 stays distinct from valid ground0 and roof1; initial
dst_nodata0 incorrectly filled mask, found/fixed by synthetic alignment checks.
Original image expiry/image hash retained; capture-date mismatch rejected before
raster downloads; expired sources rejected before network. Height cache hashes
checked before reuse. Cleanup includes all height files and .pending files. Browser
checks byte counts/hashes/datum/registration/expiry and exits with source session.
Height files never enter permanent manual library or exported cases.

Client: colored sampled height-point overlay projected through native camera, not
native LiDAR data or surveyed accuracy. Ground reference adjustable. Fit supports
four-corner roofs without dormers/kinks, including flat roofs. Keeps source XY and
edge directions; independent Huber-style robust 1D regression fits each existing
face's inward-distance slope and eave height. Excludes roof-mask negatives and face
boundary0.35m; minimum40 samples, residual/inlier and height/pitch guards. Native CAD
constructs final geometry. No automatic outline/face discovery. Preview/cancel do
not mutate; apply checks source snapshot/selection/ground for staleness, commits
once and checks construction. Rejected native construction triggers Undo. One
Undo/Redo restores tested complete geometry. Failure/no-op is explicit.

Verification so far:
- Pure math: known slopes/eave heights recovered with outliers; insufficient,
 degenerate, masked-only and detailed inputs rejected; flat proposal verified.
- Synthetic GeoTIFF checks pass: alignment, NaN/nodata handling, ground estimate,
 exact original expiry, immutable cache reuse, temporal mismatch before download,
 expired input before network. Synthetic expired-image cleanup removes all height
 files and staging bytes alongside original source files.
- Browser11487 passes synthetic pitched hip: 4m eaves/30° recovered, fixed outline,
 non-mutating preview/cancel, one Undo/Redo, stale preview rejection, reference-change
 invalidation,8886 colored pixels in3D, empty browser storage/errors/CSP/external
 attempts. Its report precedes final flat branch/UI word change; final variant run
 below will establish latest sources. Source hashes frozen in report.
- Fit-panel mouse events initially cleared native selection; mouse/touch propagation
 now stopped alongside pointer events. Test also waits native mode transition.
- Ground input is inside collapsed Height reference; fixture now expands it first.

LIVE ACQUISITION BLOCKED: exec_command automatic approval review rejected requested
DSM/mask request as not explicitly authorized external paid/location-disclosing action.
It did not execute; no height data acquired, no costs/API calls from that attempt.
Do not bypass by invoking through server/another tool/heartbeat. User was shown exact
permission request for[local test property]: one Data Layers + DSM/mask downloads,
location sent to Google, potential charges. Approval pending. Complete synthetic
work and docs; retry ONLY if human explicitly approves. Existing Google RGB unchanged.
Do not claim live heights loaded or fit improves real-house accuracy.

Current server session12634 on5191. Flat browser run98470 pending at time of note.
No user tab reloaded or edited. Source-only temporary controls available in fresh tab;
user must preserve current transient work before refreshing. No GitHub sync since
source snapshot6fa0d91. Preserve both original lab and publishing worktree.


Final height checks complete on frozen sources:
-34604 flat roof:5m height recovered; native flat-mode source pitch90° preserved,
 physical surface remains flat. Native uses90° sentinel edges for flat roofs, so fit
 must not set those edge fields to0°. UI reports physical flat slope0°.
-97373 pitched hip:4m eaves/30° recovered, exact fixed outline, nonmutating preview/
 cancel, one Undo/Redo, stale rejection, reference invalidation,8886 overlay pixels.
-Flat has12797 overlay pixels. Both empty native/page/CSP errors, external attempts
 and browser storage. Reports runtime/input-contract/height-tools-checks{,-flat}.json
 pin same final implementation hashes; UI screenshot synthetic only.
-Pure fit checks and GeoTIFF processing checks pass. Synthetic expired-source cleanup
 covers height binary/metadata/staging files. No active tests remain.

Current code/server12634 implements requested controls; live test still requires
pending explicit human approval after auto-review rejection. No DSM/mask request has
executed and no live pointcloud shown. Do not bypass by clicking live Load heights
through another tool. If approved, use explicit height-acquire for current source,
then verify local-cache render without paid retries. Existing user model must remain
untouched; test independent fresh browser and keep source captures expiry-bound.


## First approved live-height attempt and processing fix

Human explicitly approved one Google DataLayers request + DSM/mask downloads for
Kimberly. Attempt58918 executed and returned INSUFFICIENT_GROUND_SAMPLES during local
processing, after provider data returned. Earlier implementation discarded raw bytes
on processing failure; no usable height cache remains from that attempt. Do NOT claim
network failed or retry that exact one-request approval automatically.

Reproduced failure synthetically with binary mask TIFF declaring nodata0: GDAL treated
valid zero/non-roof pixels as absent. Fixed by reading mask into array, overriding source
nodata255 and preserving0=non-roof/1=roof/255=unknown. This reproduces/fixes a concrete bug;
actual initial raw rasters were not retained, so definitive live cause still unverified.
height-data-checks.py now uses nodata0 and passes alignment/nodata/ground/cache/expiry.

Added expiry-bound original raster cache BEFORE local processing: height-dsm.tif,
height-mask.tif, height-source.json, atomic .pending files. Hashes/date/image identity/
original expiry checked before reprocessing, so future processing fixes reuse raw bytes
without another Google request. Original height fetchedAt retained across reprocessing.
Cleanup in server.py/google-imagery.py covers original height bytes and staging files.
Synthetic cache-reprocessing and full raw-file expiry cleanup pass. Syntax checked.
Current server session27928 on5191 (previous12634 stopped); no browser tabs reloaded.

Explicit follow-up question asks approval for ONE ADDITIONAL billed/location-disclosing
retry because first did not retain bytes. Approval is pending. Do not route around via
browser/server/heartbeat. No new calls after58918. Prepared height-live-check.cjs reads
local cache only and intercepts height-acquire POST, so it cannot acquire/bill. Run only
after usable height.json exists, then inspect expiry-bound preview.png. No live fitting
or geometry-accuracy claim yet; synthetic flat/pitched fitting remains verified.


## Live height integration verified; approvals superseded

Human explicitly approved as many runs as needed for this property's height-data
integration. This supersedes earlier pending one-request/retry approval notes; do
not ask again for necessary Kimberly runs. Reuse caches rather than rebill. Other
properties/background acquisition remain outside this specific approval context.

Retry75963 succeeded:25511 valid samples, including5097 roof and20414 non-roof.
Actual source mask TIFF declares nodata0, confirming reproduced mask-zero bug.
Root imagery expiry unchanged. Original DSM/mask and metadata now retained privately
before processing, with checksums/date/source expiry; no provider URLs or keys saved.
No further Google requests used for verification.

Live display91818 passed from local cache, with acquisition POST intercepted to prevent
API calls. 3D point overlay verified and expiry-bound preview.png visually inspected.
Native user model untouched; separate empty test browser, no browser storage or external
traffic. Local original heights plausible relative to estimated ground, not surveyed.

Live patch fitting17332 passed on a separate temporary four-corner shed over one
planar portion of the real cached DSM. Test uses a fitted local patch solely to check
wiring, not whole-house reconstruction or accuracy. Preview nonmutating, applied native
roof valid, XY unchanged, one Undo/Redo restores geometry, browser storage empty.
Script height-live-fit-check.cjs is cache-only and intercepts acquisition POST. Never
publish source samples/screenshots; existing preview.png is under original source expiry.

Current server27928 serves working controls; no active tests. No user tab reloaded.
User asked whether heights are a map or points: Google supplies DSM raster; own adapter
samples aligned grid into XYZ points (~0.5m spacing for fitting; display subset for speed).
This is derived raster visualization, not raw LiDAR returns. Continuous height mesh is
not implemented. Fitting uses robust sampled elevations with fixed XY, not a new image
recognition model. Keep initial supported scope and ground-reference limitations explicit.

## Ground photo brightness fixed — October 30, 2026

User reported dark imagery. Raw cached PNG is bright; DOM/canvas opacity1 and no
filter. Focused static inspection found lit ground ShaderMaterial using environment
lighting. REA summary ev_5b6a504d9a47fa4477c4a57483944b9bc33fedead88f6c618a7ca65f3113a886,
parent ev_4c474e1263687b0b4a395784634ff9e28e971328e48b2f22526c52ae18558f4c
analyzes private extracted GroundRenderer slice only (one parsed file, zero parse
failures, semantic coverage partial/unknown;218 unknowns). Static analysis alone
does not establish runtime brightness. Retained slice stays under ignored runtime.

Own imagery-session.js adapter now outputs source display RGB on single ground photo
after scene shading, with feathered image border. Native grid outside image, roof
materials, geometry, original texture bytes and vendor artifacts remain unchanged.
Ground material shape is validated; version mismatch fails explicitly. This is a
version-specific runtime adapter, not a captured vendor-file patch or global gamma
change. Future multi-image/opacity controls require a separate display design.

Regression `node imagery-brightness-checks.cjs` generates synthetic64x48 gray bands,
intercepts source/case responses, blocks every POST/external origin, and checks actual
screenshot pixels against64/128/192/240. Exact values pass at90° and35° camera angles.
No shader/page errors;16 pre-existing feature-name console warnings separately counted.
Raster fixture has no georeferencing (expected test-only rasterio warnings). No new
Google calls. Live cached photo visually verified in a new browser tab; original user
tab untouched. Final preview uses existing expiry-bound runtime/google-kimberly/preview.png.
Both vendor SHA256 hashes unchanged. No outstanding work for this brightness fix.
