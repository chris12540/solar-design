# Continue isolated local roof editor lab

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


Updated October 29, 2026. Read this file, `progress.md`, `README.md` and the
relevant interaction notes before editing. Latest state and resume point are in
the final completed section; earlier milestones are historical. Earlier milestones remain in progress.md.
Do not restart the production reconstruction plan or repeat already-fixed issues.

## Objective and boundaries

Continue the existing local manual roof editor toward tested roof-modeling parity.
User reaffirmed manual test-case authoring is the goal; automatic reconstruction
is separate and must not displace this work.
Workspace: `/Users/chris/Documents/ChatGPT/Solar Auto-Estimation/research/aurora-local-lab`.
Demo: http://127.0.0.1:5191/?demo=1 . Empty editor: `/`. Earlier minimal host:
`/?prototype=1`. Captured controls and CAD client run through local adapters;
the complete Aurora account application and server-side AI do not run locally.

- Preserve all files, existing work and private ignored runtime artifacts. No
  resets, cleanup, automatic commits/pushes, deployment or vendor publication.
- Production `/Users/chris/code/solar-designer` has separate ongoing work. Read-only
  inspection is permitted; do not modify it or its frozen evaluation direction.
  User may be viewing its separate roof studio at port 5173; leave that app alone.
- Only local manual/synthetic examples here. No paid imagery/API calls, Aurora
  account/design requests, remote edits, entitlement bypass or usage-limit bypass.
  Addresses alone do not authorize acquisition. Keep external browser traffic
  blocked during tests. Do not restart the previously paused parity automation.
- Licensing/patent clearance remains unresolved. Technical success is not
  permission. Prefer independent adapter code and tests over further vendor copying.
- Manual cases are not measured physical truth or evidence of real-house accuracy.
  No Google/address/imagery adapter, remote shading/AI or DXF service is implemented.
- Respect exact source expiry/privacy for externally derived data. Current
  permanent browser library is intended for manual synthetic cases. Source-derived
  Google cases need expiry-aware import/storage/export before using that library.

## Verified state

Retained CAD 1.1876.0 and WASM are unchanged; hashes and frontend extraction
provenance are documented in README.md and ignored runtime/frontend manifests.
The default UI mounts retained Site menu, roof insert controls and property views.
Unknown metadata queries fail explicitly; local metric-unit cache needs no API.

Passing synthetic checks include:
- Pitched, flat and standalone-face drawing; L footprint retains six source
  corners and six initial faces. Their geometry survives local save/reopen.
- Internal/perimeter-line dragging, undo/redo, source pitch/height inputs and
  derived slope refresh. Fold-boundary drag changes derived fold height.
- Initial gable/hip/shed dormers; all three shape controls; initial hip/shed reopen.
- Flat/sloping/vertical folds; two sloping folds; gable+hip dormers together;
  gable dormer plus sloping fold on one host.
- Dormer pointer movement passes in 2D/3D and on an L host: every vertex
  translates consistently, topology/pitch are retained and undo/redo/reopen pass.
- Escape discards second-fold/second-dormer preview, restores complete committed
  geometry and adds no undo step. Keyboard Delete restores the original roof;
  undo recovers deleted fold/dormer and redo removes it again. Save/reopen passes.
- Oblique fold placement uses roof-surface picking. Empty-space click discards
  stale preview; committed exterior wall remains an occluder.

Simple legacy comparisons use 1e-9 m quantization where documented. Broader
interaction-cases.cjs compares finite face/wall geometry at 1e-7 m and preserves
source IDs/structure. These tests do not prove non-overlap or physical accuracy.
Passing runs check page/native errors, unexpected CSP blocks, metadata queries
and external request attempts; all were empty in verified runs.

### Fixed pointer defects

Read fold-placement-notes.md. Original oblique fold tool used ground-plane XY,
placing a clicked roof point outside the footprint. Local fold-placement.js uses
host-face surface hits, preserving native plan-view path, snapping and validity
checks. It ignores non-opaque edge/node handles and walls whose source is only
the current edited fold. This fixes vertical preview self-occlusion while retaining
committed-wall blocking. Adapter depends on private, version-specific interfaces.
Retained vendor bytes are not patched; runtime interaction behavior is adapted.

## Files and reproducible checks

- app.js: engine host, local named example library, save/reopen and native export.
- frontend-ui.js: control/provider bridge and local metadata cache.
- fold-placement.js: local surface-picking adapter.
- server.py: loopback server, explicit allowlist, artifact hashes and local CSP.
- probe.cjs: fresh credential-free Chrome/Playwright, external routing blocked.
- interaction-cases.cjs: detail placement, geometry, undo/redo and reopen scenarios.
- runtime/: ignored private vendor assets, captures/provenance, cases and evidence.

Check port 5191 before starting `python3 server.py` from this directory. Current
server session 51092 serves current modules; verify actual process
before reuse or restart. Never kill unrelated processes. JS/CSS edits are served live; restart
only for server changes. Preserve current example before reloading a user tab.

Run tests serially; screenshots/reports are shared. Browser checks may need host
execution approval; keep network guards. Typical commands from this directory:

```sh
node probe.cjs --verify
node probe.cjs --demo --ui-fields
node probe.cjs --demo --ui-dormers --dormer=hip --placement-only
node probe.cjs --demo --ui-dormers --dormer=shed --placement-only
node probe.cjs --demo --ui-fold-fields
node probe.cjs --demo --ui-fold-3d --angle=30
node probe.cjs --demo --ui-fold-3d --outside-fold
node probe.cjs --demo --case=dormer-and-fold
node probe.cjs --demo --case=fold-vertical-3d
node probe.cjs --demo --case=two-dormers
node probe.cjs --demo --case=fold-height-drag
node probe.cjs --demo --case=committed-wall-blocks
node probe.cjs --demo --case=cancel-fold
node probe.cjs --demo --case=cancel-dormer
node probe.cjs --demo --case=delete-fold
node probe.cjs --demo --case=delete-dormer
node probe.cjs --concave --case=fold-sloped-3d
node probe.cjs --prototype --verify
```

Interaction cases require exactly one host option: --demo or --concave. The latter
freshly draws/reopens an L footprint before detail tests, and retains reports with
`-concave` suffix. Its baseline projected-area check describes pre-detail roof,
not a new accuracy score for the final detailed model.

Passing reports: runtime/verified-<interface>-<test>.json. They record timestamps,
app/UI/adapter/style/probe/case source hashes. Hashes are captured before execution
and rechecked before accepting a report; editing sources during a run now rejects
verification. Native demo is promoted only after the standard roundtrip passes.
Generic probe.json/preview.png overwrite each run; failure.json/png can be historical.
Before-fix vertical trace: runtime/vertical-fold-before-fix.json.

Native integration facts: viewport `design-3d`; mouse-up is consumed next frame
(wait before another move). Roof menu opens on hover. Keep toolbar memoized and
root pointer propagation intact. Original stateFramework/reactive instance/UI
extension must agree. Inspector tab follows a supported nonempty selection.
Serialization rounds tiny floats; do not assert byte-exact coordinate identity.

## Current activity and next work

Latest completed: dormer movement in 2D/3D and on L host, plus
Delete-fold/Delete-dormer and L-host mixed dormers plus
sloping/vertical folds pass geometry, undo/redo and reopen. L host retains six
corners; sloping fold gives seven faces, vertical fold retains six.

Latest regression completed: all nine distinct workflows pass against current
adapter: L-host mixed dormers and sloping/vertical folds, rectangular fold/dormer
Delete, committed-wall blocking, rectangular vertical fold, opposite-view flat
fold and outside-click rejection. No page/native errors, external attempts,
CSP blocks or unknown metadata queries. No active test remains.

L vertical placement initially lost its live host-face collider behind a preview
wall. Trace: runtime/concave-vertical-before-fix.json. Adapter now copies committed
single-ring faces before placement, then uses independent ray/plane and point-in-
ring intersection only if no other solid hit remains and the current preview wall
is present. Known holes are excluded; unknown metadata/courtyards are unverified.
Last passing L-vertical report records committedSurfaceReads=2 and undo/redo/reopen.

Next: complex junctions beyond tested L host and additional foreign-roof geometries; broader mixed-detail hosts. Before reference export or cached geodata,
read integration-contract.md: current production benchmark expects DXF Buildings
lines, not native lab JSON. Coordinate frame, registration, height datum, holes,
visibility, provenance and source lifetime need explicit validated handling.
Do not rewrite evaluator, acquire paid data or manufacture ground truth.

If usage ends, leave files intact and record exact unfinished test/session,
evidence and next action here. Do not claim completion or rerun identical failures
without changed inputs. User resume phrase: "Read research/aurora-local-lab/CONTINUE.md
and continue."


## Latest movement coverage

Three passing cases: --demo --case=move-dormer, --demo --case=move-dormer-3d,
and --concave --case=move-dormer. Pointer movement is verified as uniform XYZ
translation rather than resizing; shape, pitch and vertex count stay unchanged.
Undo/redo and reopen retain finite face/wall geometry at 1e-7 m. No external
attempts, native/page errors, CSP blocks or unknown metadata queries. No adapter
or production changes in this pass. No active test remains; lab server healthy.

Next: separate-roof/foreign-occluder coverage, further complex junctions and input
contracts. Same-host committed-wall and disjoint foreign-roof occlusion now have separate
checks; do not generalize either to arbitrary structures or camera configurations. Preserve source expiry and
no-paid-call restrictions before imagery/reference integration.


## Foreign-roof occlusion continuation

Added --demo --case=foreign-roof-blocks. It draws a second flat roof through the
visible UI, confirms disjoint footprints, then sets local fixture edge heights so
the foreign roof intercepts a ray toward the edited host. Selection must leave
prior roof isolation before entering the intended host. Inactive roofs are picked
through derived face.building meshes; the fixture verifies physical ownership by
the front hit inside its disjoint rectangular prism, not only model identity.

First complete pass: placement is rejected and both roofs' full geometry survives
reopen. This case deliberately records undoRedo=false; it does not claim fixture
construction undo coverage. No adapter or production code changed.
Diagnostic repeat passed and retains front-hit coordinates/type and blocker
bounds. No active test remains. Native/page errors, external attempts, CSP blocks
and unknown metadata queries are empty. Native adapter and production files are
unchanged. Next: complex multi-level junctions and broader host/occluder shapes;
then reference/geodata contracts. No paid calls or data acquisition.


## Portable test-case export completed

Added case-export.js and visible Export test case button. It downloads a versioned
manual/unregistered package containing exact native JSON + SHA-256, copied native
building-face/wall XYZ rings, preserved known holes, explicit unknown-hole flags,
startup-pinned engine artifact identities and a running-exporter algorithm hash.
It explicitly says benchmarkCompatible=false and is not surveyed truth or a DXF
reference. Obstructions/trees/panels remain in raw native payload, not the geometry
view. No imagery/expiry-aware import or production benchmark adapter implemented.

Server restarted for the new allowed module route; current exec session 75747.
Five export/restoration workflows pass: basic, mixed dormer/fold, L host, standalone
face and preserved prototype draw/edit host. Standalone-face testing corrected a
harness assumption about perimeter/fold arrays. Holes, invalid indices/nonfinite
coordinates and unknown-hole flags are checked. Sources remain hash-frozen. No
active test remains. Export payload restoration is proven through the native
loader. Open test case now provides file import (see latest completion).
No paid/external calls, vendor source changes or production modifications.


Manual package opening is now implemented. Checksums remain integrity checks,
not authentication. External/imagery-derived cases still require expiry-aware
integration; benchmark DXF conversion and world registration remain unimplemented.


## Manual package-open completed

Added visible Open test case file control. It accepts matching-engine manual v1
packages after checksum, native format and geometry consistency checks. Validation
runs before storage mutation. Current nonempty example is saved first, incoming
case gets a fresh local ID, and one-hop source identity/provenance is retained
through subsequent saves/re-exports. Imported saved case also survives ordinary
home-page refresh. Fresh demo generation clears inherited import provenance.

All five workflows pass: basic, mixed-detail, L host, standalone face and preserved
prototype. Each rejects six bad-file classes without changing current scene or
library; edited current work is saved before replacement. Imported provenance
survives explicit save, refresh and re-export. New example opens empty; Reopen
saved restores imported geometry and metadata. Reports: verified-*-case-import*.json
and verified-original-ui-dormer-and-fold-import.json. No active test remains.
All have empty native/page errors, external attempts, CSP blocks and unknown
metadata queries. Server remains on 5191 (session 75747). Native artifacts and
production code are unchanged.

Next: general authoring/draft reliability and remaining roof controls, then cached
geodata and benchmark reference integration under integration-contract.md. Home
refresh restores saved active examples; unsaved edits are not background-autosaved.
Do not mistake manual case imports for registered/expiry-aware imagery imports.


## Saved-example recovery completed

Reopen saved preserves outgoing unsaved roof work when switching examples. When
reopening the active checkpoint, changed current geometry/name is first retained
as a separate '(recovery)' entry with recoveredFrom metadata. Save now retains
recovery/import record metadata. Repeated unchanged reopens do not create copies.

Six workflows pass: basic, mixed details, L host, standalone plane, preserved
prototype and imported-provenance. Each tests checkpoint/recovery restoration,
further recovery edits, switching away/back, latest-state preservation and metadata.
Standalone import was also rechecked with a genuine plane-height change. A prior
fixture had tried an undefined edge-height property; helpers now require finite
height and select the correct model type. No product corruption was established.
All current reports have no native/page errors, external attempts, CSP blocks or
unknown metadata queries. No active test remains; local server still on 5191.

Commands: append --recovery to a supported draw/import/interaction flow, e.g.
node probe.cjs --demo --recovery or --demo --import-case --recovery. Reports end
in -recovery.json; reopen-checks.cjs contains the full navigation checks.

Next: remaining roof controls and draft reliability, then reference/geodata
integration under integration-contract.md. Explicit navigation now protects edits,
but background autosave and complete version history are not implemented. Native
historyData exposes recentVersion, lastSavedVersion and hasUnsavedChanges (observed
in --inspect-storage); do not save in-progress tool previews or invalid geometry
when designing future autosave. Keep current no-paid-call and expiry constraints.


## Tab-local draft recovery completed

Committed manual changes and name edits now journal into sessionStorage after
roughly 1.2 seconds idle. Matching-engine drafts restore on ordinary refresh;
native format 3 is checked before loading. Named library checkpoints remain
unchanged. Undo to the saved baseline replaces a stale draft; deleting the last
roof restores an empty scene. Native drawing/placement modes, held pointer gestures
and invalid roofs defer serialization. Save clears the journal, and explicit
navigation pauses/invalidate pending serialization before clearing it.

Six workflows pass against matching current source hashes: pitched, L footprint,
standalone face, imported case plus navigation recovery, preserved prototype with
real line dragging, and combined dormer/fold. Each checks refresh, Undo baseline,
checkpoint separation, preview/pointer exclusion, explicit-save clearing, empty
scene recovery and saved-checkpoint restoration. Imported provenance is retained.
The import workflow also rechecks six rejected file classes, New/Reopen and
recovery-copy behavior. No native/page errors, external attempts, CSP blocks or
unknown metadata queries. Earlier slow reload/setup failures were harness timing:
repeated initialization now allows 30 seconds, and double-click selection can use
the visible native Edit roof action. No vendor changes were required.

Sources: tab-drafts.js, app.js, draft-checks.cjs; server allows the new module.
Verification: append --drafts to supported flows. Reports are
verified-original-ui-startup-drafts.json, verified-original-ui-concave-drafts.json,
verified-original-ui-single-face-drafts.json,
verified-original-ui-case-import-recovery-drafts.json,
verified-prototype-roundtrip-drafts.json and
verified-original-ui-dormer-and-fold-drafts.json in ignored runtime/.

No active test remains. Local server remains on 5191 (session 67308, PID 69403).
Tab drafts are not file backups, cross-tab synchronization or complete history;
closing the tab can lose them, and edits before the idle interval may be absent.
Save locally and Export test case remain the durable user actions. This feature
still accepts only manual/synthetic data under integration-contract.md.

Next required work: audit remaining manual roof controls against current runtime
behavior, choose the next unverified control/interaction and add a concrete
browser check before changing adapters. Do not repeat completed draft/import work.
Cached geodata and reference benchmark integration remain behind the explicit
expiry/registration contract. Do not modify the production evaluator or infer
real-house accuracy from manual cases. No paid/external calls or deployment.


## Roof properties and nondisruptive idle drafts completed

Audit found roof height/stories, roof type, Move and Explode controls. Added
roof-property-checks.cjs and --roof-properties. Whole-roof height edits translate
all roof-face and attached dormer vertices vertically while retaining XY, source
pitch and topology. Stories is coupled to roof elevation, not metadata-only.
Height/stories Undo/Redo and reopening pass for pitched, L and dormer/fold hosts
at 1e-7 m geometry tolerance. No control adapter change was needed.

Important correction: native property edits use deferred commits. A 500ms check
incorrectly suggested missing Undo history; tests now wait for recentVersion to
change. Experimental setter wrapper was removed. frontend-ui.js remains exactly
at SHA256 a761d4a0e9e59790d66d422d4d5c30eacf0f945f42d5710c4fbcf0208d9e98a8.

A real idle-draft bug was reproduced: getJsonToSave() uses serializeForSave(),
which can leave roof editing and create a save-preparation history entry, clearing
Redo. Drafts now call makeDesignJsonToSave() only on already-committed valid roofs.
Explicit Save/export keep their existing validation-oriented path. Expanded draft
checks enter roof editing, retain that exact mode through idle writes, Undo, wait
for an idle draft, require Redo to remain available, Redo/Undo again, then verify
refreshed geometry. Empty scenes, previews/pointer deferral, checkpoint separation,
save clearing and imported provenance remain covered. Native bytes unchanged.

- [x] Pitched roof properties + drafts.
- [x] L-roof properties + drafts.
- [x] Combined dormer/fold properties + drafts.
- [x] Standalone face drafts.
- [x] File import + saved-version recovery + drafts.
- [x] Prototype line dragging + roundtrip + drafts.

All six have matching current source hashes and empty native/page errors, external
attempts, CSP blocks and unknown metadata queries. Reports in ignored runtime/:
verified-original-ui-startup-drafts-roof-properties.json,
verified-original-ui-concave-drafts-roof-properties.json,
verified-original-ui-dormer-and-fold-drafts-roof-properties.json,
verified-original-ui-single-face-drafts.json,
verified-original-ui-case-import-recovery-drafts.json,
verified-prototype-roundtrip-drafts.json.

Focused REA static evidence: parent ev_e92eee039042b4a39d6bb9ef8d2e2bcde36484cc390ebf68f3926a1f3b637c61,
summary ev_bfeb6c38238ee460dae0412961197f02535622a07a4850c66dee2c592409714b.
Two exact method excerpts with original SHA/offset provenance remain in ignored
runtime/analysis/roof-history. Static semantic coverage has 32 unknowns and does
not prove full native call paths. Browser checks establish runtime behavior.

No active test remains (matrix session 21049 completed). Server remains on 5191,
session 67308, PID 69403. No production, vendor, paid API or remote changes.

Next required item: test visible roof-type conversion (pitched/flat) including
Undo/Redo, finite geometry and save/reopen, then whole-roof Move or Explode. Inspect
actual control markup using --audit-controls before choosing an interaction; do
not infer behavior from the label alone. Keep current source hashes frozen while
running checks. Broader multi-roof/courtyard cases and expiry-aware cached geodata
remain unverified; follow integration-contract.md before acquiring/importing data.


## Roof-type conversion and visible native messages completed

Added roof-type-checks.cjs / --roof-type. Visible native data-key flat/pitched
buttons are tested with aria-pressed state confirmation. Rectangle converts
4 -> 1 -> 4 faces; L footprint converts 6 -> 1 -> 6. Footprints stay unchanged,
plain flat geometry is horizontal, pitched geometry regains elevation variation,
Undo/Redo restores exact snapshots, and both states independently save/reopen at
1e-7 m comparison tolerance. This does not assert re-pitching reproduces every
prior pitch; Undo explicitly restores the original snapshot.

Native flatten() deliberately rejects roofs containing dormers or folds. The
host had dropped its notify messages, causing a silent refusal. app.js now shows
native title/message in the visible aria-live status region and records events.
No native guard was removed and no roof detail was deleted to force conversion.
This bridge displays plain notifications; action-button/dismissal UI is not added.

- [x] Rectangle conversion both ways plus expanded draft regression.
- [x] L conversion both ways.
- [x] Dormer + fold: native dormer refusal visible, geometry/version unchanged.
- [x] Fold only: native fold refusal visible, geometry/version unchanged.
- [x] Flat-roof draft refresh, Undo/Redo retention, preview/pointer deferral,
  checkpoint separation, Save clearing and empty-scene recovery.

All five current-source reports pass with empty native/page errors, external
attempts, CSP blocks and unknown metadata queries. Current reports:
verified-original-ui-startup-drafts-roof-type.json,
verified-original-ui-concave-roof-type.json,
verified-original-ui-dormer-and-fold-roof-type.json,
verified-original-ui-fold-sloped-3d-roof-type.json,
verified-original-ui-flat-drafts.json. Native/page error channels do not mean
there were no informational notifications; the two guard messages are expected.

Focused static REA parent ev_3c04d462dd78af9d0f0402603c8247bc33a19c1997aad2d0cf7d8e986ce2f8e8,
summary ev_a7020b55317016d1c755c626ca5a7889408da4cbe816febde92443fa5ac775cf.
Two inert method excerpts with exact source hash/UTF-16 offsets are retained in
ignored runtime/analysis/roof-conversion. They corroborate the guard/message
relationship; they are not a complete engine trace. Browser checks establish
visible refusal and persistence. Original conversion logic and vendor bytes stay
unchanged; only host notification handling, tests and docs changed.

No active test remains (session 19455 completed). Server remains 5191, session
67308, PID 69403. No production changes, paid calls or remote design operations.

Next required work: whole-roof Move through its visible inspector control. Check
actual pointer workflow, uniform translation of source/face/dormer geometry,
retained pitch/topology, Undo/Redo and reopen on plain, L and detailed hosts.
Only fix demonstrated adapter defects. Then test Explode semantics. Keep cached
imagery/geodata and benchmark integration behind integration-contract.md expiry,
coordinate-registration and source-lineage requirements; no paid acquisition.


## Whole-roof Move and idle recovery completed

Added roof-move-checks.cjs / --roof-move; append --move-3d for oblique view.
Correct native workflow: leave roof-edit isolation with Escape, select the whole
roof, click Move, then drag a roof-face interior. Move mode remains active after
a completed drag; Escape finishes it. Earlier face/edge/two-click experiments had
incorrect setup or hit targets. Entering Move directly from isolation cleared the
native movedRoofs targets in those experiments; normal selection retains them.
No native movement algorithm or control bridge modification was needed.

Five workflows now prove uniform XY translation of perimeter, roof faces and
walls, with all Z values, source edge pitches/heights, topology and IDs retained.
Detailed fixtures also check fold positions/pitch/height and every dormer vertex.
Undo/Redo restore exact snapshots at 1e-7 m. Opening Move and cancelling without
a drag adds no history and changes no geometry. This does not establish cancelling
an in-progress drag or rotation, multi-roof selection or arbitrary occluders.

Found required persistence gap: draft readiness excluded move.roof, although that
mode remains active after a committed drag. app.js now accepts idle Move while
pointer is released and roof validity passes. Native revision/idle gates remain.
Each test requires draft writing to preserve Move mode and refreshes from active
Move without explicit Save, verifying restored geometry. It then checks normal
Save/reopen. This does not save in-progress pointer gestures.

- [x] Plain roof, 2D.
- [x] L roof, 2D.
- [x] Plain roof, 3D.
- [x] Dormer + fold roof, 2D.
- [x] Dormer + fold roof, 3D.

All five current-source reports pass, with empty native/page errors, external
attempts, CSP blocks and unknown metadata queries:
verified-original-ui-startup-roof-move.json,
verified-original-ui-concave-roof-move.json,
verified-original-ui-startup-roof-move-3d.json,
verified-original-ui-dormer-and-fold-roof-move.json,
verified-original-ui-dormer-and-fold-roof-move-3d.json.
Source hashes include the new helper. No vendor/native/UI artifact edits or
production changes. Only app draft readiness, tests and docs changed.

No active test remains (session 17720 completed). Server remains 5191, session
67308, PID 69403. No paid calls, remote operations, deployment or commits.

Next required work: visible Explode control. Establish actual native conversion
semantics and guard/confirmation behavior first. Compare geometric coverage,
face coordinates, retained/lost source relationships, Undo/Redo and persistence
on plain, L and detailed roofs; do not assume explode keeps one roof or every
source ID. Keep imagery/geodata and reference integration behind current expiry,
registration and provenance contract. Do not modify the production evaluator.


## Explode conversion verified

Added roof-explode-checks.cjs / --roof-explode. Select whole roof outside isolation
and click visible Explode. Operation is immediate; success message is shown.
SmartRoof/dormer/fold sources are replaced by new roof.plane IDs, one per source
roof or dormer face. Original parametric relationships are removed. No conversion
algorithm or host adapter change was required in this pass.

Tests compare source polygon multisets with cyclic/reversed vertex ordering at
1e-7 m tolerance. Native exported roof outer rings and provided hole rings also
match before/after. Current five samples have zero courtyard holes; no courtyard
or arbitrary hole support is established. Derived building groups and wall
polygons change, so this is not lossless building-envelope conversion.

| Case | Output planes | Exported building groups | Exported wall polygons |
| --- | ---: | --- | --- |
| Plain pitched | 4 | 1 → 4 | 4 → 14 |
| L roof | 6 | 1 → 6 | 6 → 24 |
| Dormer + fold | 7 | 1 → 5 | 8 → 25 |
| Flat roof | 1 | 1 → 1 | 4 → 4 |
| Vertical fold | 4 | 1 → 4 | 5 → 17 |

All original roof outer rings match in these cases. Mixed-detail and vertical-fold
cases each have one original wall ring without an exact after-match, with added
wall polygons. This is a polygon comparison, not a wall-union or volume proof.
Do not treat exploded envelopes as equivalent benchmark truth.

- [x] Plain pitched roof.
- [x] L footprint.
- [x] Dormer plus sloping fold.
- [x] Flat roof.
- [x] Vertical fold.

Each current-source workflow verifies independent plane type/count, finite source
face geometry, replaced parametric sources, native success notification, Undo/Redo,
idle-draft refresh and explicit Save/reopen. Restored derived face/wall/hole rings
match the post-Explode state after both reload paths. Undo restores original
source relationships and native roof/hole rings. Native/page errors, external
attempts, CSP blocks and unknown metadata queries are empty.

Reports: verified-original-ui-{startup,concave,dormer-and-fold,flat,
fold-vertical-3d}-roof-explode.json in ignored runtime/. Source hashes include the
new helper. All test sources frozen during verification. No product, vendor,
production, paid API or remote design changes; only tests and docs this turn.

No active test remains (session 90612 completed). Server remains 5191, session
67308, PID 69403. Keep native artifacts and private examples intact.

Next required work: independent face editing after Explode. Select one generated
roof.plane through current UI, inspect actual height/pitch/edge controls and edit
one face. Verify other source planes remain unchanged, native history commits,
Undo/Redo, draft refresh and saved reopen. Distinguish source-plane independence
from changed derived building grouping/intersections. Start with plain roof,
then L/detailed sources. Preserve the native exporter/integration-contract.md
limitations; no production evaluator rewrite or imagery acquisition.


## Independent face height/pitch editing verified

Added plane-edit-checks.cjs / --plane-edit after --roof-explode. A real canvas
click selects a generated plane in 2D. Visible Height to roof base and Pitch
controls change that plane. Height translates its vertices vertically; pitch
changes its geometry. Every other source-plane snapshot stays unchanged, including
IDs and geometry. This does not imply derived native building intersections or
wall groups remain unchanged.

Native edit revisions are awaited explicitly. Undo/Redo restores each edit;
idled drafts refresh into the edited state; explicit Save/reopen retains geometry
and displayed height/pitch fields. Comparison tolerance is 1e-7 m. Inspector
numbers can be rounded: height changes use the absolute entered target minus the
exact native height, not displayed-value deltas. An earlier fixture wrongly
assumed those deltas were identical; no product defect was established.

- [x] Plain source: 4 planes.
- [x] L source: 6 planes.
- [x] Dormer/fold source: 7 planes.
- [x] Flat source: 1 plane, subsequently tilted by the test.

Four current-source reports pass with empty native/page errors, external attempts,
CSP blocks and unknown metadata queries:
verified-original-ui-startup-roof-explode-plane-edit.json,
verified-original-ui-concave-roof-explode-plane-edit.json,
verified-original-ui-dormer-and-fold-roof-explode-plane-edit.json,
verified-original-ui-flat-roof-explode-plane-edit.json.
These also rerun their source Explode checks. No product or vendor modification
was needed; only tests and documentation changed this turn.

No active test remains (session 9267 completed). Server remains 5191, session
67308, PID 69403. No commits, deployment, paid calls or production edits.

Next required work: pointer-driven boundary/vertex reshaping on an independent
plane, including planes generated by Explode. Inspect actual handle/mode workflow
first. Verify selected-plane geometry changes as intended, other source planes
stay unchanged, native validity and Undo/Redo work, and draft/saved recovery holds.
Numeric height/pitch verification does not establish edge/vertex dragging. Keep
manual authoring as scope; no automatic house-modeling work. Existing imagery,
expiry, reference/export and independent-accuracy limits remain unchanged.


## Manual authoring guidance and outline editing completed

User clarified manual test-case creation is the goal and questioned test-only
milestones. Prioritize a usable authoring flow and demonstrated integration gaps.
Clearly distinguish existing native behavior being verified from new host features.
Do not drift into automatic reconstruction or endless test permutations.

Actual host/UI changes this turn:
- Header now identifies the Roof test-case builder and provides How to model.
- Expandable guide covers drawing, roof/face edits, dormers/folds, Move, checkpoint
  saving/export, tab drafts and Explode consequences.
- Independent-face inspector now explains outline dragging and numeric edits.
- Guide is HTML/CSS and the inspector hint is independent host React code; no
  retained vendor asset or native algorithm was edited.

Existing native boundary behavior is now established: select an independent
plane, drag a perimeter edge or a white corner node directly in normal selection
mode. No extra isolation/Edit outline control is required. Source pitch is
retained, selected projected area changes, at least one vertex remains stationary
(reshaping rather than whole-face Move), and all other source planes stay fixed.

Seven frozen-source workflows pass validity, finite coordinates, native history,
Undo/Redo, idle draft refresh and saved reopening at 1e-7 m:
- [x] Plain plane: edge and corner.
- [x] L-source plane: edge and corner.
- [x] Dormer/fold-source plane: edge and corner.
- [x] Flat-source plane: corner.

Reports: verified-original-ui-{startup,concave,dormer-and-fold}-roof-explode-plane-boundary.json
and corresponding -corner.json files, plus
verified-original-ui-flat-roof-explode-plane-boundary-corner.json. These verify
existing native modeling controls; new code adds guidance and regression checks.
All have empty native/page errors, external attempts, CSP blocks and unknown
metadata queries. Source identity is checked before/after each run.

How to model opens successfully in the plain-corner flow and a separate startup
smoke run. Expanded guide and contextual face hint were visually inspected; guide
capture is ignored runtime/manual-modeling-guide.png. Current user tabs were not
reloaded or edited. Save current work before refreshing to load the new guidance.

No active tests remain (matrix 20646 and guide smoke 57368 completed). Server
remains 5191, session 67308, PID 69403. No paid calls, production edits, deployment
or commits. No changes to native CAD/WASM or retained frontend assets.

Next required work: exercise a practical manual case end-to-end and fix actual
usability gaps. Focus on direct edge-length/dimension entry and inserting/removing
outline corners, whose human workflows are not established. Inspect existing
native controls first; expose missing host bindings only when demonstrated.
Keep checks narrow and tied to user-visible work rather than broadening matrices
as the main output. Existing source expiry, unregistered-coordinate and benchmark
format limitations still apply. No automatic house modeling or evaluator rewrite.


## Missing roof-corner inspector implemented

Actual authoring gap: selecting node.perimeter produced a blank inspector. Added
independent host Roof corner inspector bound to existing native
changePerimeterNodeAngle action. Click a white SmartRoof corner while editing,
enter Plan angle, choose whether to move the opposite adjacent corner, and Apply.
Selected corner remains fixed; one neighbor moves. Concave corners use the smaller
between-edge angle (0 < angle <= 180), not a 270-degree reflex-angle display.

Existing native Length input was already available in perimeter-edge inspector;
no duplicate was added. Edge guidance and How to model now point to Length and
new corner Angle controls. UI was visually inspected; private capture is
runtime/corner-angle-editor.png.

Native cached node.angle could stay at 95° after Undo restored 90° coordinates.
Own inspector now measures current plan angle from adjacent source coordinates
for display/no-op detection. Native callback still edits geometry; no solver or
vendor code is replaced. Display rounds to two decimals, but an untouched Apply
never quantizes the underlying value or adds history. Explicit fractional inputs
are preserved in geometry. Incomplete outlines and invalid numeric ranges are
guarded before dispatch.

- [x] Plain convex corner, both moving-side choices.
- [x] L-source concave corner, both choices.
- [x] Dormer/fold-source corner, both choices.

Each frozen-source case tests real pointer corner selection, existing Length
input, measured fractional target (95.123°), fixed selected corner, exactly one
adjacent corner moved, different moving neighbor for opposite-side choice,
unchanged source pitches/heights, native validity, Undo/Redo including displayed
angle, invalid input, untouched-Apply history, draft refresh and saved reopen.
Geometry tolerance is 1e-7 m; angle checks use 1e-7 degrees. Expected display can
round by up to 0.005°. Native/page errors, external attempts, CSP blocks and
unknown metadata queries are empty.

Reports: verified-original-ui-startup-corner-angle.json,
verified-original-ui-concave-corner-angle.json (innerCorner=true),
verified-original-ui-dormer-and-fold-corner-angle.json. corner-angle-checks.cjs
contains the full workflow. No active tests remain (session 22821 completed).
Server remains 5191, session 67308, PID 69403. User's browser was not reloaded or
edited. Save current work before refreshing to load new controls.

Focused static REA parent ev_d77b6a24ecaf00af017613e1dad0d26d7be0062f139b1f06419e896e27477387,
summary ev_98b02276665174115ff27e573b7a03aeeb4bf8b32fe46a43d887268fcccc4827.
Exact inert callback/provenance retained in runtime/analysis/corner-angle; not a
complete native call-path analysis. Runtime coordinate checks establish behavior.
Changes are own frontend UI/CSS/guide and tests/docs. No native CAD/WASM, retained
frontend artifact, production, paid API, remote operation, deployment or commit.

Next required work: adding/removing outline corners in a practical manual case.
Inspect existing native gestures/controls first; do not create duplicate geometry
logic if native code already supplies them. Prioritize missing host bindings and
clear authoring steps rather than test-only permutations. Current native cached
angle is not authoritative after Undo; derive/check source coordinates. Keep
manual test-case scope, source expiry/reference-export limitations and production
boundaries. No automatic reconstruction or evaluator rewrite.


## Closed-outline Remove corner implemented

Added Remove corner to the local SmartRoof corner inspector. It calls existing
native roof.closePerimeter(selectedNode), commits through native datastore and
selects a surviving neighbor. It removes the selected node and joins its adjoining
outline edges while keeping the roof closed. This is own host convenience UI,
not a new roof solver. Button disables at three remaining corners and explains
the minimum. The guide now exposes the control. UI layout was visually inspected;
private capture is runtime/corner-remove-control.png.

Native direct node deletion opens a perimeter; it is not equivalent to this
closed-outline command. Native roof-edit mode contains a double-click-open-end
continuation path. Those add/redraw gestures are not yet end-to-end verified;
do not advertise adding corners as implemented. Bounded prototype inspection did
not locate a public split/insert method on the sampled roof/edge models, which
is not proof that no such feature exists elsewhere.

- [x] Plain 4→3 corner removal: closed valid native roof, unchanged remaining
  positions, selected node removed, Undo restores it, Redo, draft refresh and
  saved reopen; three-corner limit remains disabled after reload.
- [x] L-source 6→5 corner removal: same geometry/history/recovery checks.
- [x] Existing fractional corner-angle workflow regressed with new control.

All three current-source reports pass with empty native/page errors, external
attempts, CSP blocks and unknown metadata queries:
verified-original-ui-startup-remove-corner.json,
verified-original-ui-concave-remove-corner.json,
verified-original-ui-startup-corner-angle.json.
Topology edits can recreate identical walls in different datastore order; the
removal helper sorts walls by source ID before comparing geometry. No wall loss
was established by the initial order-only mismatch. Other native metadata order
and source fields remain checked. Attached-detail preservation for arbitrary
corner removal is not established; outline edits rebuild the native roof.

Focused static REA parent ev_c13b5526ea7e9660c17841a3e3f43df114087875216ff0870d7bb46c806f6a2d,
summary ev_f42c6c9f3d5a8e175bbe826125807e4822e7344c6d0479708fedcd9653267ea6.
Exact inert ring-model methods/provenance are in runtime/analysis/corner-remove.
These establish the sampled API body, not full native runtime correctness.
Runtime checks above establish tested behavior. Public SmartRoof help was also
reviewed for general workflow, but did not establish an insertion gesture for
this captured version: https://help.aurorasolar.com/hc/en-us/articles/360034501014-SmartRoof-Best-Practices-and-Tips

No active test remains (11322, 84656, 81051 completed). Server remains 5191,
session 67308, PID 69403. Save current work before refreshing user tab to load
new controls. User's tab was not changed. No vendor/native, production, paid API,
remote design, deployment or commit changes.

Next required work: add/redraw outline corners in a practical manual case. Inspect
native modifier/transform handles and open-perimeter continuation first. Establish
Escape, Undo and save behavior before exposing any new control that opens an
outline. Do not implement duplicate roof geometry. Keep manual authoring scope;
focus on usable bindings and actual gaps, not expanding test permutations.
Source expiry, unregistered coordinates and reference-format limits still apply.

## Midpoint corner insertion implemented; detail boundary enforced

New host control: select one SmartRoof perimeter edge, choose Add corner at
midpoint, then drag the selected white corner into place. Original endpoints stay
fixed during insertion; two replacement source edges inherit original pitch and
height. Native ring primitives create the node/edges and native engine rebuilds
faces. No solver, vendor bundle or retained frontend artifact was changed.
Control uses private `_makeNewNode` / `_makeNewEdge` methods of the pinned engine;
this version-specific dependency must be checked before any engine upgrade.

A mixed dormer/fold test exposed a real limit: insertion plus subsequent corner
drag and Undo/Redo left native roof `isValid=true`, `isConstructed=false`,
`needsReconstruct=false`, `error=false`. Idle drafts correctly refused to persist
that unconstructed state. Repeating with readiness diagnostics reproduced the
failure. Do not weaken draft gates or claim attached-detail preservation. Exact
causal step was not isolated; no silent loss of user work occurred because tests
used fresh synthetic browser contexts. Private failure screenshot/state retained
as runtime/corner-add-detail-failure.{png,json}; diagnostic came from session
44395. The failure screenshot is after reload, not a full pre-reload model dump.

Both Add corner and Remove corner now disable while the roof has dormers or
folds, including handler-side rechecks. Their inspectors explain: finish outline
first; remove those details before changing corner count. This conservative
boundary prevents the failing combined workflow; removal on detailed roofs was
not separately proven defective. Existing angle/detail controls remain available.
Open-perimeter native redraw remains unverified and is not exposed by these
controls. No outline is left open by midpoint insertion.

Completed verification: plain Add corner (54916), L Add corner (19291),
mixed-detail guard (89145), and plain removal regression (8037) passed. No active
test remains. Plain and L insertion tests use real pointer
edge selection and new-corner dragging, native validity and construction, original
corner positions, original face-plane membership and summed projected area
before drag, split-edge pitch/height, separate insertion/drag Undo/Redo, idle draft
refresh and explicit saved reopening. Area/plane checks are limited geometric
checks, not proof of globally correct roof topology or measured accuracy.

Visual inspection: runtime/corner-add-control.png shows visible enabled control
and retained Length input in edge inspector. User's browser was not changed.
README has practical workflow and detail restriction. Four final reports:
- verified-original-ui-startup-add-corner.json
- verified-original-ui-concave-add-corner.json
- verified-original-ui-dormer-and-fold-add-corner.json
- verified-original-ui-startup-remove-corner.json

All pass with empty native/page errors, external attempts, CSP blocks and unknown
metadata queries. Their source hashes match current product/test files. Earlier
current-source claims refer to each historical milestone's recorded hashes.
Server remains 5191, session 67308, PID 69403. No active test or agent remains.
Save current work before refreshing user tab to load new controls.

Next required work after finishing current checks: practical dimension-led manual
case. Existing perimeter Length input was observed, but real numeric changes and
its two moving-side choices were not yet verified. Establish actual native
endpoint movement and shared-edge/roof validity, Undo/Redo and saved recovery;
fix only demonstrated integration gaps. Keep outline-first detail workflow.
No automatic reconstruction, evaluator rewrite, imagery acquisition, paid calls,
server bypass, remote design edits, deployment, commits or vendor publication.
Manual cases remain unregistered and not surveyed truth. Source expiry/reference
format constraints in integration-contract.md still apply.

## Perimeter Length precision and endpoint choices

Completed: focused native Length workflow. Earlier corner-angle test already
included one +0.5 m length change followed by Undo; the preceding resume point
overstated that gap. New edge-length-checks.cjs establishes both endpoint choices,
explicit fractional entry, endpoint motion, history and full persistence.

Actual host improvement: retained Length field now has accessible name Roof edge
length in meters and associated explanatory text. Icon choices have accessible
names/hover labels Keep first corner fixed / Keep second corner fixed. Names
refer to native edge.nodes order, not screen left/right. Native anchorLeft keeps
second node fixed; anchorRight keeps first fixed. Retained native handlers remain
responsible for geometry. Own PerimeterEdgeFields wrapper adds only DOM labels;
no vendor bytes or native edit action were replaced. Edge hint explains circle =
fixed end, arrow = moving end, meters, blur-to-apply and adjoining-edge changes.

Plain and L cases passed on final UI/test sources (sessions 34754, 61853).
Detailed dormer/fold case also passed (24939). No active tests remain. All three
reports match current product/test source hashes. Successful checks use pointer
edge selection, both labeled choices,
+1.2345 m exact target, exactly one endpoint moving along original edge direction,
all other perimeter nodes fixed, source pitches/heights unchanged, valid and
constructed roof, finite faces, Undo/Redo and rounded display, untouched blur
preserving exact geometry/history, idle-draft refresh and Save/reopen.

README has human workflow. Native Length is an individual edge edit, not a whole
rectangle resize; adjacent edge lengths and corner angles change. Do not add
another length solver. No automatic modeling, production edits, paid data, remote
requests, engine changes, deployment or commits. User browser remains untouched.
Visual inspection passed: runtime/edge-length-controls.png. Fields remain usable
and explanatory text is visible; native side panel scrolls to Length. Independent
visual run had no external request attempts. Final reports:
- verified-original-ui-startup-edge-length.json
- verified-original-ui-concave-edge-length.json
- verified-original-ui-dormer-and-fold-edge-length.json

All have empty page/native errors, unknown metadata, CSP blocks and external
attempts. Tests use 1e-7 m geometry tolerance and <=0.005 m displayed rounding.
Detailed model remained constructed and persisted; this does not promise every
detail vertex stays fixed when its host geometry changes. No native geometry
fix was required. Changes are small host accessibility/guidance improvements,
focused tests, and docs. Do not describe them as a newly implemented length
solver or a major new modeling engine capability.

Next required work: one practical outline-first manual case, from a blank drawing
through dimension edits and corner insertion, then adding dormer/fold details,
naming, checkpoint saving and portable export/reimport. Verify details can be
added after the outline edits, not just tested independently on a pristine host.
Fix actual usability/data-loss gaps found in that combined flow. Avoid expanding
test matrices as the main output. Corner-count controls must remain guarded when
details exist. No need to repeat completed length/corner permutations without
new evidence. Open-outline redraw remains unverified; it is not required to
replace the working closed-outline midpoint path.

Server remains port 5191 (session 67308/PID 69403). User tab untouched. Preserve
manual/unregistered package contract and source-expiry restrictions; no imagery
acquisition, paid calls, production evaluator edits, deployment or commits.

## Practical manual authoring flow and portable names

Completed one combined flow: blank native pitched-roof drawing, fractional Length
edit, midpoint insertion, real pointer corner reshape, gable dormer, sloping fold,
named checkpoint, saved reopen, portable export, New example, file import and
imported Save/refresh. Details are placed on two large distinct faces, not the
small new eave face. Native roof remains valid and constructed. This verifies
outline-first composition, not arbitrary detailed-roof perimeter editing.

Actual usability gap found by source inspection: export omitted example name,
used only a UUID filename, and import always replaced name with Imported test
case. Fixed own host/exporter: optional v1 `name` field, readable filename slug
plus case ID, name validation and import restoration. Older unnamed v1 files
remain accepted with original fallback. Input/import limits are 500 characters;
control characters and nonstrings are rejected. Name is cosmetic metadata, not
covered by native payload checksum and not authenticated provenance. Exporter
algorithm fingerprint now includes the name normalizer. No native/vendor bytes
changed, and no roof solver was added.

New helper manual-authoring-checks.cjs / --manual-case runs combined flow. Native
drawing uses existing fresh blank pointer path; details reuse existing native
placement helper. It also checks package checksum/manual-unregistered flags,
readable suggested filename, imported name persistence, unnamed-v1 validation
and bad-name rejection. Native full geometry comparison uses 1e-7 m tolerance.
Private worked sample: runtime/manual-outline-first.roofcase.json. It contains
manual native design + face/wall geometry, no imagery. No benchmark compatibility,
world registration or measured-accuracy claim. User can open it with Open test
case; it is not inserted into their browser automatically.

Final combined run passed (45629). First run (99710) only failed an expected
filename-prefix assertion: separators produced three adjacent hyphens. Slug now
collapses consecutive hyphens; model/dormer/fold checks had already passed.
No native geometry defect or user-data loss was established. Name/import
regression passed (95861): six existing malformed-package classes rejected
without changing library/scene, outgoing edited example retained, import geometry,
refresh, saved/re-exported provenance and New/Reopen all pass.

Final reports verified-original-ui-manual-authoring.json and
verified-original-ui-case-import.json match current source hashes and contain no
native/page errors, external requests, unexpected CSP blocks or unknown metadata.
Separate fresh-browser file-open + 3D visual run passed; capture is
runtime/manual-outline-first.png. Native artifacts retain original pinned hashes.
No active tests remain. Server remains 5191, session 67308/PID 69403. User tab
was not reloaded or modified. README describes worked file and named exports.

Next required work: roof starter presets for faster manual authoring. Default
pitched insertion yields a hip-style roof; gable/shed creation still requires
manual face settings. Inspect existing native edge Pitch type/vertical controls
and available actions first, then expose missing host preset bindings only when
native behavior is established. Start with a gable starter on a plain outline;
verify finite valid construction, intended faces/ridge, source pitch/height,
Undo/Redo and save/reopen. Do not add a competing roof solver or change vendor
bytes. Keep preset outline edits before dormers/folds and retain corner guards.
Do not turn this into a new test-only matrix or automatic reconstruction task.
Source-expiry/registration/reference-format constraints remain unchanged. No
paid/remote calls, Aurora account actions, production edits, deployment or commits.

## Native-backed roof starters implemented; verification active

New whole-roof inspector card: Hip/Gable/Shed, proposed pitch, Apply roof starter,
and Turn starter 90°. Each application sets existing native perimeter-edge
pitches in one datastore commit. Gable uses two opposite pitched eaves and two
native vertical edges (pitch 90); shed uses one pitched eave and three vertical
edges; hip pitches all four. No roof geometry solver or vendor bytes changed.
Native vertical-edge control was first exercised in isolated browser; its source
pitch became 90 and native construction remained valid. Opposite-edge settings
then produced a valid two-face gable at requested pitch.

Supported boundary: one closed, valid/constructed pitched rectangle, four corners,
equal edge heights, no dormers/folds. Rectangle check uses source endpoint angles
and graph adjacency, not roof reconstruction. Other footprints, flat roofs and
detailed roofs disable commands with explanation; handlers recheck eligibility.
Footprint/source edges/heights stay fixed. Existing mixed pitches are replaced by
selected uniform preset pitch. Form settings are proposed values, not an inferred
current shape after Undo/reload. Hip has no turn; gable has two axes, shed four
directions. Range is above 0° through 80°. Unchanged Apply adds no history.

First plain run (56369) passed all three shapes, both gable axes, all four shed
directions, actual gable ridge/face checks, unchanged footprint/heights, one-step
Undo/Redo, unchanged Apply, invalid pitch, draft refresh and saved reopening.
Source changed afterward only for guide wording and flat-fixture guard handling;
rerun plain against final sources before final completion. L guard passed final
sources (72320). Detailed guard is running (89035). Still required: flat guard,
final plain run, visual inspection and final source-hash check. Run serially and
keep product/test sources frozen. README and How to model expose starter workflow.

Next resume: finish active checks and fix actual failures. Keep manual authoring
scope and detailed-roof corner guards. No production edits, paid/remote calls,
auth/entitlement bypass, deployment, commits or vendor publication. User browser
untouched. Source expiry, manual/unregistered coordinates and DXF benchmark
limits still apply.


Flat-source finding: native flat creation stores four perimeter pitches of 90°,
not four zero pitches. Flat test 11522 actually completed every preset/turn and
restored flat geometry on Undo; it was not a disabled-guard test. Starter supports
flat rectangles directly. Removed the inaccurate pitched-only wording and the
unnecessary all-zero-pitch predicate. README/guide corrected. Guard remains
rectangle + equal source heights + valid/constructed + no details. Final plain,
flat and unsupported-guard runs must now use these final sources.


## Roof starters completed; next fix is tall-roof Fit

Final-source runs passed:
- plain starters 13828 → verified-original-ui-startup-roof-starter.json
- flat conversion 75417 → verified-original-ui-flat-roof-starter.json
- L guard 64502 → verified-original-ui-concave-roof-starter.json
- detailed guard 72177 → verified-original-ui-dormer-and-fold-roof-starter.json

All four reports match current product/test hashes. Plain and flat workflows each
check Hip (4 source faces), Shed in four directions (1), and Gable in both axes
(2), source pitch 31.25°, finite valid/constructed geometry, fixed footprint/source
edge IDs/heights, actual two-ended level gable ridge parallel to pitched eaves,
90° ridge-axis change, and one-step Undo/Redo for every application/turn. Final
rotated gable survives idle draft refresh and explicit Save/reopen. No-op Apply
and invalid-pitch checks pass. L/detailed controls disable and leave full geometry
unchanged. Native/page errors, metadata misses, CSP blocks and external attempts
are empty. Native artifacts unchanged. No active functional tests remain.

Visual run 3053 produced runtime/roof-starter-{gable,shed,hip}.png. Gable/hip card
layout and shapes are usable. Shed exposed a real native Fit issue: upper roof is
clipped. Settled repro 1688 still clips after 1800 ms, so do not dismiss as short
animation timing. Viewport is 960×788; projected roof Y extends from 184.9116 to
826.0852 (bottom-origin), beyond its 788 px height. Peak is 13.6596 m for 30° shed.
Roof geometry is still valid/constructed. Exact camera/bounds cause is unproven.
Fresh isolated repro 90511 confirms same bounds. No user design was involved.

Private evidence: runtime/roof-starter-shed-clipped.png,
runtime/analysis/fit/clipping.json, and clipping-probe.cjs (copied own probe,
not vendor code). That script is currently a diagnostic, not a passing regression.
README records manual zoom workaround. Do not claim full 3D Fit correctness.

Next required work: fix own host Fit binding for tall roof geometry using native
camera APIs, then turn this repro into a real viewport-containment check. Avoid
changing retained vendor bytes or camera math without an established native API.
Current Fit is the native focusOnAll action. Bounded runtime inspection found:
- viewport has cameraModel, camerasThree, bounds; cameraModel serialization and
  available setters have not yet been inspected.
- viewportManager: registerCameraModel/getViewportByCameraModel/createCameraModel/
  updateCameraModel; no direct focus/fit method appeared in sampled prototypes.
- worldSpace is a perspective camera with zoom/focus/getViewBounds.
- engine callbacks include focusOnAll, focusOnSelection, zoomAndOrbit,
  animateCameraToAngle, activateZoom/deactivateZoom, setCameraPosition/selectCamera.

Use small bounded evidence/probes; no large vendor analyzer. Preserve zoom/orbit
and existing whole-scene semantics, not just the new shed. User can zoom out
manually meanwhile. After Fit fix, verify adding dormer/fold details after gable
and shed starters through a practical authoring flow. Do not rerun all completed
preset permutations unless source changes/failures justify it.

User tab untouched. Server stays 5191, session 67308/PID 69403. Save work before
refreshing to load starter controls. No paid/remote calls, production changes,
auth/entitlement bypass, deployment, commits or vendor publication. Keep source
expiry, unregistered manual coordinates and reference-format limits.

## Height-aware host Fit implemented; interaction checks active

Current own app.js Fit binding aggregates native focus-model bounds plus computed
roof/dormer faces and implicit walls. It encloses those bounds about the native
XY-center/ground-Z orbit pivot, uses the smaller actual horizontal/vertical field
of view with margin, then invokes existing native CameraAnimationController.
Native model/radius conversion is respected. It waits for an existing animation;
new host commands or viewport pointer/wheel input invalidate a waiting request.
No geometry commit or vendor byte change. Shape/selection/mode are not changed.

Native evidence: retained focus callback explicitly uses target Z=0 but computes
radius from half 3D box diagonal/tangent. Native roof bounds already included the
13.6596 m peak; missing roof height in its bounds was NOT the observed cause.
Own enclosure uses full height relative to ground pivot and a bounding-sphere
sine constraint. Ground pivot retained for native orbit conventions. Direct raw
camera setters changed model values without updating render; not used. Native
updateCameraModel copies model fields, not a render-sync API; not used.

Settled runtime proof 57236: native animation with independent framing gives
projected roof X 221.4171..728.5519, Y 279.7337..687.0867 inside 960×788 viewport;
angle remains 35°, target Z=0, camera distance 51.2563. Host reproduction 67211
matches those bounds. No native/page errors or external attempts.

REA small inert exact callback excerpt + original SHA/UTF16 offsets retained in
runtime/analysis/fit/native-excerpt. Parent ev_03bd86eeb356754d3fc1ead47e471c93d5cded8b9f8951fd38218a4b87781487;
summary ev_8b454032b803484a51512ad60b0dbea186dc2e459a8e20e277f113dc7b198724.
Static semantic coverage is partial (enclosing bindings initially unresolved);
this is not a complete native camera trace. Native focus-type identifiers were
resolved from bounded sky/components/types.ts export and are mirrored as SDK
metadata to preserve whole-scene membership. Runtime proof establishes framing.

New view-fit-checks.cjs / --view-fit checks real projected roof/detail/wall vertices,
depth clipping, geometry/history, mode/selection, native view transitions and
portrait resize. First --demo --view-fit run 78599 advanced through 3D, repeat,
2D and orbit containment/history assertions, then timed out waiting for a native
wheel gesture to change model.radius. This is not yet attributed to host code;
zoom may use another native gesture/state. No final verification report accepted.
Native zoom diagnostic running in 41068; inspect its output before edits. Keep
Fit implementation intact while diagnosing actual gesture. Still required: finish
zoom/portrait checks, multi-roof/detail and empty cases, visual check and final
hashes. No broad preset reruns unless source behavior changed.

Only lab files changed; no user tab, production, paid API, account/design, auth,
deployment or commit actions. Native engine/retained frontend unchanged.


## Height-aware Fit completed and verified

Final sources pass:
- tall-shed view/interaction check 83087: verified-original-ui-startup-view-fit.json
- dormer/fold/wall check 72688: verified-original-ui-dormer-and-fold-view-fit.json
- two separate roofs 3924: verified-original-ui-foreign-roof-blocks-view-fit.json
- empty scene 41164: verified-original-ui-startup-view-fit-empty.json

All four current source hashes match. Native/page errors, external attempts, CSP
blocks and unknown metadata are empty. Every populated flow tests 3D containment,
repeat Fit, 2D, explicit 3D restoration + orbit to 55°/145°, native wheel zoom and
refit, 720×900 window (400 px scene width), then original 1280×900. Actual projected
roof/dormer/wall vertices stay inside view and near/far depth planes. Geometry
snapshots at 1e-7 m, design history revision, mode and selection remain unchanged.
Only camera framing changes. Empty Fit returns Nothing to fit without edits.

Earlier wheel failures (78599, 28823) were fixture mistakes: it tried a 3D orbit
without first switching back from native 2D orthographic mode, then watched radius
for orthographic zoom. Native 3D wheel diagnostic 41068 changed radius normally.
Explicit 3D restore and assertion of actual requested pose fixed the fixture;
77011 passed before final empty/range handling, 83087 passed final sources. Hover
is also allowed a frame before wheel dispatch. No product zoom patch was needed.

Native 2D is orthographic and intentionally uses original focusOnAll callback.
New host 3D Fit uses native scene-type bounds + computed roof details/walls,
conservative ground-pivot sphere enclosure with horizontal/vertical FOV, native
radius conversion and CameraAnimationController. It waits for pending native
animation and rejects nonfinite framing ranges before animation. Empty scene
check precedes native projection fallback. No vendor method was replaced.
Internal SDK focus/keyboard shortcuts remain native; only own top Fit/Lab run
binding changed. Conservative framing leaves some margin to preserve orbit.

Final visual check 21715: runtime/view-fit-shed-fixed.png. At original failing
35°/30° pose, roof pixels are X 221.417..728.552 and Y 279.734..687.087 inside
960×788 scene. Original preserved clipped image/provenance remain in runtime/.
No user tab was reloaded or edited. Native CAD/WASM hashes unchanged. No active
tests remain; server still 5191 (session 67308/PID 69403).

Next required work: practical details-after-starters authoring. Apply Gable to a
plain rectangle, then place a dormer and fold through actual controls, name/save,
export/reimport. Repeat only the distinct Shed single-face case if needed; choose
valid separated placements rather than assuming two host faces. Verify native
validity/construction, expected source details, source footprint/pitch and saved
geometry. Fix any demonstrated usability or data-loss gaps. Do not rerun broad
completed preset/Fit matrices without changed behavior or new failure. Keep
starter/corner guards when details exist; do not convert existing detailed roofs
with a starter. No automatic reconstruction/evaluator work, paid/remote calls,
auth bypass, deployment, commits or vendor publication. Existing expiry,
manual/unregistered coordinate and benchmark-format boundaries remain in force.

## Details after starters passed; authoring gap selected

Gable flow 54672 and Shed single-face flow 33568 passed blank drawing → starter →
dormer/fold → named save/reopen → export → New → import → Save/refresh. Own helper
now supports --manual-case --manual-starter=gable|shed. Source footprint, perimeter
edge IDs/pitches/heights stay fixed while adding details. Private worked files:
runtime/manual-gable-details.roofcase.json and manual-shed-details.roofcase.json.
Shed uses separated uphill/downhill positions on its one host face, not a second
nonexistent face. No native/product defect found; these are composed native
workflows, not newly implemented dormer/fold algorithms.

Next actual authoring gap: individual native Length changes one endpoint and
turns a rectangle into a trapezoid. Fast exact rectangular test cases need whole
footprint Width/Depth entry. Add a guarded rectangle-size form beside starters:
keep center/orientation, source edge heights/pitches and IDs; change source XY
corners as one native commit and let native CAD rebuild faces. No independent
roof solver. Disable after dormers/folds and for unsupported outlines. Preserve
unmodified-axis precision despite rounded display; test no-op, Undo/Redo and
saved recovery. This is required manual authoring convenience, not a rewrite.
Gable/Shed reports above precede this planned UI change; do not call them final-
source reports after editing product files without checking provenance.

## Whole-rectangle dimensions implemented; final guards active

New Footprint size form under Roof starter: Width/Depth (0.1–1000 m), Resize
rectangle. Computes a rectangle XY transform in the existing edge basis, keeps
center/orientation/source node and edge IDs/pitches/heights, commits once; native
CAD rebuilds faces. It does not reconstruct a roof independently. Same eligibility
as starters: closed valid rectangle, equal edge heights, no dormers/folds. Keeps
untouched-axis full precision despite rounded millimeter display. No-op Apply
adds no history. Native single-edge Length remains unchanged.

Rotated gable test passed 93809 (37° fixture rotation uses native source setters;
not a rotation-handle UI claim). Flat test passed 31462. Each covers fractional
width then depth, fixed center and axes, source IDs/pitch/height, rectangle and
native validity, two atomic Undo/Redo edits, unchanged-axis/no-op precision,
invalid size, idle draft and saved reopen. Detailed guard is running in session 28950.
Still required: L guard, visual UI check, one practical starter-details regression
on final product sources, final hash check and resume instructions. Product/test
files must remain frozen during tests. README/How to model updated.


## Rectangle footprint sizing completed

Final product/test sources pass:
- rotated Gable 93809: verified-original-ui-startup-rectangle-size-rotated.json
- flat rectangle 31462: verified-original-ui-flat-rectangle-size.json
- detailed guard 28950: verified-original-ui-dormer-and-fold-rectangle-size.json
- L guard 23355: verified-original-ui-concave-rectangle-size.json
- composed Gable/details regression 2283: verified-original-ui-manual-authoring-gable.json

All five reports match current source hashes and have empty native/page errors,
external attempts, CSP blocks and unknown metadata. Resizes preserve center,
orientation, node/edge IDs, source pitches/heights and validity. Tests retain
fractional 31.123456 × 17.654321 m through single-axis edits, Undo/Redo, draft
refresh and saved reopen. Unchanged rounded fields never quantize the untouched
axis or add history. Invalid dimensions rejected; L/detailed inputs disable and
full geometry stays unchanged. The 37° fixture is created via native source
setters, not a claimed rotation-handle UI workflow. Flat remains one flat face;
Gable remains two. Dimension display rounds to 0.001 m, geometry tolerance 1e-7 m.

Visual run 44203 simultaneously entered Width=24, Depth=14, produced exactly those
source dimensions and valid/constructed Gable, then used new 3D Fit. Capture:
runtime/rectangle-size-controls.png. Actual new host UI/transform code, not just
verification of an already available native dimension control. Native CAD still
constructs roof faces. Size is a planar rectangle layout, not a roof solver.
README/How to model updated. Older generated Gable file retained in private
runtime/manual-example-history/ before final regeneration. No user tab touched.

Completed checklist for this pass:
- [x] Gable + dormer/fold save/export/import composition.
- [x] Distinct Shed single-face composition (33568, before sizing UI addition).
- [x] Whole-footprint dimensions, including rotated/flat support and precision.
- [x] Unsupported-outline/detail guards and native atomic recovery.
- [x] Final Gable authoring regression, source hashes and visual inspection.

No active tests remain. Server still 5191, session 67308/PID 69403. Native CAD/WASM
and retained frontend artifacts unchanged; no production edits, paid/remote calls,
auth bypass, deployment or commits. Save user work before refreshing for new UI.

Next required work: cached-background integration boundary for manual tracing.
Read integration-contract.md first. Current builder still has no imagery/address
adapter; permanent manual library/export is not expiry-aware. First inspect own
data-provider/native imagery entrypoints and available local cache manifests
read-only. Establish a concrete source-free adapter plan and input-manifest
validation/calibration using a self-generated test grid. Do not ingest real
Google/other external cached data until exact original expiry, permitted storage,
content hashes, XY transform/units and elevation datum are established AND
expiry enforcement covers image caches, drafts, named saves, imports and exports.
Unknown expiry is not permission to retain a derivative; do not infer policy or
extend it from file mtime. Keep permanent manual synthetic cases separate. No
new paid/API acquisition or Aurora requests. No automatic roof reconstruction or
production evaluator rewrite. Native source artifacts remain analysis evidence;
new adapters/validation must be own code. If necessary cache metadata is absent,
continue source-free contract/calibration work, then ask only for required data.

## Cached-background boundary groundwork completed

Own source-free implementation: input-manifest.mjs and checks helper. 31 checks
pass; hash-frozen report at runtime/input-contract/checks.json. Validates version,
explicit projected-meter/pixel-center declarations, invertible affine matrices,
non-collinear pixel/editor and editor/projected controls, aligned RGB/DSM/mask
grids, nodata conventions, any used DSM datum/offset controls, current/original
SHA relationships, explicit source operation permissions and exact original dates.
External sources require explicit expiry; synthetic provider must be generated-
locally. Effective expiry is earliest asset expiry; caller-supplied root expiry
cannot extend it. Submillisecond source strings retained, effective milliseconds
floor conservatively. Denied operations/expired or unknown-lifetime external
inputs reject. Async verification rechecks the clock after hashing.

Generated fixture only: runtime/input-contract/grid.svg and manifest.json (64×48
pixels, 0.25 m/pixel, 16×12 m exterior extent, source-free). Test controls verify
half-pixel placement, inverse transforms, 90° rotation, unit/alignment errors,
calendar/timezone validity, microsecond expiry preservation, permissions,
elevation registration, corrupted/missing bytes and expiry during async hashing.
External tests are metadata mocks; no external image bytes were read. Module
never opens paths, fetches URLs, decodes/renders images or writes app storage.
Not wired into UI/server routes; current manual library/export remains unchanged.

Production inspection was code-only/read-only: scripts use database fields
source_fetched_at/expires_at and prepared aligned.transform. No DB connection,
pickle load, source image read or acquisition performed. Actual cache availability,
permitted use and lifetime remain unestablished. No provider policy was invented.
Concrete stages/limits are in background-input-plan.md. No real data activation
before end-to-end expiry-aware storage/import/export and coordinate validation.

Native imagery observation (90761 inventory; 56231 signatures) used fresh empty
local browser, zero external attempts/errors, no textures loaded. Candidate route:
collection.orthoImageResourceFromWorldfile(model, worldfile) →
createGroundTexture(model, resource) → loadTexture(wrapper) → setGroundTextures.
Actual worldfile object layout, source enum, activation and refresh ownership are
NOT established. Host still has useMapView=false and no imagery provider.
Private evidence: runtime/input-contract/native-imagery-{inventory,methods}.json.
Exact inert method excerpts + native SHA/UTF16 offsets in native-excerpt/.
REA parent ev_fb3097c1704c9de6b62d9f43affe07cbf34506becddefedcf03623cf00df5a5b;
summary ev_1b6ebc08fe56012c389434221eec05db27622641c16a819961f29b5d7ce2acaf.
Static semantic coverage unknown/partial: not a complete imagery trace or a
successful registration. Existing native loadTexture body checks decoded width/
height; decoder was not executed. No native bytes changed.

Next required work: prove synthetic-only grid underlay with native registration.
Inspect small bounded worldfile/source enum/texture activation evidence; call no
remote URL or map service. Use immutable locally generated Blob bytes and a fresh
browser. Verify exact corner/center placements, scale and rotation in native
2D/3D. Preserve current user tab and permanent manual cases. Do not expose real
file/address ingestion or claim imagery support yet. Do not reuse network map
fallbacks. Keep source lifecycle/rights/CRS/decoder/persistence gates in plan.
If that interface cannot be established, record exact failure and continue source-
free work; do not patch vendor code or invent mapping semantics.

No active tests/browser probes remain. Existing lab server stays 5191, session
67308/PID 69403. No product/UI/production changes this pass; only own contract,
tests, synthetic fixture and docs/evidence. No paid/remote/account calls, auth
bypass, deployment, commits, source expiry extension or vendor publication.


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


## GitHub source snapshot published

User requested all lab work on its own GitHub branch. Source/docs committed as
6fa0d91 on codex/local-roof-editor-lab in chris12540/solar-design, from origin/main.
Publishing worktree: /Users/chris/.codex/worktrees/local-roof-editor-lab/solar-designer .
Original running lab/runtime remains here; production accuracy branch untouched.
Runtime/vendor bundles, source imagery/cases/screenshots and credentials not uploaded.
Public snapshot omits personal address/IP from notes; acquisition target reads local
ROOF_LAB_ADDRESS/ROOF_LAB_PARCEL_ID config there. Original live lab source untouched.
46 files committed; Python/JS syntax and 31 source-free manifest checks pass.
Do not reacquire data or run the server from a dependency-free publishing checkout.
Use explicit original lab directory for ongoing running-editor work. No PR created.


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


Height-fit capability investigation completed; see height-fitting-findings.md.
Confirmed captured client BuildingFitLidar + roof/plane Fit to LiDAR controls; own
adapter disables them. Google DSM can support analogous workflow after registration
and fitting adapter. No implementation/data acquisition performed; Show LiDAR display
path and direct native DSM compatibility remain unverified. REA evidence/provenance
recorded; private excerpts remain ignored. User asked feasibility, not data acquisition.


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
