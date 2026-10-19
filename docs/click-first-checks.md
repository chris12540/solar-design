# Click-first acceptance checks

## Required

- [x] Search and map clicks preview only, anchored Add popup.
- [x] Same click, empty-map click, X, Escape, and tool switch dismiss. Pending response cannot resurrect canceled preview.
- [x] Ambiguous point results require explicit candidate choice; branch independently source-reviewed (no live overlap fixture).
- [x] Added geometry and permanent text label show highest severity; no numbered warnings or info-only map markers.
- [x] Review refresh/failure retains known notices; unknown review never claims ready.
- [x] Added-area click opens neighborhood menu; house selection reachable only there.
- [x] House clicks toggle once, restricted to included members of chosen area; Done exits.
- [x] Draw, cancel, redraw, remove, exclusions, sample intent, overlapping-area deduplication retain semantics.
- [x] Search, saved sets, set review, manual AHJ overrides, confirmation and reopen remain available.
- [x] Confirmed snapshots require explicit Edit as draft before edits.
- [x] Production progress defaults idle; no animation toggles/job creation; overlay primitive scoped and reduced-motion accessible.
- [x] TypeScript/Vite build and pure presentation policy tests pass.
- [x] Desktop and 390px viewport usable; no horizontal overflow; popup controls reachable.
- [x] Independent review findings resolved or material limitation documented.

No design execution, new data/API contract, live D1 connection or hosting deployment in scope.
