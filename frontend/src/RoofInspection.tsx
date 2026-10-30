import { useEffect, useId, useRef, useState } from 'react'
import type { Selection } from './HouseSheet'
import './roofInspection.css'
import RoofBuilderBridge from './RoofBuilderBridge'

type Point = [number, number]
type Polygon = Point[]
type RoofFace = {
  id: string
  source_plane_id?: string | null
  polygon: Polygon
  holes?: Polygon[]
  pitch_degrees?: number | null
  azimuth_degrees?: number | null
  area_m2?: number | null
  fit_rmse_m?: number | null
  pixel_count?: number | null
}
type Obstruction = { polygon: Polygon; holes?: Polygon[]; area_m2?: number | null; height_m?: number | null }
type RefinedPart = { polygon: Polygon; holes?: Polygon[] }
type RefinedFace = {
  id: string
  parts: RefinedPart[]
  source_region_ids?: string[]
  source_plane_ids?: string[]
  pitch_degrees?: number | null
  azimuth_degrees?: number | null
  area_m2?: number | null
  largest_contiguous_area_m2?: number | null
  fit_rmse_m?: number | null
}
type RefinedEdge = { id: string; face_ids: string[]; kind: 'ridge' | 'hip' | 'valley' | 'unknown'; coordinates: Point[]; inferred: boolean }
type RoofCandidate = {
  face_id: string
  rank: number
  score: number
  area_m2: number
  contiguous_area_m2: number
  reasons: string[]
  unknown_checks: string[]
  shading_status: 'unknown' | 'available'
}
type RoofRefinement = {
  algorithm_version: string
  status: string
  face_groups?: RefinedFace[]
  edges?: RefinedEdge[]
  inferred_regions?: RefinedPart[]
  quality?: { coverage_fraction?: number; added_area_m2?: number; max_boundary_deviation_m?: number; height_rmse_m?: number; outline_iou?: number; overlap_area_m2?: number; unexplained_fraction?: number; checks_passed?: boolean; photo_edge_support?: number }
  warnings?: string[]
  design_ready?: boolean
  candidates?: RoofCandidate[]
}
export type RoofResult = {
  status: 'needs_review' | 'unavailable'
  algorithm_version?: string
  faces?: RoofFace[]
  obstruction_candidates?: Obstruction[]
  roof_outline?: { polygon: Polygon; holes?: Polygon[] }
  bounds?: { min_x: number; min_y: number; max_x: number; max_y: number }
  quality?: { assigned_fraction?: number; unassigned_fraction?: number; valid_pixel_count?: number; plane_count?: number; source_height_coverage_fraction?: number; polygon_coverage_fraction?: number }
  warnings?: string[]
  refinement?: RoofRefinement
  fitting?: RoofRefinement
  photo?: { data_url: string; bounds: Bounds; imagery_date?: string; alignment_status?: string }
  ahj?: { status?: string }
  design_ready?: boolean
}
type RoofStatus = 'not_run' | 'expired' | 'running' | 'needs_review' | 'unavailable'
type StatusResponse = { status: RoofStatus; result?: RoofResult; fetched_at?: string; expires_at?: string; message?: string; reused?: boolean }
type Model = StatusResponse & { error?: string; checked?: boolean }

async function post<T>(path: string, body: unknown, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: 'POST', credentials: 'same-origin', signal,
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { const payload = await response.json() as { detail?: unknown }; if (typeof payload.detail === 'string') message = payload.detail } catch { /* response may have no JSON body */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

function validPolygon(value: unknown): value is Polygon {
  return Array.isArray(value) && value.length >= 3 && value.every((point) => Array.isArray(point) && point.length >= 2 && Number.isFinite(point[0]) && Number.isFinite(point[1]))
}
function polygonPath(polygon: Polygon, bounds: { min_x: number; min_y: number; max_x: number; max_y: number }, width: number, height: number, padding: number) {
  const spanX = Math.max(bounds.max_x - bounds.min_x, 0.001)
  const spanY = Math.max(bounds.max_y - bounds.min_y, 0.001)
  const scale = Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY)
  const offsetX = (width - spanX * scale) / 2
  const offsetY = (height - spanY * scale) / 2
  return polygon.map(([x, y], index) => `${index ? 'L' : 'M'}${(offsetX + (x - bounds.min_x) * scale).toFixed(1)},${(height - offsetY - (y - bounds.min_y) * scale).toFixed(1)}`).join(' ') + ' Z'
}
type Bounds = { min_x: number; min_y: number; max_x: number; max_y: number }
function sharedBounds(result: RoofResult): Bounds {
  const coordinates: Point[] = []
  const add = (polygon?: Polygon) => { if (polygon) coordinates.push(...polygon) }
  add(result.roof_outline?.polygon)
  result.roof_outline?.holes?.forEach(add)
  result.faces?.forEach((face) => { add(face.polygon); face.holes?.forEach(add) })
  result.obstruction_candidates?.forEach((item) => { add(item.polygon); item.holes?.forEach(add) })
  result.refinement?.face_groups?.forEach((group) => group.parts.forEach((part) => { add(part.polygon); part.holes?.forEach(add) }))
  result.refinement?.inferred_regions?.forEach((part) => { add(part.polygon); part.holes?.forEach(add) })
  result.refinement?.edges?.forEach((edge) => coordinates.push(...edge.coordinates))
  result.fitting?.face_groups?.forEach((group) => group.parts.forEach((part) => { add(part.polygon); part.holes?.forEach(add) }))
  result.fitting?.edges?.forEach((edge) => coordinates.push(...edge.coordinates))
  if (result.photo?.alignment_status === 'georeferenced' && Object.values(result.photo.bounds).every(Number.isFinite)) {
    coordinates.push([result.photo.bounds.min_x, result.photo.bounds.min_y], [result.photo.bounds.max_x, result.photo.bounds.max_y])
  }
  if (result.bounds && [result.bounds.min_x, result.bounds.min_y, result.bounds.max_x, result.bounds.max_y].every(Number.isFinite)) {
    coordinates.push([result.bounds.min_x, result.bounds.min_y], [result.bounds.max_x, result.bounds.max_y])
  }
  return coordinates.length
    ? { min_x: Math.min(...coordinates.map(([x]) => x)), min_y: Math.min(...coordinates.map(([, y]) => y)), max_x: Math.max(...coordinates.map(([x]) => x)), max_y: Math.max(...coordinates.map(([, y]) => y)) }
    : { min_x: 0, min_y: 0, max_x: 1, max_y: 1 }
}
function partPath(part: RefinedPart, bounds: Bounds) {
  return [polygonPath(part.polygon, bounds, 360, 240, 28), ...(part.holes ?? []).filter(validPolygon).map((hole) => polygonPath(hole, bounds, 360, 240, 28))].join(' ')
}
function RoofDiagram({ result, view }: { result: RoofResult; view: 'raw' | 'refined' | 'fitted' }) {
  const [showPhoto, setShowPhoto] = useState(true)
  const [showRaw, setShowRaw] = useState(false)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const enlargeRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  useEffect(() => {
    const dialog = dialogRef.current
    return () => { if (dialog?.open) dialog.close() }
  }, [result, view])
  const viewLabel = view === 'raw' ? 'Raw reconstruction' : view === 'refined' ? 'Refined roof' : 'Fitted roof'
  const fitted = view === 'fitted'
  const photo = fitted && result.photo?.alignment_status === 'georeferenced' && /^data:image\/(png|jpeg|webp);base64,/.test(result.photo.data_url) && Object.values(result.photo.bounds).every(Number.isFinite) ? result.photo : null
  const faces = (result.faces ?? []).filter((face) => validPolygon(face.polygon))
  const refinement = fitted ? result.fitting : result.refinement
  const groups = (refinement?.face_groups ?? []).filter((group) => group.parts.some((part) => validPolygon(part.polygon)))
  const outline = result.roof_outline && validPolygon(result.roof_outline.polygon) ? result.roof_outline : null
  const obstructions = (result.obstruction_candidates ?? []).filter((item) => validPolygon(item.polygon))
  const bounds = sharedBounds(result)
  const colors = ['#90b99c', '#aec99b', '#82aaa7', '#c2b989', '#9ca9cb', '#c49b82']
  const drawRaw = view === 'raw' || !refinement
  const project = ([x, y]: Point) => {
    const spanX = Math.max(bounds.max_x - bounds.min_x, 0.001)
    const spanY = Math.max(bounds.max_y - bounds.min_y, 0.001)
    const scale = Math.min(304 / spanX, 184 / spanY)
    return [(360 - spanX * scale) / 2 + (x - bounds.min_x) * scale, 240 - (240 - spanY * scale) / 2 - (y - bounds.min_y) * scale]
  }
  const photoTopLeft = photo ? project([photo.bounds.min_x, photo.bounds.max_y]) : [0, 0]
  const photoBottomRight = photo ? project([photo.bounds.max_x, photo.bounds.min_y]) : [0, 0]
  const diagram = <>
    {fitted && <div className="roof-photo-controls">
      {photo ? <label><input type="checkbox" checked={showPhoto} onChange={(event) => setShowPhoto(event.target.checked)} />Show photo</label> : <span>Photo unavailable</span>}
      <label><input type="checkbox" checked={showRaw} onChange={(event) => setShowRaw(event.target.checked)} />Raw overlay</label>
      {photo?.imagery_date && <span>Imagery {photo.imagery_date}</span>}
    </div>}
    <svg className={`roof-diagram${photo && showPhoto ? ' roof-diagram-photo' : ''}`} viewBox="0 0 360 240" role="img" aria-label={drawRaw ? `Raw roof reconstruction with ${faces.length} regions and ${obstructions.length} obstruction candidates` : `${fitted ? 'Fitted' : 'Refined'} roof with ${groups.length} face groups and proposed edges`}>
      <title>Local roof geometry · north is up</title>
      <desc>Experimental roof geometry, displayed in local coordinates. Proposed edges are not verified.</desc>
      <rect x="0" y="0" width="360" height="240" rx="8" className="roof-diagram-bg" />
      {photo && showPhoto && <image href={photo.data_url} x={photoTopLeft[0]} y={photoTopLeft[1]} width={photoBottomRight[0] - photoTopLeft[0]} height={photoBottomRight[1] - photoTopLeft[1]} preserveAspectRatio="none"><title>Georeferenced roof photo · north is up</title></image>}
      {outline && <path className="roof-outline-shape" d={[polygonPath(outline.polygon, bounds, 360, 240, 28), ...(outline.holes ?? []).filter(validPolygon).map(hole => polygonPath(hole, bounds, 360, 240, 28))].join(' ')} fill="#dce2df" fillRule="evenodd" stroke="#697970" strokeWidth="1"><title>Roof mask · gray regions remain unassigned</title></path>}
      {drawRaw && faces.map((face, index) => {
        const colorIndex = Math.max(0, Number(face.id.match(/^plane-(\d+)/)?.[1] ?? index + 1) - 1)
        const holes = (face.holes ?? []).filter(validPolygon)
        const d = [polygonPath(face.polygon, bounds, 360, 240, 28), ...holes.map((hole) => polygonPath(hole, bounds, 360, 240, 28))].join(' ')
        return <path key={face.id} d={d} fill={colors[colorIndex % colors.length]} fillRule="evenodd" stroke="#314c3b" strokeWidth="1.5" className="roof-face-shape"><title>{`Roof face ${face.id}`}</title></path>
      })}
      {!drawRaw && (refinement?.inferred_regions ?? []).filter((part) => validPolygon(part.polygon)).map((part, index) => <path key={`inferred-${index}`} d={partPath(part, bounds)} fill="#dce2df" fillRule="evenodd" stroke="#697970" strokeWidth="1.2" className="roof-unknown-shape"><title>Unclassified or inferred region · geometry is uncertain</title></path>)}
      {!drawRaw && groups.map((group, index) => {
        const colorIndex = Math.max(0, Number(group.id.match(/(\d+)/)?.[1] ?? index) % colors.length)
        const d = group.parts.filter((part) => validPolygon(part.polygon)).map((part) => partPath(part, bounds)).join(' ')
        const candidate = !fitted && refinement?.candidates?.find((item) => item.face_id === group.id && item.rank === 1)
        return <g key={group.id}>
          <path d={d} fill={colors[colorIndex % colors.length]} fillRule="evenodd" stroke="#314c3b" strokeWidth="1.5" className="roof-face-shape"><title>{`${fitted ? 'Fitted' : 'Refined'} face group ${group.id}${candidate ? ' · top ranked' : ''}`}</title></path>
          {group.parts.flatMap((part, partIndex) => (part.holes ?? []).filter(validPolygon).map((hole, holeIndex) => <path key={`${partIndex}-${holeIndex}`} d={polygonPath(hole, bounds, 360, 240, 28)} fill="none" stroke="#697970" strokeWidth="1.3" className="roof-hole-outline"><title>Preserved opening · extent remains unknown</title></path>))}
          {candidate && <path d={d} fill="none" fillRule="evenodd" className="roof-candidate-highlight"><title>Top ranked candidate</title></path>}
        </g>
      })}
      {!drawRaw && (refinement?.edges ?? []).filter((edge) => (fitted || edge.inferred) && edge.coordinates.every((point) => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite))).map((edge) => {
        const points = edge.coordinates.map(project).map((point) => point.join(',')).join(' ')
        return <polyline key={edge.id} points={points} fill="none" className="roof-inferred-edge"><title>{`Proposed ${edge.kind} · not verified`}</title></polyline>
      })}
      {fitted && showRaw && faces.map((face) => <path key={`raw-${face.id}`} d={partPath(face, bounds)} fill="none" fillRule="evenodd" className="roof-raw-overlay"><title>Raw region {face.id}</title></path>)}
      {obstructions.map((item, index) => {
        const holes = (item.holes ?? []).filter(validPolygon)
        const d = [polygonPath(item.polygon, bounds, 360, 240, 28), ...holes.map((hole) => polygonPath(hole, bounds, 360, 240, 28))].join(' ')
        return <path key={`obstruction-${index}`} d={d} fill="#e39a52" fillRule="evenodd" stroke="#9c5720" strokeWidth="1.5" className="roof-obstruction-shape"><title>Obstruction candidate</title></path>
      })}
      <g className="roof-north" aria-hidden="true"><path d="M326 54V24m0 0-7 10m7-10 7 10" /><text x="326" y="17" textAnchor="middle">N</text></g>
    </svg>
    <div className="roof-legend">
      {drawRaw ? <><span><i style={{background:'#dce2df'}} />Unassigned roof</span><span><i className="roof-legend-face" />Roof faces</span><span><i className="roof-legend-obstruction" />Obstruction candidates</span></>
        : <><span><i className="roof-legend-face" />{fitted ? 'Fitted' : 'Refined'} face groups</span>{!fitted && <span><i className="roof-legend-unknown" />Unknown / inferred area</span>}<span><i className="roof-legend-edge" />Proposed edge · not verified</span>{!fitted && <span><i className="roof-legend-rank" />Top ranked face</span>}{fitted && showRaw && <span><i className="roof-legend-raw" />Raw regions</span>}{obstructions.length > 0 && <span><i className="roof-legend-obstruction" />Obstruction candidates</span>}</>}
    </div>
    <p className="roof-attribution">Source: Includes solar data from Google</p>
  </>
  return <div className="roof-diagram-wrap">
    <div className="roof-diagram-actions"><button type="button" className="roof-enlarge" ref={enlargeRef} aria-haspopup="dialog" onClick={() => dialogRef.current?.showModal()}>Enlarge</button></div>
    {diagram}
    <dialog className="roof-diagram-modal" ref={dialogRef} aria-labelledby={titleId}
      onKeyDown={(event) => { if (event.key === 'Escape') event.stopPropagation() }}
      onClose={() => { if (enlargeRef.current?.isConnected) enlargeRef.current.focus() }}
      onClick={(event) => {
        event.stopPropagation()
        if (event.target !== event.currentTarget) return
        const bounds = event.currentTarget.getBoundingClientRect()
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) event.currentTarget.close()
      }}>
      <div className="roof-modal-head"><h2 id={titleId}>Roof reconstruction <span>· {viewLabel}</span></h2><button type="button" className="roof-modal-close" onClick={() => dialogRef.current?.close()} autoFocus>Close</button></div>
      <p className="roof-modal-caveat">Experimental · Not ready for production or design</p>
      <div className="roof-modal-diagram">{diagram}</div>
    </dialog>
  </div>
}
function number(value: unknown, digits = 1) { return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—' }
function percent(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` : '—' }
function candidateRows(candidates: RoofCandidate[]) {
  return [...candidates].sort((a, b) => a.rank - b.rank)
}
function faceLabel(id: string) {
  const numberPart = id.match(/(\d+)/)?.[1]
  return numberPart ? `Face ${numberPart}` : `Face ${id}`
}
function CandidateRow({ candidate, detailed = false }: { candidate: RoofCandidate; detailed?: boolean }) {
  return <li className="roof-candidate-row">
    <div className="roof-candidate-title"><b>#{candidate.rank} · {faceLabel(candidate.face_id)}</b>{!detailed && candidate.shading_status === 'unknown' && <span className="roof-exposure-unknown">Exposure unknown</span>}</div>
    <p>Contiguous footprint {number(candidate.contiguous_area_m2)} m²{detailed && ` · total horizontal footprint ${number(candidate.area_m2)} m²`}</p>
    {detailed && <>
      <p><b>Score:</b> {number(candidate.score, 2)} · after preliminary obstruction allowance; before AHJ setbacks and panel fitting</p>
      {!!candidate.reasons.length && <p><b>Ranking factors:</b> {candidate.reasons.join('; ')}</p>}
      {!!candidate.unknown_checks.length && <p><b>Unverified:</b> {candidate.unknown_checks.join('; ')}</p>}
      <p><b>Shading:</b> {candidate.shading_status === 'available' ? 'source exposure available; preliminary' : 'unknown'}</p>
    </>}
  </li>
}

export default function RoofInspection({ selection, parcelId }: { selection: Selection; parcelId: string }) {
  const [model, setModel] = useState<Model>({ status: 'not_run' })
  const [loadingStatus, setLoadingStatus] = useState(false)
  const [reconstructing, setReconstructing] = useState(false)
  const [opened, setOpened] = useState(false)
  const [view, setView] = useState<'raw' | 'refined' | 'fitted'>('refined')
  const activeRequest = useRef<AbortController | null>(null)
  const requestId = useRef(0)
  const selectionKey = JSON.stringify(selection)
  const body = { selection, parcel_id: parcelId }
  const result = model.result
  const rawPlaneIds = new Set((result?.faces ?? []).flatMap((face) => {
    const prefixPlaneId = face.id.match(/^(plane-\d+)(?:-|$)/)?.[1]
    return [face.source_plane_id, prefixPlaneId].filter((id): id is string => Boolean(id))
  }))
  const missingSourcePlaneIds = [...new Set((result?.refinement?.face_groups ?? []).flatMap((group) => group.source_plane_ids ?? []))].filter((id) => !rawPlaneIds.has(id))
  const hasRefinedView = Boolean(result?.refinement && result.refinement.status !== 'unavailable' && (result.refinement.face_groups?.length ?? 0) > 0)
  const hasFittedView = Boolean(result?.fitting?.face_groups?.some((group) => group.parts.some((part) => validPolygon(part.polygon))))
  const showingFitted = hasFittedView && view === 'fitted'
  const showingRefined = hasRefinedView && view === 'refined'
  const activeView = showingFitted ? 'fitted' : showingRefined ? 'refined' : 'raw'
  const hasTabs = hasRefinedView || hasFittedView
  useEffect(() => { setView(hasFittedView ? 'fitted' : hasRefinedView ? 'refined' : 'raw') }, [result, hasFittedView, hasRefinedView])
  const needsRebuild = model.status === 'not_run' || model.status === 'expired'
  const mayRebuild = model.checked === true && !model.error && needsRebuild

  useEffect(() => () => { requestId.current++; activeRequest.current?.abort() }, [selectionKey, parcelId])

  const checkStatus = async () => {
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller
    const id = ++requestId.current
    setLoadingStatus(true); setModel((current) => ({ ...current, error: undefined }))
    try {
      const response = await post<StatusResponse>('/houses/roof/status', body, controller.signal)
      if (requestId.current === id) setModel({ ...response, checked: true })
    } catch (error) {
      if (!controller.signal.aborted && requestId.current === id) setModel({ status: 'not_run', checked: true, error: error instanceof Error ? error.message : 'Could not check roof status.' })
    } finally { if (requestId.current === id) setLoadingStatus(false) }
  }
  const reconstruct = async () => {
    if (reconstructing || !needsRebuild) return
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller
    const id = ++requestId.current
    setReconstructing(true); setModel((current) => ({ ...current, error: undefined }))
    try {
      const response = await post<StatusResponse>('/houses/roof/reconstruct', body, controller.signal)
      if (requestId.current === id) setModel({ ...response, checked: true })
    } catch (error) {
      if (!controller.signal.aborted && requestId.current === id) setModel((current) => ({ ...current, checked: true, error: error instanceof Error ? error.message : 'Could not reconstruct the roof.' }))
    } finally { if (requestId.current === id) setReconstructing(false) }
  }
  const onToggle = (event: React.SyntheticEvent<HTMLDetailsElement>) => {
    const nextOpen = event.currentTarget.open
    setOpened(nextOpen)
    if (nextOpen && !model.checked && !loadingStatus) void checkStatus()
  }
  const onViewTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight' || event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      const tabs: ('raw' | 'refined' | 'fitted')[] = ['raw', ...(hasRefinedView ? ['refined' as const] : []), ...(hasFittedView ? ['fitted' as const] : [])]
      const index = tabs.indexOf(activeView)
      const next = tabs[event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowLeft' ? -1 : 1) + tabs.length) % tabs.length]
      setView(next)
      document.getElementById(`roof-tab-${next}`)?.focus()
    }
  }
  const statusText = model.status === 'running' ? 'A roof reconstruction is already running.'
    : model.status === 'expired' ? 'The saved reconstruction has expired.'
      : model.status === 'unavailable' ? 'Roof reconstruction is unavailable for this house.'
        : model.status === 'needs_review' ? 'Saved roof reconstruction' : 'No roof reconstruction saved.'

  return <details className="roof-inspection" onToggle={onToggle}>
    <summary>Roof reconstruction</summary>
    <div className="roof-panel">
      <h3>Roof geometry · experimental</h3>
      {loadingStatus && <p className="roof-message" role="status">Checking saved roof status…</p>}
      {model.error && <div className="roof-error" role="alert"><span>{model.error}</span>{!result && <button type="button" onClick={() => void checkStatus()} disabled={loadingStatus || reconstructing}>Retry status check</button>}</div>}
      {!loadingStatus && <p className="roof-message">{model.message || statusText}</p>}
      {!loadingStatus && !model.error && model.status === 'needs_review' && !result && <p className="roof-message">Saved roof status has no geometry result.</p>}
      {result && <>
        <RoofBuilderBridge result={result} fetchedAt={model.fetched_at} expiresAt={model.expires_at} />
        {hasTabs && <div className="roof-view-tabs" role="tablist" aria-label="Roof geometry view">
          <button type="button" role="tab" id="roof-tab-raw" aria-controls="roof-panel-raw" aria-selected={activeView === 'raw'} tabIndex={activeView === 'raw' ? 0 : -1} onClick={() => setView('raw')} onKeyDown={onViewTabKeyDown}>Raw reconstruction</button>
          {hasRefinedView && <button type="button" role="tab" id="roof-tab-refined" aria-controls="roof-panel-refined" aria-selected={activeView === 'refined'} tabIndex={activeView === 'refined' ? 0 : -1} onClick={() => setView('refined')} onKeyDown={onViewTabKeyDown}>Refined roof</button>}
          {hasFittedView && <button type="button" role="tab" id="roof-tab-fitted" aria-controls="roof-panel-fitted" aria-selected={activeView === 'fitted'} tabIndex={activeView === 'fitted' ? 0 : -1} onClick={() => setView('fitted')} onKeyDown={onViewTabKeyDown}>Fitted roof</button>}
        </div>}
        <div role={hasTabs ? 'tabpanel' : undefined} id={hasTabs ? `roof-panel-${activeView}` : undefined} aria-labelledby={hasTabs ? `roof-tab-${activeView}` : undefined}>
          <div className="roof-result-head">
            <b>{showingFitted ? `${result.fitting?.face_groups?.length ?? 0} fitted face groups` : showingRefined ? `${result.refinement?.face_groups?.length ?? 0} refined face groups · ${result.faces?.length ?? 0} raw regions` : `${result.faces?.length ?? 0} regions · ${result.quality?.plane_count ?? 0} planes`}</b>
            <span>Unmodeled roof {percent(showingFitted ? result.fitting?.quality?.unexplained_fraction : showingRefined ? 1 - (result.refinement?.quality?.coverage_fraction ?? 0) : (result.quality?.polygon_coverage_fraction === undefined ? result.quality?.unassigned_fraction : 1 - result.quality.polygon_coverage_fraction))}</span>
          </div>
          <RoofDiagram key={`${selectionKey}:${parcelId}`} result={result} view={activeView} />
          {showingFitted && <details className="roof-face-list roof-fit-checks"><summary>Experimental · Needs validation</summary>
            <p className="roof-message">Height RMSE {number(result.fitting?.quality?.height_rmse_m, 2)} m · Outline IoU {number(result.fitting?.quality?.outline_iou, 2)} · Overlap {number(result.fitting?.quality?.overlap_area_m2, 2)} m²</p>
            <p className="roof-message">Coverage {percent(result.fitting?.quality?.coverage_fraction)} · Boundary deviation {number(result.fitting?.quality?.max_boundary_deviation_m, 2)} m · Photo contrast at edges {percent(result.fitting?.quality?.photo_edge_support)}</p>
            <p className="roof-message">{result.fitting?.algorithm_version} · Automated geometry checks {result.fitting?.quality?.checks_passed === true ? 'passed; validation still required' : result.fitting?.quality?.checks_passed === false ? 'need review' : 'unavailable'}</p>
          </details>}
        </div>
        {result.refinement && showingRefined && <>
          {missingSourcePlaneIds.length > 0 && <p className="roof-source-mismatch" role="status">Source mismatch: refined groups reference raw planes that are missing ({missingSourcePlaneIds.join(', ')}).</p>}
          <section className="roof-candidates" aria-labelledby="roof-candidates-title">
            <h4 id="roof-candidates-title">Top array candidates</h4>
            <p className="roof-ranking-note">Preliminary ranking · after preliminary obstruction allowance · before AHJ setbacks and panel fitting</p>
            {candidateRows(result.refinement.candidates ?? []).slice(0, 3).length
              ? <ol>{candidateRows(result.refinement.candidates ?? []).slice(0, 3).map((candidate) => <CandidateRow key={`${candidate.face_id}-${candidate.rank}`} candidate={candidate} />)}</ol>
              : <p className="roof-message">No array candidates were ranked.</p>}
            <details className="roof-face-list roof-all-candidates"><summary>Full ranking details · {result.refinement.candidates?.length ?? 0}</summary>
              {candidateRows(result.refinement.candidates ?? []).length ? <ol>{candidateRows(result.refinement.candidates ?? []).map((candidate) => <CandidateRow key={`${candidate.face_id}-${candidate.rank}`} candidate={candidate} detailed />)}</ol> : <p className="roof-message">No candidates returned.</p>}
            </details>
          </section>
        </>}
        {model.expires_at && <p className="roof-message">Working model expires {new Date(model.expires_at).toLocaleDateString()}.</p>}
        {model.fetched_at && <p className="roof-message">Saved result checked {new Date(model.fetched_at).toLocaleString()}.</p>}
        <p className="roof-message">Height data coverage: {percent(result.quality?.source_height_coverage_fraction)}</p>
        <p className="roof-caveat">Experimental · Not ready for production or design · Obstruction detection incomplete · AHJ setbacks not applied</p>
        {(result.obstruction_candidates?.length ?? 0) > 0 && <p className="roof-message">{result.obstruction_candidates?.length} obstruction candidates need review.</p>}
        {[...(result.warnings ?? []), ...(result.refinement?.warnings ?? []), ...(result.fitting?.warnings ?? [])].length ? <ul className="roof-warnings">{[...(result.warnings ?? []), ...(result.refinement?.warnings ?? []), ...(result.fitting?.warnings ?? [])].map((warning, index) => <li key={index}>{warning}</li>)}</ul> : null}
        <details className="roof-face-list"><summary>Region details · {result.faces?.length ?? 0}</summary>
          {result.faces?.length ? <ul>{result.faces.map((face) => <li key={face.id}><b>Region {face.id}</b><span>Pitch {number(face.pitch_degrees)}° · Azimuth {number(face.azimuth_degrees)}° · RMSE {number(face.fit_rmse_m, 2)} m</span></li>)}</ul> : <p className="roof-message">No roof faces were returned.</p>}
        </details>
        {result.refinement && <details className="roof-face-list"><summary>Refined face details · {result.refinement.face_groups?.length ?? 0}</summary>
          {result.refinement.face_groups?.length ? <ul>{result.refinement.face_groups.map((face) => <li key={face.id}><b>{face.id} · {face.parts.length} parts</b><span>Pitch {number(face.pitch_degrees)}° · Azimuth {number(face.azimuth_degrees)}° · Footprint {number(face.area_m2)} m² · Largest contiguous {number(face.largest_contiguous_area_m2)} m² · RMSE {number(face.fit_rmse_m, 2)} m</span><span>Source regions: {face.source_region_ids?.join(', ') || '—'} · source planes: {face.source_plane_ids?.join(', ') || '—'}</span></li>)}</ul> : <p className="roof-message">No refined face groups were returned.</p>}
        </details>}
        {result.refinement && <details className="roof-face-list"><summary>Refinement details</summary>
          <p className="roof-message">{result.refinement.algorithm_version} · {result.refinement.status} · coverage {percent(result.refinement.quality?.coverage_fraction)} · added area {number(result.refinement.quality?.added_area_m2)} m² · max boundary deviation {number(result.refinement.quality?.max_boundary_deviation_m, 2)} m</p>
        </details>}
      </>}
      {mayRebuild && !loadingStatus && <>
        <p className="roof-charge-note">Uses fresh saved data when available. New Google roof data may incur API charges.</p>
        <button type="button" className="roof-action" onClick={() => void reconstruct()} disabled={reconstructing || !opened}>
          {reconstructing && <span className="roof-spinner" aria-hidden="true" />}{reconstructing ? 'Reconstructing…' : model.status === 'expired' ? 'Rebuild roof' : 'Reconstruct roof'}
        </button>
      </>}
      {model.status === 'running' && <p className="roof-message">Refresh this panel later to check the saved result.</p>}
      {!result && <p className="roof-attribution">Source: Includes solar data from Google</p>}
    </div>
  </details>
}
