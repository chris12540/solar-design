import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './filters.css'
import { runSolarReviewQueue, type BatchResult } from './solarReviewQueue'

type Selection = { mode: 'areas'; area_ids: string[]; excluded_ids: string[]; sample_ids: string[]; intent: 'single' | 'sample' | 'all' }
type FilterValues = {
  owner_occupied: boolean
  recent_sale_days: number
  exclude_condo_multifamily: boolean
  exclude_existing_solar: boolean
  exclude_do_not_mail: boolean
  year_min: number | null
  year_max: number | null
  min_home_value: number | null
  min_roof_area_sqft: number | null
  min_lot_area_sqft: number | null
  min_system_kw: number | null
}
type Home = { parcel_id: string; apn?: string | null; address?: string | null; status: 'excluded' | 'needs_review' | 'not_checked' | 'passes_available_checks'; reason_codes: string[]; unknown_checks: string[]; pending_checks?: string[]; reasons: { code: string; message: string; source: string | null }[]; facts: Record<string, unknown> }
type Report = {
  review_scope?: { area_ids?: string[]; parcel_ids?: string[]; selection?: Selection }; solar_configured?: boolean; solar_expires_at?: string | null; policy_version: string; as_of_date: string; as_of_timezone: string; filters: FilterValues
  input_count: number; excluded_count: number; needs_review_count: number; not_checked_count?: number; passes_available_checks_count: number; remaining_count: number
  selection_fingerprint: string; source_warnings: string[]; coverage: { code: string; label: string; status: 'available' | 'partial' | 'not_checked' | 'unavailable'; source: string; warnings?: string[] }[]
  steps: { code: string; label: string; matched_count: number; newly_excluded_count: number; remaining_count: number }[]
  homes: Home[]; eligible_sample_ids: string[]; needs_review_sample_ids: string[]; excluded_sample_ids: string[]
  preexisting_excluded_ids?: string[]; preexisting_excluded_count?: number; fact_snapshot?: { source_files?: unknown[]; source_snapshot_date?: string | null; transform_version?: string | null }
}
type SavedMeta = { id: string; created_at: string; policy_version: string | null; as_of_date: string | null; selection_fingerprint: string | null; input_count: number | null; excluded_count: number | null; needs_review_count: number | null; passes_available_checks_count: number | null }
type Props = { open: boolean; onClose: () => void; selection: Selection; savedRunId: string | null }
const DEFAULTS: FilterValues = { owner_occupied: false, recent_sale_days: 0, exclude_condo_multifamily: true, exclude_existing_solar: true, exclude_do_not_mail: false, year_min: null, year_max: null, min_home_value: null, min_roof_area_sqft: null, min_lot_area_sqft: null, min_system_kw: null }
const CHECK_LABELS: Record<string, string> = { owner_occupied: 'Owner occupancy', recent_sale: 'Recent sale', construction_year: 'Construction year', min_home_value: 'Assessor home value', home_value_below_minimum: 'Assessor home value', condo_multifamily: 'Detached home classification', existing_solar: 'Existing solar', do_not_mail: 'Do not mail', min_roof_area_sqft: 'Roof area', min_lot_area_sqft: 'Lot area', min_system_kw: 'Solar potential' }
const REASON_LABELS: Record<string, string> = { not_owner_occupied: 'Likely not owner occupied', recent_sale: 'Recent sale', construction_year: 'Outside construction year range', home_value_below_minimum: 'Below assessor value minimum', roof_area_below_minimum: 'Below roof area minimum', lot_area_below_minimum: 'Below lot area minimum', system_size_below_minimum: 'Below solar potential minimum', not_detached: 'Not a detached home', existing_solar: 'Existing solar detected', condo_multifamily: 'Not a detached home' }
function messageOf(error: unknown) {
  const status = typeof error === 'object' && error && 'status' in error ? Number((error as { status: number }).status) : 0
  if (status === 401) return 'Your staff session expired. Sign in again to continue.'
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}
async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, credentials: 'same-origin', headers: { ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers } })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { const body = await response.json() as { detail?: unknown }; if (typeof body.detail === 'string') message = body.detail; else if (Array.isArray(body.detail)) message = body.detail.map((x) => typeof x === 'object' && x && 'msg' in x ? String((x as { msg: unknown }).msg) : String(x)).join('. ') } catch { /* response may not include JSON */ }
    throw Object.assign(new Error(message), { status: response.status })
  }
  return response.json() as Promise<T>
}
function identity() { return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}` }
const pretty = (value: string) => value ? value.replace(/_/g, ' ') : value
function sourceFileLabel(file: unknown) {
  if (typeof file === 'string') return file
  if (file && typeof file === 'object') {
    const item = file as Record<string, unknown>
    for (const key of ['name', 'filename', 'file_name', 'path']) if (typeof item[key] === 'string') return item[key] as string
  }
  return ''
}

type View = 'overview' | 'filters' | 'excluded' | 'needs_review' | 'passes_available_checks' | 'all'
const viewLabels: Record<View, string> = { overview: 'Home review', filters: 'Choose home filters', excluded: 'Excluded homes', needs_review: 'Homes needing review', passes_available_checks: 'Homes that passed checks', all: 'All homes' }

export default function FiltersSheet({ open, onClose, selection, savedRunId }: Props) {
  const [filters, setFilters] = useState<FilterValues>(DEFAULTS)
  const [draftFilters, setDraftFilters] = useState<FilterValues>(DEFAULTS)
  const [view, setView] = useState<View>('overview')
  const [optionalOpen, setOptionalOpen] = useState(false)
  const [report, setReport] = useState<Report | null>(null)
  const [preview, setPreview] = useState<Report | null>(null)
  const [previewContext, setPreviewContext] = useState<string | null>(null)
  const [metadata, setMetadata] = useState<SavedMeta[]>([])
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [readonly, setReadonly] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [enriching, setEnriching] = useState(false)
  const [pauseRequested, setPauseRequested] = useState(false)
  const pauseRef = useRef(false)
  const [sourceRefresh, setSourceRefresh] = useState(0)
  const [sourceNotice, setSourceNotice] = useState('')
  const [sourceError, setSourceError] = useState('')
  const [checkedThisRun, setCheckedThisRun] = useState(0)
  const enrichController = useRef<AbortController | null>(null)
  const enrichGeneration = useRef(0)
  const [error, setError] = useState('')
  const [showCount, setShowCount] = useState(30)
  const [details, setDetails] = useState<string | null>(null)
  const generation = useRef(0)
  const metadataGeneration = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const dialog = useRef<HTMLElement | null>(null)
  const runIdRef = useRef(savedRunId)
  runIdRef.current = savedRunId
  const retryKeys = useRef(new Map<string, string>())
  const selectionKey = useMemo(() => JSON.stringify(selection), [selection])

  const invalidate = useCallback(() => { generation.current += 1; controller.current?.abort(); controller.current = null; setPreview(null); setPreviewContext(null); setBusy(false); setSaving(false) }, [])
  const loadMetadata = useCallback(async (signal?: AbortSignal, expectedGeneration = metadataGeneration.current, expectedRunId = savedRunId) => {
    if (!savedRunId) { setMetadata([]); return }
    try { const result = await api<{ reports: SavedMeta[] }>(`/runs/${encodeURIComponent(savedRunId)}/eligibility`, { signal }); if (!signal?.aborted && metadataGeneration.current === expectedGeneration && runIdRef.current === expectedRunId) setMetadata(result.reports ?? []) }
    catch (e) { if (!signal?.aborted && metadataGeneration.current === expectedGeneration && runIdRef.current === expectedRunId) setError(messageOf(e)) }
  }, [savedRunId])

  useEffect(() => {
    metadataGeneration.current += 1; setMetadata([])
    enrichGeneration.current += 1; enrichController.current?.abort(); pauseRef.current = true
    setEnriching(false); setPauseRequested(false); setSourceNotice(''); setSourceError(''); setView('overview'); setCheckedThisRun(0)
    if (!open) { invalidate(); return }
    invalidate(); setError(''); setReport(null); setSelectedReportId(null); setReadonly(false); setShowCount(30); setDetails(null)
    const abort = new AbortController()
    void loadMetadata(abort.signal, metadataGeneration.current, savedRunId)
    return () => { abort.abort(); enrichGeneration.current += 1; enrichController.current?.abort(); pauseRef.current = true; metadataGeneration.current += 1; invalidate() }
  }, [open, savedRunId, selectionKey, invalidate, loadMetadata])

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const frame = requestAnimationFrame(() => dialog.current?.querySelector<HTMLButtonElement>('.filters-close')?.focus())
    return () => { cancelAnimationFrame(frame); previous?.focus() }
  }, [open])

  useEffect(() => {
    if (!open || readonly) return
    invalidate()
    const current = generation.current
    const abort = new AbortController(); controller.current = abort
    setBusy(true); setError('')
    const timer = window.setTimeout(() => {
      void api<Report>('/eligibility/preview', { method: 'POST', body: JSON.stringify({ selection: JSON.parse(selectionKey) as Selection, filters }), signal: abort.signal })
        .then((result) => { if (generation.current === current && !abort.signal.aborted) { setPreview(result); setPreviewContext(`${savedRunId ?? ''}:${selectionKey}`); setBusy(false) } })
        .catch((e) => { if (generation.current === current && !abort.signal.aborted) { setBusy(false); setPreview(null); setError(messageOf(e)) } })
    }, 200)
    return () => { window.clearTimeout(timer); abort.abort() }
  }, [open, readonly, selectionKey, savedRunId, filters, sourceRefresh, invalidate])

  const close = () => { invalidate(); enrichGeneration.current += 1; enrichController.current?.abort(); pauseRef.current = true; setEnriching(false); onClose() }
  const numberValue = (value: string, integer = false): number | null => { if (!value.trim()) return null; const n = Number(value); return Number.isFinite(n) && n >= 0 ? (integer ? Math.trunc(n) : n) : null }
  const openView = (next: View) => { setView(next); setDetails(null); setShowCount(30) }
  const changeFilters = (limits = false) => { setDraftFilters(filters); setOptionalOpen(limits); openView('filters') }
  const editFilters = () => { invalidate(); setReadonly(false); setReport(null); setSelectedReportId(null); setFilters({ ...(report?.filters ?? filters), owner_occupied: false, recent_sale_days: 0, exclude_do_not_mail: false }); setError(''); setSourceError(''); openView('overview') }
  const applyFilters = () => { invalidate(); setFilters({ ...draftFilters }); setReport(null); setSelectedReportId(null); setSourceNotice(''); setSourceError(''); openView('overview') }
  const updateDraft = <K extends keyof FilterValues>(key: K, value: FilterValues[K]) => setDraftFilters(current => ({ ...current, [key]: value }))
  const openSaved = async (id: string) => {
    if (enriching) return
    invalidate(); const current = generation.current; const abort = new AbortController(); controller.current = abort; setBusy(true); setError('')
    try { const result = await api<{ id: string; report: Report }>(`/eligibility/${encodeURIComponent(id)}`, { signal: abort.signal }); if (generation.current === current && !abort.signal.aborted) { setReport(result.report); setFilters(result.report.filters); setSelectedReportId(id); setReadonly(true); setPreview(null); setBusy(false); openView('overview'); setSourceNotice(''); setSourceError('') } }
    catch (e) { if (generation.current === current && !abort.signal.aborted) { setBusy(false); setError(messageOf(e)) } }
  }
  const save = async () => {
    if (!savedRunId || !preview || previewContext !== `${savedRunId}:${selectionKey}` || busy || enriching || !preview.selection_fingerprint || saving) return
    const body = { filters: preview.filters, selection: JSON.parse(selectionKey) as Selection }
    const retrySignature = `${savedRunId}:${JSON.stringify(body)}`
    const key = retryKeys.current.get(retrySignature) ?? identity()
    retryKeys.current.set(retrySignature, key)
    const current = generation.current
    setSaving(true); setError('')
    try {
      const result = await api<{ id: string; report: Report }>('/runs/' + encodeURIComponent(savedRunId) + '/eligibility', { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(body) })
      retryKeys.current.delete(retrySignature)
      if (generation.current === current && runIdRef.current === savedRunId) { setReport(result.report); setSelectedReportId(result.id); setReadonly(true); setPreview(null); setSourceNotice('Review saved. Map selection unchanged.'); openView('overview'); await loadMetadata(undefined, metadataGeneration.current, savedRunId) }
    } catch (e) { if (generation.current === current && runIdRef.current === savedRunId) setError(messageOf(e)) }
    finally { if (generation.current === current) setSaving(false) }
  }

  const checkSolarData = async () => {
    if (enriching || readonly || saving || busy || !preview) return
    const current = ++enrichGeneration.current
    const abort = new AbortController(); enrichController.current = abort; pauseRef.current = false
    generation.current += 1; controller.current?.abort(); setBusy(false)
    setEnriching(true); setPauseRequested(false); setCheckedThisRun(0); setError(''); setSourceNotice(''); setSourceError('')
    const active = () => current === enrichGeneration.current && !abort.signal.aborted
    try {
      const result = await runSolarReviewQueue({
        checkBatch: () => api<BatchResult>('/eligibility/enrich', { method: 'POST', body: JSON.stringify({ selection: JSON.parse(selectionKey) as Selection, filters }), signal: abort.signal }),
        refresh: () => api<Report>('/eligibility/preview', { method: 'POST', body: JSON.stringify({ selection: JSON.parse(selectionKey) as Selection, filters }), signal: abort.signal }),
        shouldStop: () => !active() || pauseRef.current,
        onProgress: (fresh, checked) => { if (active()) { setPreview(fresh); setPreviewContext(`${savedRunId ?? ''}:${selectionKey}`); setCheckedThisRun(checked) } },
      })
      if (active()) setSourceNotice(result.paused ? 'Paused. Completed checks are kept.' : 'Checks complete. Review results before saving.')
    } catch (e) {
      if (active()) { setSourceError(messageOf(e)); setSourceRefresh(value => value + 1) }
    } finally { if (active()) { setEnriching(false); setPauseRequested(false) } }
  }

  if (!open) return null
  const shown = readonly ? report : preview
  const homes = shown?.homes ?? []
  const visibleHomes = homes.filter(home => view === 'all' || home.status === view).slice(0, showCount)
  const resultCount = homes.filter(home => view === 'all' || home.status === view).length
  const droppedSamples = shown?.excluded_sample_ids ?? []
  const manualIds = shown?.preexisting_excluded_ids ?? selection.excluded_ids ?? []
  const yearRangeInvalid = draftFilters.year_min !== null && draftFilters.year_max !== null && draftFilters.year_min > draftFilters.year_max
  const previewCurrent = !!preview && previewContext === `${savedRunId ?? ''}:${selectionKey}` && !busy && !enriching && !readonly
  const solarEnabled = filters.exclude_existing_solar || filters.min_roof_area_sqft !== null || filters.min_system_kw !== null
  const solarPending = solarEnabled ? homes.filter(home => home.status !== 'excluded' && (!home.facts.solar_outcome || home.facts.solar_outcome === 'not_checked')).length : 0
  const solarRetry = solarEnabled && homes.some(home => home.status !== 'excluded' && ['failed', 'unavailable', 'building_mismatch'].includes(String(home.facts.solar_outcome)))
  const limitsCount = ['year_min', 'year_max', 'min_home_value', 'min_roof_area_sqft', 'min_lot_area_sqft', 'min_system_kw'].filter(key => filters[key as keyof FilterValues] !== null).length
  const mainCheck = !readonly && (solarPending > 0 || !!sourceError)
  const canCheck = previewCurrent && !saving && shown?.solar_configured !== false && solarEnabled
  const stateLabel = (home: Home) => home.status === 'passes_available_checks' ? 'Passed selected checks' : home.status === 'not_checked' ? 'Not checked yet' : pretty(home.status)
  const solarLabel = (home: Home) => typeof home.facts.solar_detection_status === 'string' ? pretty(home.facts.solar_detection_status.replace('DETECTION_STATUS_', '').toLowerCase()) : home.facts.solar_outcome ? pretty(String(home.facts.solar_outcome)) : 'Not checked'
  const sourceAttribution = shown?.homes.some(home => typeof home.facts.solar_outcome === 'string' && home.facts.solar_outcome !== 'not_checked')

  return <div className="filters-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) close() }}>
    <section ref={dialog} className="filters-sheet" role="dialog" aria-modal="true" aria-labelledby="filters-title" onKeyDown={event => {
      if (event.key === 'Escape') { event.stopPropagation(); close() }
      if (event.key === 'Tab') {
        const items = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),summary,a[href]')].filter(el => el.getClientRects().length > 0)
        const first = items[0], last = items[items.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
    }}>
      <header className="filters-head"><div><span className="eyebrow">STEP 3 · HOME REVIEW</span><h2 id="filters-title">Review your homes</h2><p>{(shown?.review_scope?.area_ids ?? selection.area_ids).length} {(shown?.review_scope?.area_ids ?? selection.area_ids).length === 1 ? 'neighborhood' : 'neighborhoods'} · {shown?.input_count ?? '…'} homes{readonly ? ' · Saved review' : ''}</p></div><button className="filters-close" aria-label="Close home review" onClick={close}>×</button></header>
      <div className="filters-content">
        {error && <p className="filters-error" role="alert">{error}</p>}
        {busy && <p className="filters-loading" role="status">Updating review…</p>}
        {view === 'overview' && shown && <>
          <div className="review-hero" aria-live="polite"><span className="review-eyebrow">{enriching ? 'Solar check in progress' : solarPending ? 'Solar check' : 'Selected checks'}</span><h3>{enriching ? `Checking homes${checkedThisRun ? ` · ${checkedThisRun} checked` : '…'}` : solarPending ? `${solarPending} homes to check` : `${shown.passes_available_checks_count} homes passed checks`}</h3><p>{enriching ? 'Results update as checks finish.' : solarPending ? 'Check for existing panels before designing.' : 'Review exceptions before saving.'}</p></div>
          <div className="review-counts" aria-label="Review results"><button onClick={() => openView('excluded')}>{shown.excluded_count} excluded</button>{shown.needs_review_count > 0 && <button onClick={() => openView('needs_review')}>{shown.needs_review_count} needs review</button>}{solarPending > 0 && shown.passes_available_checks_count > 0 && <button onClick={() => openView('passes_available_checks')}>{shown.passes_available_checks_count} passed</button>}</div>
          {shown.needs_review_count > 0 && <div className="review-attention"><span>{shown.needs_review_count} {shown.needs_review_count === 1 ? 'home needs' : 'homes need'} attention</span><button onClick={() => openView('needs_review')}>Review homes</button></div>}
          {droppedSamples.length > 0 && <p className="review-sample-note">{droppedSamples.length} selected sample {droppedSamples.length === 1 ? 'home is' : 'homes are'} excluded. <button onClick={() => openView('excluded')}>View exclusions</button></p>}
          {!readonly && <><div className="review-policy"><span>{filters.exclude_condo_multifamily ? 'Detached homes only' : 'All property types'}</span><button disabled={enriching || saving} onClick={() => changeFilters()}>Change</button></div><div className="review-policy"><span>{filters.exclude_existing_solar ? 'Skip homes with solar' : 'Include homes with solar'}</span><button disabled={enriching || saving} onClick={() => changeFilters()}>Change</button></div><p className="review-muted">Rentals stay included and flagged on map.</p><button className="review-link" disabled={enriching || saving} onClick={() => changeFilters(true)}>{limitsCount ? `Edit optional limits · ${limitsCount} active` : 'Add optional limits'}</button></>}
          {sourceNotice && <p className="review-feedback" role="status">{sourceNotice}</p>}
          {sourceError && <p className="filters-error" role="alert">{sourceError}</p>}
          {shown.solar_configured === false && !readonly && solarEnabled && <p className="review-muted">Google Solar isn’t connected. Local checks still work.</p>}
          <details className="review-sources"><summary>Sources &amp; saved reviews</summary>
            <p>Detached status uses assessor codes, not a shared-wall survey. Uncertain classifications need review. Solar detection reflects its imagery capture date.</p>
            {sourceAttribution && <p>Source: Includes solar data from Google</p>}
            <p>{shown.input_count} homes reviewed · {manualIds.length} manually excluded · {(shown.review_scope?.selection?.sample_ids ?? selection.sample_ids).length} selected samples. <button className="review-link" onClick={() => openView('all')}>View all homes</button></p>
            <p>Checked {shown.as_of_date} ({shown.as_of_timezone}) · {shown.policy_version}{shown.solar_expires_at ? ` · Solar results expire ${new Date(shown.solar_expires_at).toLocaleDateString()}` : ''}</p>
            {readonly && <><p>Saved results stay unchanged. Create a new review to recalculate.</p><dl className="review-applied">{Object.entries(filters).filter(([,value]) => value !== null && value !== false && value !== 0).map(([key,value]) => <div key={key}><dt>{CHECK_LABELS[key] ?? pretty(key)}</dt><dd>{String(value)}</dd></div>)}</dl></>}
            <h3>Source coverage</h3>{shown.coverage.map(item => <details key={item.code}><summary>{item.label} · {pretty(item.status)}</summary><p>{item.source}</p>{item.warnings?.map(warning => <p key={warning}>{warning}</p>)}</details>)}
            {shown.source_warnings.map(warning => <p key={warning}>{warning.replace(/ for dataset [a-f0-9]{64}\./g, '.')}</p>)}
            <p>Sources: {shown.fact_snapshot?.source_files?.map(sourceFileLabel).filter(Boolean).join(', ') || 'No optional assessor files'}{shown.fact_snapshot?.source_snapshot_date ? ` · ${shown.fact_snapshot.source_snapshot_date}` : ''}</p>
            <h3>Per-filter removals</h3>{shown.steps.map(step => <p key={step.code}>{step.label}: {step.matched_count} matched · {step.newly_excluded_count} newly excluded</p>)}
            {metadata.length > 0 && <label className="review-saved">Saved reviews<select disabled={enriching || saving} value={selectedReportId ?? ''} onChange={event => event.target.value ? void openSaved(event.target.value) : editFilters()}><option value="">Current review</option>{metadata.map(item => <option key={item.id} value={item.id}>{item.as_of_date ?? 'Saved'} · {item.input_count ?? '—'} homes · {item.excluded_count ?? 0} excluded · {new Date(item.created_at).toLocaleString()}</option>)}</select></label>}
            {solarRetry && !readonly && <><button className="review-link" disabled={!canCheck} onClick={() => void checkSolarData()}>Retry unavailable solar checks</button><p>Temporary failures can retry after five minutes. Other cached results are reused.</p></>}
          </details>
          {sourceAttribution && <p className="review-attribution">Includes solar data from Google</p>}
        </>}
        {view === 'filters' && <>
          <div className="review-subhead"><h3>Choose home filters</h3><button className="review-link" onClick={() => openView('overview')}>Cancel</button></div>
          <label className="review-check"><input type="checkbox" checked={draftFilters.exclude_condo_multifamily} onChange={event => updateDraft('exclude_condo_multifamily', event.target.checked)} />Detached homes only</label>
          <label className="review-check"><input type="checkbox" checked={draftFilters.exclude_existing_solar} onChange={event => updateDraft('exclude_existing_solar', event.target.checked)} />Exclude existing solar</label>
          <details className="review-limits" open={optionalOpen} onToggle={event => setOptionalOpen(event.currentTarget.open)}><summary>Add optional limits</summary><div className="review-fields"><label>Built from<input type="number" min="1800" max="2027" value={draftFilters.year_min ?? ''} onChange={event => updateDraft('year_min', numberValue(event.target.value, true))} /></label><label>Built through<input type="number" min="1800" max="2027" value={draftFilters.year_max ?? ''} onChange={event => updateDraft('year_max', numberValue(event.target.value, true))} /></label><label className="review-wide">Assessor value from ($)<input type="number" min="0" max="100000000" step="1000" value={draftFilters.min_home_value ?? ''} onChange={event => updateDraft('min_home_value', numberValue(event.target.value))} /></label></div>
            {yearRangeInvalid && <p className="filters-error" role="alert">Start year must be no later than end year.</p>}
            <p className="review-muted">Assessor full cash value, not current market value.</p>
            <details><summary>Roof, lot &amp; solar potential</summary><div className="review-fields"><label>Roof area from (sq ft)<input type="number" min="0" step="100" value={draftFilters.min_roof_area_sqft ?? ''} onChange={event => updateDraft('min_roof_area_sqft', numberValue(event.target.value))} /></label><label>Lot area from (sq ft)<input type="number" min="0" step="100" value={draftFilters.min_lot_area_sqft ?? ''} onChange={event => updateDraft('min_lot_area_sqft', numberValue(event.target.value))} /></label><label>Potential from (kW)<input type="number" min="0" step="0.5" value={draftFilters.min_system_kw ?? ''} onChange={event => updateDraft('min_system_kw', numberValue(event.target.value))} /></label></div><p className="review-muted">Roof and potential limits need Google data. Potential is not a completed design or usage-sized system.</p></details>
          </details><p className="review-muted review-form-note">No recent-sale limit. Rental flag never excludes a home.</p>
        </>}
        {view !== 'overview' && view !== 'filters' && shown && <>
          <div className="review-subhead"><h3>{viewLabels[view]} · {resultCount}</h3><button className="review-link" onClick={() => openView('overview')}>Back</button></div>
          {!resultCount && <p className="review-muted">No homes in this group.</p>}
          {visibleHomes.map(home => <article className="review-home" key={home.parcel_id}><button className="review-home-toggle" onClick={() => setDetails(details === home.parcel_id ? null : home.parcel_id)} aria-expanded={details === home.parcel_id}><span><strong>{home.address || home.apn || home.parcel_id}</strong><small>{home.reasons[0] ? (REASON_LABELS[home.reasons[0].code] ?? pretty(home.reasons[0].code)) : stateLabel(home)}{home.facts.rental_status === true ? ' · Rental flagged' : ''}</small></span><span aria-hidden="true">{details === home.parcel_id ? '−' : '+'}</span></button>{details === home.parcel_id && <div className="review-home-detail"><p>APN {home.apn || home.parcel_id}</p>{home.reasons.map((reason,index) => <p key={`${reason.code}-${index}`}><strong>{REASON_LABELS[reason.code] ?? pretty(reason.code)}:</strong> {reason.message}</p>)}{home.unknown_checks.length > 0 && <p>Needs review: {home.unknown_checks.map(code => CHECK_LABELS[code] ?? pretty(code)).join(', ')}</p>}{!!home.pending_checks?.length && <p>Not checked: {home.pending_checks.map(code => CHECK_LABELS[code] ?? pretty(code)).join(', ')}</p>}<p>Rental: {home.facts.rental_status === true ? 'Flagged' : home.facts.rental_status === false ? 'Not flagged' : 'Unknown'}<br />Dwelling: {pretty(String(home.facts.dwelling_type ?? 'Unknown'))}<br />Solar: {solarLabel(home)}{home.facts.solar_capture_date ? ` · captured ${home.facts.solar_capture_date}` : ''}</p>{typeof home.facts.solar_source === 'string' && <p className="review-muted">Source: Includes solar data from Google</p>}</div>}</article>)}
          {resultCount > showCount && <button className="review-link" onClick={() => setShowCount(value => value + 30)}>Show {Math.min(30, resultCount - showCount)} more homes</button>}
          {sourceAttribution && <p className="review-attribution">Includes solar data from Google</p>}
        </>}
      </div>
      <footer className="filters-actions">
        {view === 'filters' ? <><span className="review-footer-note">Limits apply to this review</span><button className="primary" disabled={yearRangeInvalid} onClick={applyFilters}>Apply filters</button></> : view !== 'overview' ? <><span /><button className="primary" onClick={() => openView('overview')}>Back to review</button></> : enriching ? <><span className="review-footer-note">{pauseRequested ? 'Finishing current batch…' : 'Checks running · results kept as they finish'}</span><button className="outline-button" disabled={pauseRequested} onClick={() => { pauseRef.current = true; setPauseRequested(true) }}>Pause checks</button></> : readonly ? <><button className="review-link" disabled={busy} onClick={editFilters}>New review</button><button className="primary" onClick={close}>Done</button></> : <><span className="review-footer-note">{mainCheck ? 'Google solar check · API charges may apply' : !savedRunId ? 'Save neighborhood first to keep this review' : 'Save results separately from map selection'}</span><div className="review-footer-buttons">{mainCheck && <button className="review-link" disabled={!savedRunId || !previewCurrent || saving} onClick={() => void save()}>{saving ? 'Saving…' : 'Save review'}</button>}{mainCheck ? <button className="primary" disabled={!canCheck} onClick={() => void checkSolarData()}>{sourceError ? 'Retry checks' : `Check ${solarPending} homes`}</button> : <button className="primary" disabled={!savedRunId || !previewCurrent || saving} onClick={() => void save()}>{saving ? 'Saving…' : 'Save review'}</button>}</div></>}
      </footer>
    </section>
  </div>
}
