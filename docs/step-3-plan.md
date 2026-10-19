# Step 3: Filter before designing

Status: local filter engine, live review UI, source-matched facts, and immutable reports implemented and verified October 13, 2026. Missing-source integrations remain pending. User offline; material unanswered questions go to docs/questions-for-morning.md. Work independently with conservative, explicit assumptions.

Source: Light design stories, Step 3 (read directly in authenticated artifact October 13):
3.1 automatic exclusions: non-owner-occupied, recent sales, condos/multifamily, existing solar, do-not-mail.
3.2 optional year built, minimum roof area, lot size, home value, minimum kW.
3.3 per-filter counts and every excluded home's reason codes.
3.4 cheap checks first, live counts, no paid design calls.
3.5 individual exclusion override is Next; defer pending user policy.

## Decisions

Implement deterministic, versioned local filtering and clear data coverage. Never treat unavailable evidence as false or invent roof area, existing solar, suppression clearance, home value, unit classification, lot area or kW. Unknown enabled checks produce needs_review; known reasons produce excluded; remaining homes are passes_available_checks, not certified eligible or mail-ready. No design execution or pricing/usage/mail integration.

Owner occupancy already stored as likely_owner_occupied/likely_not_owner_occupied/unknown; label source as heuristic, not verification. Exclude likely_not_owner_occupied under enabled default owner check; unknown stays needs_review. Record observation/source age and unknown source snapshot date. Recent sale window adjustable, initial 180 days explicitly provisional default, evaluated against server calendar date. Future/invalid dates unknown. Do not infer sale date from deed date. Home value means assessor FCV, not market estimate. Unknown imported numeric values (empty/invalid/negative) null. Zero sold price not proof of recent sale.

Existing raw Secured Master fields include SaleDate, FCV, NumUnits, PropertyType, PUC, ConstrYear. Extend via separate optional versioned fact import keyed to existing dataset, source hashes, source row identity. No owner/mailing fields stored or exposed. No main dataset reimport or mutation. Lot/Parcel_Block/Parcel_Tract are identifiers; TotalSqFt/LivingArea not roof or lot area. Do not repurpose them.

Condo/multifamily classification only from documented county/DOR PUC mapping or unambiguous explicitly sourced fact. NumUnits alone may describe ADUs/complexes and is not sufficient until mapping verified. Parent will supply source mapping if recoverable; otherwise this check remains visibly unsupported. Existing solar and do-not-mail source absent: return unknown. Do not add an unsourced bypass or import API just to make green counts.

## API contract

POST /api/eligibility/preview accepts {selection:<existing areas selection>, filters:{owner_occupied:boolean=true,recent_sale_days:integer=180 (0 disables),exclude_condo_multifamily:boolean=true,exclude_existing_solar:boolean=true,exclude_do_not_mail:boolean=true,year_min:integer|null,year_max:integer|null,min_home_value:number|null,min_roof_area_sqft:number|null,min_lot_area_sqft:number|null,min_system_kw:number|null}}. Strict validate booleans, finite/nonnegative numbers, sane bounds/reversedranges/unknownkeys; no NaN acceptance. Missing/default settings returned explicitly as normalized filters. Same bounded membership and ownership as Step 2; no GIS or paid network calls in eligibility evaluation.

Response:
{policy_version,as_of_date,filters,input_count,excluded_count,needs_review_count,passes_available_checks_count,remaining_count,selection_fingerprint,source_warnings:[],coverage:[{code,label,status:'available'|'partial'|'unavailable',source}],steps:[{code,label,matched_count,newly_excluded_count,remaining_count}],homes:[{parcel_id,apn,address,status:'excluded'|'needs_review'|'passes_available_checks',reason_codes:string[],unknown_checks:string[],reasons:[{code,message,source}],facts:<safe fields only>}],eligible_sample_ids:string[],excluded_sample_ids:string[],fact_snapshot:<source metadata/hash only>}

Counts are unique homes. Steps deterministic and cheap first; matched_count may overlap, newly_excluded_count must sum to excluded_count. Return all reasons even if another filter already excludes same home. remaining_count=input_count-excluded_count; separate held review count prevents treating remaining as ready. Samples intersect passing/needsreview remainder, never excluded. Fingerprint binds selection/exclusions/samples/intent + normalized filters + policy + sources/asof.

POST /api/runs/{rid}/eligibility body {filters}, Idempotency-Key required: create separate immutable eligibility report from creator-owned saved run.selection, without mutating confirmed neighborhood record. Same key+same request retry returns same report; changed body 409. Table stores owner,run_id,request_hash,report jsonb,created_at,idempotencykey uniqueperowner. GET /api/eligibility/{report_id} creator-only. GET /api/runs/{rid}/eligibility returns saved report metadata (newestfirst). Browser uses these only after run has been saved/confirmed; otherwise offers preview and save-neighborhood instruction.

## UI integration (after click UI stabilizes)

Step 3 Filters control opens focused sheet; no extra persistent dashboard. Enabled automatic rules, adjustable recent sales window, optional year/value constraints; roof/lot/kW unavailable controls explained and disabled until matching facts exist. Live debounced preview and counts. Dropped-home list reasons, held-home missing-checks, per-filter deduped removals and coverage. Existing hand-excluded homes remain separate from rule exclusions. Filter preview does not mutate neighborhood membership or samples. Save report attached to saved selection, reopen stored immutable result. Cancel/edit invalidates obsolete previews. No automatic mailing/designing, no single-home override in initial scope.

## Verification

Isolated backend DB tests: rule reasons, missingdata, no false clearance, overlap/newlycount consistency, dates/bounds, creator isolation/idempotency, snapshots unchanged after newfacts. Import fixture tests and sourcehash/atomicity. Real source import only after checks. Frontend production build and browser live filters/reasons/save/reopen, Step2 regressions, mobile. No paid/API design calls.

## Later

Single-home rule override; confirmed suppression source import; verified existing solar feed; roof/lot/kW enrichment; actual designs; design red-block policy; production hosting.

Verification: [Step 3 results](step-3-verification.md).
