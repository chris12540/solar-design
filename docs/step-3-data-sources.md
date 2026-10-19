# Step 3 data sources and limits

Checked October 13, 2026.

- Local Secured Master: exact source headers are validated by existing importer. Occupancy estimate is already persisted; SaleDate, FCV and NumUnits are present in raw files. Sidecar fact import must bind to original dataset/file hashes/source rows.
- Nonempty SaleDate profile: 10,000 values parsed as MMDDYYYY, none as YYYYMMDD (valid years 1800–2100). Missing or malformed dates remain unknown. This sample validates parser choice, not full-source completeness or freshness.
- First 30,000 structurally valid rows: 16,062 blank SaleDate values; NumUnits blank in 29,986. Do not infer single-family from blank unit count. Property-use leading zeroes matter.
- [Maricopa assessor glossary](https://www.mcassessor.maricopa.gov/glossary/P/) says PUC describes predominant property use and refers to Arizona Department of Revenue's code manual. The public parcel GIS metadata exposes PUC as a field without a coded-value domain; it supplies no authoritative mapping.
- [Arizona DOR assessment library](https://azdor.gov/business/property-tax/property-tax-publications/assessment-procedures-library-alphabetical) lists the Property Use Code Manual. Direct library/PDF retrieval returned HTTP 403 in this environment. No guessed code mapping applied. [Manual URL](https://azdor.gov/sites/default/files/2023-03/PROPERTY_useCodeManual.pdf).
- No verified local existing-solar, do-not-mail, roof-area, lot-area or estimated-system-kW facts currently available. Missing values must remain unknown and coverage shown.

Assessor FCV is not a market valuation estimate. Owner occupancy is inferred from source rental flag and comparison fields, not verified by the app. Dataset snapshot date is unknown; import/fetch times are not substituted for source observation date.


## October 14: completed source adapters

Supersedes earlier unsupported-source statements for local classifications and optional measurements.

- Raw RentalInd now retained in transform version 2; Y/N becomes flag true/false, other values remain unknown. No mailing-address rental inference and no rental exclusion.
- Arizona DOR Property Use Code Manual pages 10–12 and 16 supplies precise use-code mapping. Graded single-family codes act as a detached-home proxy; shared walls are not independently surveyed. Explicit separate-wall/roof codes are detached. Condo/townhouse categories, multifamily, and common-area codes are excluded. Dominant-home/additional-dwelling codes remain review because ADU policy is undecided. Source: https://azdor.gov/sites/default/files/2023-03/PROPERTY_useCodeManual.pdf
- Lot area calculated geodesically from the county parcel geometry, in square feet. Missing geometry means unknown; Lot/Block/Tract are never used as area.
- Google Solar adapter requests DETECTED_ARRAYS. Returned building center must fall in intended parcel. Capture date retained separately from processing date. Whole-roof area converted to square feet; max panel count × panel watts / 1000 gives potential kW, not final design or usage sizing.
- Google project/key absent; live calls remain unverified. No synthetic Solar responses inserted into real data. See google-solar-setup.md.
- Google content expires after 30 days, including reports containing it. Other reports stay frozen. Expiry checked on report access/save and at startup/hourly cleanup. No Google-derived map overlays on the existing non-Google map.
