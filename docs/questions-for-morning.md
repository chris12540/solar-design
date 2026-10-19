# Questions for morning review

Updated October 13, 2026. Work continues using explicit assumptions below. No paid design, mailing, live D1 changes, or deployment.

## Answers received October 14, 2026

These decisions supersede the draft assumptions below. October 14 implementation follows these answers; Google project setup is still required before live source checks. Existing saved reports remain historical records.

1. **Recent sales:** no exclusion window needed. Remove recent-sale filtering from the default workflow.
2. **Rentals:** show a rental flag and distinct home styling; do not automatically exclude rentals. Use the existing raw `RentalInd` field with verified value meanings. Do not substitute mailing-address comparisons for a rental fact. Transform version 2 now retains this field.
3. **Existing solar:** use Google Solar API `detectedArrays`, requested with `additionalInsights=DETECTED_ARRAYS`. Arrays detected means existing-solar exclusion; no arrays detected means no arrays observed at capture date. Missing, unspecified, or unavailable detection remains unknown. Store/display `latestCaptureDate`; processing date is not capture date. Match the returned building to the intended home before using its results.
4. **Do-not-mail clarification:** this meant a company-maintained suppression list, not a federal registry. No company list was supplied. Remove the missing-list dependency from default eligibility; do not hold every home for this absent input. Mailing is outside the current step.
5. **Property type:** detached homes only. Require documented classification mapping; do not infer detached status from NumUnits or guessed PUC prefixes. Treatment of a detached primary home with an ADU remains unspecified.
6. **Warnings:** user considers AHJ discrepancies more significant than parcel issues. Revise severity policy before using red as a design blocker. Proposed: conflicting AHJ assignments/rules warrant prominent review; draft registry status, multiple legitimate jurisdictions, and parcel-boundary estimates do not automatically mean a severe error. No new blocking policy approved.
7. **Missing facts explained:** before a Google lookup, solar status is “Not checked yet,” not an exclusion. Proposed: retain homes for enrichment; after an unavailable/failed lookup, flag the affected home for review. Do not hold unrelated homes for an absent optional source. This operational policy is a recommendation, not a new user answer.

### Data responsibilities

- Local assessor data: rental flag, property classification, construction year, assessed full cash value.
- Parcel/geographic data: lot area and jurisdiction assignment.
- Google Solar: detected arrays and their capture date, roof information, solar potential. Potential capacity remains an estimate, not a completed design or household usage estimate.
- Reuse a building-insights lookup for detection and roof information where available. No paid requests authorized or made by this document update.

### Sources

- Google Solar API reference: https://developers.google.com/maps/documentation/solar/reference/rest/v1/buildingInsights/findClosest
- FTC mailing preference guidance: https://consumer.ftc.gov/articles/how-stop-junk-mail

## Original questions and assumptions (historical)


1. **Recent sales:** how long should a home be excluded after sale? Initial configurable draft: 180 days. Raw assessor snapshot date remains unknown, so sale coverage cannot be called current.
2. **Owner occupancy:** okay to filter on existing likely-owner-occupied estimate (rental flag plus mailing/situs comparison), or require stronger evidence? UI must label this as an estimate.
3. **Existing solar:** which source should supply this flag? Current local dataset has no verified existing-solar field. Missing evidence stays needs-review.
4. **Do-not-mail:** where is your suppression list, and does it match APN, address, or both? No list connected yet; missing check stays needs-review. No addresses are sent anywhere.
5. **Condos vs townhomes / ADUs:** should townhomes with separate parcels and single-family homes with ADUs remain eligible? No NumUnits-based exclusion assumed. Code mapping needs a documented source before use.
6. **Red problems:** should they block all design work, only affected homes, or allow an explicit override? No design-run blocking policy implemented yet.
7. **Missing facts:** proposed default holds unknown enabled checks for review rather than treating missing solar/suppression data as clearance. Confirm this matches your intended workflow.

## Implemented/working assumptions

- Click-first map is the accepted direction; search/saved sets remain behind compact controls. Click-away cancels previews; house selection requires neighborhood menu.
- Selection membership, warnings, and design progress are separate. White progress overlay remains idle until actual design jobs exist.
- Step 3 is "Filter before designing" from Light design stories, not the roof design engine (Step 4).
- Initial optional thresholds only work from real available facts. Assessor FCV is labeled assessed full cash value, not current market value. Building/living square footage is not relabeled as roof/lot area.
- Single-home automatic-rule overrides are a Next story; defer until rule policy settled. Existing manual neighborhood exclusions remain available.
- Immutable filter reports save separately from confirmed neighborhood records.

## Data gaps / later inputs

- Verified roof area, lot area and estimated kW sources.
- Known date of the raw Secured Master snapshot.
- Pricing/time estimates for paid design runs (Step 2 story 2.5); no invented cost estimates.

Implementation results and remaining limitations will be appended before handoff.

## Source verification note

Official PUC manual could not be retrieved (HTTP 403); county GIS supplies codes without a description domain. Condo/multifamily rules remain unavailable rather than using guessed prefixes. See step-3-data-sources.md.

## Completed before handoff

- Click-first map implemented and browser checked. Preview can be unclicked or dismissed; Add explicit; highest-severity colors and permanent text labels; house selection via added-neighborhood menu; drawing preserved.
- Step 3 local filters and report saving/reopening implemented. Imported sale/value sidecar facts from all five matching local files; 1,759,895 records, two known quarantined rows skipped. Repeat import is a no-op.
- Real 109-home sample: default filters exclude 33 and hold 76 for missing checks; none falsely cleared. Optional year/value thresholds work. Saved neighborhood remains unchanged.
- 41 backend tests and seven UI policy tests pass; production build and desktop/mobile checks pass.
- App remains local at http://127.0.0.1:5173. No design jobs or cloud changes.

The source-dependent portions of Step 3 remain pending the inputs above. Details: step-3-verification.md and click-first-verification.md.


## October 14 handoff

Answered rules implemented and verified; see step-3-verification.md. User confirmed no Google project yet. Live Solar checks require setup in google-solar-setup.md; adapter tested without paid calls. Ambiguous/ADU classification remains review, not automatic exclusion. No additional policy questions block local filtering.


Google setup dependency resolved October 14: key configured, one live lookup and cache reuse verified. No additional source setup blocks existing Step 3 Solar adapter.
