# Next integration boundary

October 29, 2026. This is a contract/resume note, not an implemented imagery or
benchmark adapter. Production repository was inspected read-only.

## Reference output

The current benchmark entry point in
`/Users/chris/code/solar-designer/experiments/roof-vision/aurora-benchmark/benchmark.py`
expects a DXF reference and a saved reconstruction result. Its DXF path nodes
`Buildings` lines into planar faces, then performs rotation/translation outline
registration. Orientation references are supplied separately. Native lab JSON
is not accepted by that path and must not be presented as a reproduced benchmark.

Required local reference package before an adapter is integrated:

- Schema version, anonymous case ID, timestamps, manual/synthetic provenance,
  authoring engine identity/hash, and exporter version/hash.
- Native design JSON for reopening, with a checksum.
- Explicit local coordinates in meters, axis directions, horizontal origin,
  vertical datum and whether georeferencing is established. Current lab cases
  use an artificial origin and must be marked unregistered/synthetic.
- Roof/dormer/fold source IDs, perimeter and face polygons in XYZ, walls, topology
  and hole boundaries. Include derived pitch/azimuth conventions and tolerances.
- Explicit handling of overlapping roofs, dormers, hidden lines, vertical faces,
  courtyards and disjoint structures. Never silently flatten these into a
  supposedly complete planar reference.
- Data lineage and original expiry for any externally sourced inputs/derivatives.
  Manual synthetic examples have no external-imagery source; do not invent one.

An independent adapter may produce DXF or a new benchmark reference interface.
Either requires geometric comparison against known synthetic examples before
real-house scoring. Do not change the frozen production evaluator in this lab
without a separate implementation decision. Aurora-derived geometry is a
comparison reference, not surveyed ground truth.

## Cached imagery/geodata

Before connecting an address or image, define and validate a local input manifest:

- Anonymous source/case ID, provider, acquisition time, exact original expiry,
  content hashes and permitted storage/derivative behavior.
- Horizontal CRS, transform from raster pixels to projected meters, origin and
  axis orientation, image extent/resolution, plus elevation units/datum.
- RGB, DSM and mask nodata conventions, raster alignment, dates and resolution.
- Adapter output transform into editor coordinates; verify known distances,
  rotation, image/geometry overlays and height offsets independently.
- Source expiry enforcement in every cache, local save, export and imported
  example. Unknown expiry for source-derived data is not permission to retain it.

Current permanent browser example library is intended for manual synthetic data.
Do not insert Google-derived cases into it until expiry-aware storage/import and
export are implemented. No new paid calls, Aurora API requests or remote design
edits are authorized by this contract. Addresses alone do not authorize acquisition.


## Implemented lab package (partial reference contract)

Export test case downloads roof-lab-case/v1. It contains exact nativeDesignJson
and its UTF-8 SHA-256, anonymous case ID, creation time, startup-pinned engine
artifact identities and an algorithm fingerprint of the running exporter functions
plus schema/version. The fingerprint is not a whole-file checksum or signature.

The geometry view resolves native building face/wall index rings to local XYZ,
preserves known hole rings, and marks unknown hole metadata explicitly. Invalid
indices, nonfinite coordinates and unsupported hole encodings are rejected.
Raw native JSON preserves remaining object/source/topology data; trees, panels
and obstructions are not converted by the geometry view. Visibility/overlap are
native-computed and not independently verified.

Packages explicitly remain unregistered, unvalidated manual comparisons with
benchmarkCompatible=false, sourceLineageComplete=false and georeferenced=false.
No CRS, real horizontal origin or verified vertical datum is invented. No external
inputs are registered by this lab; that is not proof of independent source lineage.
Source-derived imagery cases still require expiry-aware integration.

Native payload restoration is verified by replaying the exact exported string
through the existing local loader, including roof, mixed dormer/fold, L-host and
standalone-face cases. Open test case now provides the validated manual-package import control described below.
DXF/reference benchmark integration remains unimplemented. Checksums detect byte
changes; they do not authenticate an author or establish roof accuracy.


## Manual package-open policy

Open test case is limited to v1 unregistered manual packages with matching current
engine identities, native format 3, native checksum and geometry consistency.
The file is read locally (20 MB limit); validation precedes example changes.
Existing nonempty work is saved first. Imported cases receive fresh local IDs,
retaining a one-hop source case ID/checksum/exporter identity reference. The saved
browser record and subsequent re-export retain that reference; it does not make
sourceLineageComplete true or authenticate the source author.

Imported saved cases reopen on ordinary home-page refresh. New example still
starts empty; saved imported examples can be reopened through the local library.
External/imagery-derived and world-registered packages remain unsupported under
this policy. Metadata checks are not proof of physical source lineage; only use
manual lab packages here until expiry-aware source integration is implemented.


Five opening workflows pass: basic, mixed dormer/fold, L host, standalone face and
preserved prototype. Each rejects checksum, engine, geometry, source-policy,
schema and native-format errors without changing current model/library. Edited
current work is preserved, saved provenance survives refresh/re-export, and New
example/Reopen saved retains the imported case. A fresh local case ID is a fork
identifier, not an independent house sample or proof of source lineage.

## Source-free input contract groundwork

`input-manifest.mjs` and `background-input-plan.md` now define/test the next input
boundary. They are not integrated with the editor, image decoder, source storage,
address lookup or v1 manual package loader. Real imagery remains unsupported.
Validator checks declared original expiry/permissions, byte hashes and numerical
pixel/editor/projected/elevation controls; these do not authenticate rights,
lineage, true CRS units, trusted time or physical accuracy. Source registration
and every persistence/export path remain required before external cache use.
