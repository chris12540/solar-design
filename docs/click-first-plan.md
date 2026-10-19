# Click-first neighborhood workspace

Status: implemented and verified October 13, 2026. Approved interactive concept: neighborhood-click-flow.html in this chat. No backend/API/schema redesign, design jobs, D1 changes, deployment, or enforcement of red blocking.

## Required behavior

- Only Neighborhoods and Draw area are top-level modes. Search and saved sets remain reachable through compact controls, not a permanent sidebar. Keep review/confirmation flow and all existing exclusions, sample intents, AHJ overrides, source warnings, saved runs.
- Click map neighborhood or search result: outline preview and geographically anchored popup with explicit Add. Clicking same preview or empty map, X, Escape, or changing tools cancels preview and invalidates pending requests. Never change selected membership before Add. Ambiguous hits require choosing a candidate.
- Click added neighborhood: anchored menu with details, select houses, redraw, remove. Selecting houses requires this menu, is scoped to included parcels in that area, and exits via Done. No global Homes tab. Parcel clicks outside scoped home mode select/open their neighborhood, not samples.
- Selected geometry uses highest neighborhood severity consistently. Persistent non-numbered geographic text label shows actionable highest-level notice. No info markers or issue-count badges. Red: coverage_incomplete. Orange: estimated_boundary, ahj_unresolved, ahj_provisional, ahj_mixed, recorded_scope. Blue only in details: construction-year heuristics, single_parcel_scope, other info. Unknown warning-severity codes conservatively orange. Pending/failed review must not present green ready state. Preserve readable words/shapes alongside color. All original notices accessible in details/review.
- Membership, severity, and running progress remain independent. Progress visual primitive supports none/whole area/sample houses, white transparent diagonal moving stripes; reduced motion static. No fake design states, start-job controls, timers, or run API in production. Default idle. Source scope/id explicit.
- Saved confirmed records remain immutable. Explicit Edit as draft before membership/sample/AHJ edits. New draft may clear deliberately. No implicit silent mutation of confirmed snapshot.
- Keep middle-ground scale: 14px supporting text, 15–16px controls; mobile usable and no horizontal overflow. Progress never hides severity/notice. Empty geometry notices remain accessible via set review.

## Agent ownership / integration contract

Interaction agent owns frontend/src/App.tsx and frontend/src/MapContext.tsx (if extraction useful). State/style agent owns frontend/src/mapPresentation.ts, frontend/src/DesignProgress.tsx, frontend/src/styles.css, frontend/src/mapPresentation.test.mjs or equivalent meaningful pure-policy tests. Do not edit other owner's files. Coordinate via parent if contract needs change.

Presentation API:
- export type Notice = {code:string;severity:'warning'|'info';message:string}
- export type AreaPresentation = {level:'problem'|'review'|'clear'|'pending';color:string;label:string;notice:Notice|null}
- export function areaPresentation(notices:Notice[], state:'ready'|'pending'|'failed'):AreaPresentation
- export function noticeColor(notice:Notice):string
- export type DesignProgressState = {scope:'none'} | {scope:'area';areaId:string} | {scope:'samples';areaId:string;parcelIds:string[]}
- export default DesignProgress component from DesignProgress.tsx: props {area:{id:string;geometry:GeoJSON.Geometry|null;parcels:{id:string;geometry:GeoJSON.Geometry|null}[]};progress:DesignProgressState}. Default idle (App explicitly supplies {scope:'none'} until real data available). Uses map pane/GeoJSON with pointer events off. No job creation.

App adds semantic classes to compact toolbar, map-context-popup (preview/menu), persistent area-status-label with level, scoped-home-tools, set summary drawer; style owner provide base selectors and coordinate additions. Existing classes remain available for retained search/review forms.

## Verification

Build TypeScript/Vite. Pure policy checks for severity ordering, pending/failed state, unknown codes, mixed info and actionable notices. Browser: cancel pending preview, preview/Add, reopen selected neighborhood menu, scoped samples, exclusion/remove correctness, draw/cancel, persistent warning labels, confirmation/edit-as-draft, search and saved sets, mobile, no design job controls. Independent review before completion.

## Later

Actual design queue, job progress feed, red-block/override policy, roof design engine, live D1 integration.

Verification: [Click-first checks](click-first-verification.md).
