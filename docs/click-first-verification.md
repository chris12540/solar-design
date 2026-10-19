# Click-first workspace verification

Verified October 13, 2026 against real local Scottsdale and Gila Bend selections.

- Full-window map; compact Neighborhoods/Draw tools, Search drawer and selected-set summary. Step 3 Filters is a separate focused sheet.
- Search/map neighborhood previews show geographically anchored explicit Add. Clicking preview again removes outline/prompt. Empty-map click cancels without launching replacement lookup. X/Escape cancel pending requests; old responses cannot restore canceled preview. Ambiguous chooser branch reviewed independently; no live overlap fixture asserted.
- Gila Bend preview leaves original109 unchanged. Add ->197, remove ->109, preserving original manual exclusion.
- Warning count icons removed. Geometry and parcel colors use highest severity: incomplete coverage red, jurisdiction/estimated boundary review orange; informational notes only inside details. Persistent geographic text labels use server interior anchors; no full warning paragraphs on map. Labels centered and mobile toolbar text unclipped.
- Added-neighborhood menu exposes all notices, scoped house selection, redraw and remove. Native parcel clicks toggle sample count 2 ->3 ->2 once each. House list stays collapsed by default. Tool switches clear house mode/context.
- Drawing through selected parcel geometry records three vertices; cancel preserves 109 included homes. Rapid draw/cancel no longer strands review in pending state; selection review uses independent request identity.
- Confirmed records disable edits until explicit Edit as draft; original snapshot remains intact. Source warnings stay visible during review refresh/failure. No-geometry selections retain drawer management.
- Progress primitive supports whole area or selected parcels, white transparent stripes, no pointer interception and static reduced-motion presentation. Production defaults idle; no fake job controls.
- Desktop/390x844 phone checked; viewport override reset.

Verification: TypeScript/Vite production build; seven presentation-policy tests; independent source review; browser checks. Step 3 backend has41 passing tests (see step-3-verification.md).
