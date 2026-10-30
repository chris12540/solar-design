# 3D fold placement: findings and local adapter

October 28, 2026. Scope: retained CAD client 1.1876.0 and one synthetic roof.

## Observed failure

Before the adapter, a visible roof point at approximately
`(-0.307716, -5.272196, 4.306659) m` produced native fold coordinates
`(-3.901974, -12.449691, 0) m` from the same cursor ray. Native fold `inBounds`
was false while the parent roof remained valid and constructed. Clicking removed
that preview; no fold was committed. Collision picking simultaneously reported
the expected elevated roof point.

Focused inert inspection found the placement base method resolves the mouse ray
on a ground plane; fold placement uses that XY point. This agrees with the
runtime discrepancy. Earlier occlusion guesses did not establish the cause.

REA parent evidence:
`ev_d4c58fd8133e403bdee06c8d2a8a56909d7214d9677555a75355961587bb4ec8`.
Summary evidence:
`ev_f7740e6660e290b81bd685465e1dc0406892fd6c00a0519f9fe61438d5af2838`.
REA parsed one 8,706,421-byte JavaScript file without parse errors; semantic
analysis exhausted its 1 GiB heap. Graph coverage is partial. REA did not execute
the client or establish this runtime behavior. Runtime observations come from
the isolated browser probe; focused source inspection supplements its trace.

Retained bundle SHA-256:
`065f6e39575ec8b5bc15ddac809aa7178285e0a90852ebe46a04c16249dcfedb`.

## Change

`fold-placement.js` installs a local interaction adapter on the fold mode instance.
For oblique rays it uses the frontmost opaque hit only when that hit belongs to a
face of the roof currently being edited. It ignores line/vertex handles and the
current preview point, preserving native snapping. This matters because the fold
preview can place an edge directly under the cursor during reconstruction.

Plan-view positioning still uses the original method. Native validity checks are
retained. A click without a valid host-face hit cannot commit the last valid
preview position. Retained vendor files are unchanged; local interaction behavior
is intentionally adapted at runtime. This uses private client interfaces and is
version-specific, not a supported Aurora SDK integration.

## Verification and limits

Read `runtime/verified-original-ui-fold-3d-<angle>.json` for passing angle checks.
They assert an elevated pointer, in-bounds preview and matching pointer/preview
XY, then commit one flat fold producing five faces. Native source properties and
face coordinates must survive save/reopen at 1e-9 m comparison precision.

`--demo --ui-fold-3d --outside-fold` checks moving from a valid roof preview to
empty canvas, clicking there, discarding the fold and restoring four faces.
`--demo --ui-fold-fields` checks the original 2D path and numeric pitch/slope edits.

These are synthetic interaction checks. Other roof shapes, multiple overlapping
buildings, explicit occluders, perspective modes and vertical/sloping fold tools
need independent coverage. Source bytes and runtime behavior are separate claims.


## October 29: vertical preview wall

Vertical-fold testing exposed a separate self-occlusion issue. The draft was
in bounds and the roof was valid, but the frontmost wall had `source.id` equal to
the current edited fold. The adapter treated that generated preview wall as an
occluder. The trace is retained in runtime/vertical-fold-before-fix.json.

The adapter now skips only walls whose source is the current edited fold; it
continues to respect committed walls. Direct 90° placement then passed. A
separate exterior-wall case verifies a committed wall is frontmost before
asserting pointer rejection and unchanged geometry. Earlier attempts aimed at
hidden cut-wall points; those were invalid occlusion fixtures, not evidence of
an adapter failure.

interaction-cases.cjs adds mixed details, 45°/90° folds, fold-boundary height
changes, undo/redo and reopen checks. Numeric comparison tolerance for these
broader cases is 1e-7 m; earlier simple probes retain their narrower tolerances.
Other buildings and complex roof topologies remain outside this proof.


## October 29: L-host preview removes its live host collider

An L-shaped-host vertical-fold test exposed another preview interaction. The
live hit list contained only the current preview wall and an edge; its previously
visible host-face collider was absent. Skipping the preview wall alone therefore
returned no surface. Trace: runtime/concave-vertical-before-fix.json.

At placement start, the adapter now copies committed roof-face vertex rings.
Only when no other solid hit remains and the current preview wall is present,
it intersects the current ray with those committed face planes and checks the
projected point against each ring. This uses independent plane/polygon math,
not a copied vendor reconstruction algorithm. Empty-space clicks still need a
valid ring hit; committed walls and other solid hits are never bypassed by this
fallback. Native snapping and validity checks remain in place.

Known hole-bearing faces are excluded. The fallback is validated only for the
manual single-ring synthetic hosts tested here. Unknown hole metadata, courtyards,
imported meshes and separate-building occluders are not established by this check;
validate them before integrating new input types. This change is version-specific.
