import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './houseSheet.css'
import RoofInspection from './RoofInspection'

export type Selection = { mode: 'areas'; area_ids: string[]; excluded_ids: string[]; sample_ids: string[]; intent: 'single' | 'sample' | 'all' }
type HouseSummary = {
  parcel_id: string; address?: string | null; review_status?: string | null; last_reviewed_at?: string | null
  design_status?: string | null; needs_attention?: boolean; rental_status?: boolean | null
  eligibility_status?: string | null; reason_codes?: string[]
}
type Counts = { total?: number; reviewed?: number; not_reviewed?: number; needs_attention?: number; designed?: number }
type HouseDetail = {
  parcel_id?: string; dataset_id?: string; apn?: string | null; address?: string | null; city?: string | null; postal_code?: string | null
  property?: Record<string, unknown>; review?: Record<string, unknown>; design?: Record<string, unknown>; ahj?: Record<string, unknown>
  eligibility?: Record<string, unknown>; history?: { id?: string; kind?: string; created_at?: string | null; label?: string; report_id?: string | null }[]
  neighborhoods?: { area_id?: string; label?: string }[]; source_warnings?: string[]
}
export type HouseSheetProps = {
  open: boolean; selection: Selection; selectedAreaId: string | null; selectedParcelId: string | null; areaLabel?: string
  onClose: () => void; onInspectHouse: (id: string) => void; onBackToNeighborhood: () => void; onAddNeighborhoods: () => void
  onSelectSamples: () => void; onReview: () => void; onReviewHouse?: (id: string) => void
  onRemoveArea?: () => void; onRedrawArea?: () => void; locked?: boolean; refreshKey?: number; areaParcelIds?: string[]
}

function apiError(error: unknown) {
  const status = typeof error === 'object' && error && 'status' in error ? Number((error as { status: number }).status) : 0
  return status === 401 ? 'Your staff session expired. Sign in again to continue.' : error instanceof Error ? error.message : 'Could not load house records.'
}
async function post<T>(path: string, body: unknown, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api${path}`, { method: 'POST', credentials: 'same-origin', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { const payload = await response.json() as { detail?: unknown }; if (typeof payload.detail === 'string') message = payload.detail } catch { /* response may have no JSON body */ }
    throw Object.assign(new Error(message), { status: response.status })
  }
  return response.json() as Promise<T>
}
const human = (value: unknown) => typeof value === 'string' ? value.replace(/_/g, ' ') : ''
const date = (value: unknown, withTime = false) => {
  if (typeof value !== 'string' || !value) return 'Not recorded'
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value)
  const parsed = dateOnly ? new Date(`${value}T12:00:00`) : new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', ...(withTime && !dateOnly ? { timeStyle: 'short' as const } : {}) }).format(parsed)
}
const labelFor = (key: string) => key.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
const display = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return 'Not available'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return value.toLocaleString()
  if (Array.isArray(value)) return value.map(display).join(', ')
  if (typeof value === 'object') return 'Details available'
  return String(value)
}
function Rows({ values, omit = [] }: { values: Record<string, unknown>; omit?: string[] }) {
  const rows = Object.entries(values).filter(([key, value]) => !omit.includes(key) && value !== undefined && value !== null && value !== '')
  return <dl className="house-facts">{rows.length ? rows.map(([key, value]) => <div key={key}><dt>{labelFor(key)}</dt><dd>{display(value)}</dd></div>) : <div><dt>Details</dt><dd>Not available</dd></div>}</dl>
}

export default function HouseSheet(props: HouseSheetProps) {
  const { open, selection, selectedAreaId, selectedParcelId, areaLabel, onClose, onInspectHouse, onBackToNeighborhood, onAddNeighborhoods, onSelectSamples, onReview, onReviewHouse, onRemoveArea, onRedrawArea, locked = false, refreshKey = 0, areaParcelIds } = props
  const [summary, setSummary] = useState<{ key: string; homes: HouseSummary[]; counts: Counts } | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState('')
  const [detail, setDetail] = useState<{ key: string; value: HouseDetail } | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [showCount, setShowCount] = useState(10)
  const [retryKey, setRetryKey] = useState(0)
  const dialogRef = useRef<HTMLElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)
  const selectionKey = useMemo(() => JSON.stringify(selection), [selection])
  const summaryKey = `${selectionKey}|${selectedAreaId ?? ''}|${refreshKey}|${retryKey}`
  const detailKey = `${summaryKey}|${selectedParcelId ?? ''}`
  const currentSummary = summary?.key === summaryKey ? summary : null
  const currentDetail = detail?.key === detailKey ? detail.value : null

  useEffect(() => {
    if (!open) return
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    return () => { previousFocus.current?.focus() }
  }, [open])

  useEffect(() => { setShowCount(10) }, [selectionKey, selectedAreaId])

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setSummaryLoading(true); setSummaryError('')
    void post<{ homes?: HouseSummary[]; counts?: Counts }>('/houses/summary', { selection }, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setSummary({ key: summaryKey, homes: result.homes ?? [], counts: result.counts ?? {} }) })
      .catch((error: unknown) => { if (!controller.signal.aborted) setSummaryError(apiError(error)) })
      .finally(() => { if (!controller.signal.aborted) setSummaryLoading(false) })
    return () => controller.abort()
  }, [open, selectionKey, summaryKey])

  useEffect(() => {
    if (!open || !selectedParcelId) { setDetailLoading(false); setDetailError(''); return }
    const controller = new AbortController()
    setDetailLoading(true); setDetailError('')
    void post<HouseDetail>('/houses/inspect', { selection, parcel_id: selectedParcelId }, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setDetail({ key: detailKey, value: result }) })
      .catch((error: unknown) => { if (!controller.signal.aborted) setDetailError(apiError(error)) })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false) })
    return () => controller.abort()
  }, [open, selectionKey, selectedParcelId, detailKey])

  const close = useCallback(() => onClose(), [onClose])
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close(); return }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, close])

  if (!open) return null
  const homes = currentSummary?.homes ?? []
  const scopedHomes = selectedAreaId && areaParcelIds ? homes.filter((home) => areaParcelIds.includes(home.parcel_id)) : homes
  const orderedHomes = [...scopedHomes].sort((a, b) => Number(Boolean(b.needs_attention)) - Number(Boolean(a.needs_attention)) || (a.address ?? a.parcel_id).localeCompare(b.address ?? b.parcel_id))
  const visibleHomes = orderedHomes.slice(0, showCount)
  const counts = currentSummary?.counts ?? {}
  const reviewed = (status: unknown) => ['checked', 'reviewed', 'complete'].includes(String(status ?? '').toLowerCase())
  const shownCounts = selectedAreaId && areaParcelIds ? {
    total: scopedHomes.length,
    reviewed: scopedHomes.filter((home) => reviewed(home.review_status)).length,
    needs_attention: scopedHomes.filter((home) => home.needs_attention).length,
    designed: scopedHomes.filter((home) => Boolean(home.design_status) && home.design_status !== 'not_run').length,
  } : counts
  const isHouse = Boolean(selectedParcelId)
  const title = isHouse ? currentDetail?.address || currentDetail?.apn || selectedParcelId : areaLabel || 'Selected neighborhoods'
  const rowReview = (home: HouseSummary) => home.needs_attention ? 'Needs attention' : human(home.review_status) || 'Not reviewed'
  const review = currentDetail?.review ?? {}
  const design = currentDetail?.design ?? {}
  const property = currentDetail?.property ?? {}
  const eligibility = currentDetail?.eligibility ?? {}
  const reasonCodes = Array.isArray(eligibility.reason_codes) ? eligibility.reason_codes : []
  const reasons = Array.isArray(eligibility.reasons) ? eligibility.reasons as unknown[] : []
  const history = currentDetail?.history ?? []
  const ahjStatus = String(currentDetail?.ahj?.status ?? '').toLowerCase()
  const ahjMethod = String(currentDetail?.ahj?.method ?? '').toLowerCase()
  const ahjNeedsAttention = ['unresolved', 'ambiguous'].some((value) => ahjStatus.includes(value) || ahjMethod.includes(value))
  const criticalWarnings = (currentDetail?.source_warnings ?? []).filter((warning) => /unavailable|failed|error|incomplete/i.test(warning))

  return <div className="house-backdrop">
    <section ref={dialogRef} className="house-sheet" role="dialog" aria-modal="false" aria-labelledby="house-title" tabIndex={-1}>
      <header className="house-head">
        <div className="house-headline"><div><span className="house-kicker">{isHouse ? 'House record' : selectedAreaId ? 'Neighborhood' : 'House records'}</span><h2 id="house-title">{title}</h2></div><button className="house-close" type="button" aria-label="Close house records" onClick={close}>×</button></div>
        <div className="house-head-actions">
          {isHouse && <button type="button" className="house-text-button" onClick={onBackToNeighborhood}>← {areaLabel || 'Neighborhood'}</button>}
          {!isHouse && selectedAreaId && <span className="house-muted">{(shownCounts.total ?? scopedHomes.length).toLocaleString()} houses</span>}
        </div>
      </header>

      {isHouse ? <main className="house-content">
        {detailLoading && <p className="house-state" role="status">Loading house record…</p>}
        {detailError && <div className="house-error" role="alert"><span>{detailError}</span><button type="button" onClick={() => setRetryKey((value) => value + 1)}>Retry</button></div>}
        {!detailLoading && !detailError && currentDetail && <>
          <div className="house-address-meta">{[currentDetail.city, currentDetail.postal_code].filter(Boolean).join(' · ')}{currentDetail.apn ? <span>APN {currentDetail.apn}</span> : null}</div>
          <div className="house-status-row"><div><b>Review</b><small>{date(review.last_reviewed_at)}</small></div><span className={`house-badge ${reviewed(review.status) ? 'is-good' : review.status === 'needs_review' || review.status === 'refresh_needed' ? 'is-alert' : ''}`}>{human(review.status) || 'Not reviewed'}</span></div>
          <div className="house-status-row"><div><b>Design</b><small>Design engine unavailable</small></div><span className="house-badge">Not run</span></div>
          <p className="house-context">Eligibility: {human(eligibility.status) || 'Not assessed'}{reasonCodes.length ? ` · ${human(reasonCodes[0])}` : ''}</p>
          {ahjNeedsAttention && <p className="house-warning">Jurisdiction match needs review: {human(currentDetail.ahj?.status || currentDetail.ahj?.method)}</p>}
          {criticalWarnings.map((warning, index) => <p className="house-warning" key={`critical-${index}`}>{warning}</p>)}
          <div className="house-accordions">
            {selectedParcelId && <RoofInspection key={`${selectionKey}|${selectedParcelId}`} selection={selection} parcelId={selectedParcelId} />}
            <details><summary>Property facts</summary><Rows values={property} /></details>
            <details><summary>Review and solar details</summary><p className="house-muted">Solar data: Google Solar API</p><Rows values={review} omit={['status', 'last_reviewed_at']} />{(review.solar_capture_date != null || review.expires_at != null) && <p className="house-muted">Solar capture: {date(review.solar_capture_date)} · refresh after {date(review.expires_at)}</p>}</details>
            <details><summary>Jurisdiction and eligibility</summary>{currentDetail.ahj && <Rows values={currentDetail.ahj} />}{(reasonCodes.length > 0 || reasons.length > 0 || Boolean(eligibility.status)) && <div className="house-eligibility"><b>{human(eligibility.status) || 'Eligibility details'}</b>{reasonCodes.map((reason, index) => <p key={`code-${index}`}>{human(reason)}</p>)}{reasons.map((reason, index) => <p key={`reason-${index}`}>{typeof reason === 'string' ? reason : display((reason as Record<string, unknown>).message)}</p>)}{Array.isArray(eligibility.unknown_checks) && eligibility.unknown_checks.length > 0 && <small>Unknown checks: {display(eligibility.unknown_checks)}</small>}{Array.isArray(eligibility.pending_checks) && eligibility.pending_checks.length > 0 && <small>Pending checks: {display(eligibility.pending_checks)}</small>}</div>}</details>
            <details><summary>Design history</summary><p className="house-muted">Design generation is unavailable.</p>{Array.isArray(design.history) && (design.history as unknown[]).length > 0 && <Rows values={{ history: design.history }} />}</details>
            <details><summary>History · {history.length}</summary>{history.length ? <ul className="house-history">{history.map((item, index) => <li key={item.id ?? index}><b>{item.label || human(item.kind) || 'Activity'}</b><small>{date(item.created_at, true)}</small></li>)}</ul> : <p className="house-muted">No history recorded.</p>}</details>
            {(currentDetail.neighborhoods?.length ?? 0) > 0 && <details><summary>Neighborhoods · {currentDetail.neighborhoods?.length}</summary><ul className="house-history">{currentDetail.neighborhoods?.map((item) => <li key={item.area_id}>{item.label}</li>)}</ul></details>}
            {(currentDetail.source_warnings?.length ?? 0) > 0 && <details><summary>Source notes · {currentDetail.source_warnings?.length}</summary><ul className="house-history">{currentDetail.source_warnings?.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
          </div>
        </>}
      </main> : <main className="house-content">
        <p className="house-summary-line">{(shownCounts.total ?? scopedHomes.length).toLocaleString()} houses · {(shownCounts.reviewed ?? scopedHomes.filter((home) => reviewed(home.review_status)).length).toLocaleString()} reviewed · {(shownCounts.needs_attention ?? scopedHomes.filter((home) => home.needs_attention).length).toLocaleString()} need attention · {(shownCounts.designed ?? 0).toLocaleString()} designed</p>
        {summaryLoading && <p className="house-state" role="status">Loading house list…</p>}
        {summaryError && <div className="house-error" role="alert"><span>{summaryError}</span><button type="button" onClick={() => setRetryKey((value) => value + 1)}>Retry</button></div>}
        {!summaryLoading && !summaryError && currentSummary && <div className="house-list" aria-label="Houses">
          {visibleHomes.map((home) => <button type="button" className="house-list-row" key={home.parcel_id} onClick={() => onInspectHouse(home.parcel_id)}>
            <span className="house-row-title">{home.address || home.parcel_id}<i aria-hidden="true">›</i></span>
            <span className="house-row-states"><span className={home.needs_attention ? 'text-attention' : ''}>Review: {rowReview(home)}</span><span>Design: {human(home.design_status) || 'Not run'}</span>{home.rental_status === true && <span>Rental</span>}</span>
            {home.eligibility_status === 'excluded' && <small className="house-excluded">Eligibility: excluded · remains in neighborhood</small>}
          </button>)}
          {orderedHomes.length > showCount && <button type="button" className="house-more" onClick={() => setShowCount((value) => Math.min(value + 10, orderedHomes.length))}>Load {Math.min(orderedHomes.length - showCount, 10)} more houses</button>}
          {orderedHomes.length === 0 && <p className="house-muted">No houses found in this selection.</p>}
        </div>}
        {selectedAreaId && <div className="house-area-actions"><button type="button" onClick={onRedrawArea} disabled={locked || !onRedrawArea}>Redraw area</button><button type="button" onClick={onRemoveArea} disabled={locked || !onRemoveArea}>Remove area</button></div>}
      </main>}

      <footer className="house-foot">
        {!isHouse ? <><div className="house-foot-links"><button type="button" className="house-text-button" disabled={locked} onClick={onAddNeighborhoods}>Add neighborhoods</button><button type="button" className="house-text-button" disabled={locked} onClick={onSelectSamples}>Select samples</button></div><button type="button" className="house-primary" disabled={selection.area_ids.length === 0} onClick={onReview}>Review selection</button></> : <><span className="house-foot-note">Review actions use the existing review tools.</span>{onReviewHouse && <button type="button" className="house-primary" onClick={() => onReviewHouse(selectedParcelId!)}>Review this house</button>}</>}
      </footer>
    </section>
  </div>
}
