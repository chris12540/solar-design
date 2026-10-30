import { useEffect, useRef, useState } from 'react'

type Origin = { latitude: number; longitude: number; crs: string }
type Ring = [number, number, number][]
type Correction = { schema: string; caseId: string; expiresAt: string; origin: Origin; heightDatum: string; faces: { id: string; vertices: Ring; holes: Ring[] | null; holesKnown: boolean }[]; referenceStatus: string }
type Generator = { origin?: Origin; algorithm_version?: string; faces?: Record<string, unknown>[]; fitting?: { face_groups?: Record<string, unknown>[] } }

export default function RoofBuilderBridge({ result, fetchedAt, expiresAt, editorBase = import.meta.env.VITE_ROOF_EDITOR_URL || 'http://127.0.0.1:5191' }: { result: unknown; fetchedAt?: string; expiresAt?: string; editorBase?: string }) {
  const [message, setMessage] = useState(''), [busy, setBusy] = useState(false), [link, setLink] = useState(''), [correction, setCorrection] = useState<Correction | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const generator = result as Generator
  const key = JSON.stringify(generator.origin)
  useEffect(() => { setLink(''); setCorrection(null); setMessage('') }, [key, fetchedAt])
  useEffect(() => {
    if (!correction) return
    const timer = window.setInterval(() => { if (Date.parse(correction.expiresAt) <= Date.now()) { setCorrection(null); setMessage('Returned correction expired.') } }, 1000)
    return () => window.clearInterval(timer)
  }, [correction])
  const post = async (path: string, body: unknown) => {
    const response = await fetch(editorBase + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : 'Roof builder transfer failed.')
    return data
  }
  const open = async () => {
    setBusy(true); setMessage('Transferring generated geometry…')
    try {
      if (!generator.origin || !fetchedAt || !expiresAt || Date.parse(expiresAt) <= Date.now()) throw new Error('A fresh generated model with coordinate context is required.')
      const fitted = generator.fitting?.face_groups
      const stage = fitted?.length && fitted.every(group => group.plane_model) ? 'fitted' : 'raw'
      const pick = (group: Record<string, unknown>) => ({ id: group.id, polygon: group.polygon, holes: group.holes, parts: group.parts, plane_model: group.plane_model })
      const response = await post('/model-handoff', { name: 'Generated roof for correction', handoff: { schema: 'roof-reconstruction-handoff/v1', heightDatum: 'EGM96', stage, fetchedAt, expiresAt, result: { origin: generator.origin, algorithm_version: generator.algorithm_version, faces: generator.faces?.map(pick), fitting: { face_groups: fitted?.map(pick) } } } })
      setLink(editorBase + response.url); setMessage('Geometry ready. Open roof builder, correct faces, and export a test case to return it here.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not connect. Start local roof builder and load matching property imagery/heights first.') }
    finally { setBusy(false) }
  }
  const receive = async (file?: File) => {
    if (!file) return
    setBusy(true)
    try {
      if (!generator.origin || !expiresAt) throw new Error('Original model coordinate frame unavailable.')
      if (file.size > 20 * 1024 * 1024) throw new Error('Case file exceeds20MB.')
      const packet = JSON.parse(await file.text())
      const data = await post('/model-return', { packet, target: { origin: generator.origin, expiresAt } }) as Correction
      if (data.schema !== 'roof-correction/v1' || data.heightDatum !== 'EGM96' || !Number.isFinite(Date.parse(data.expiresAt)) || Date.parse(data.expiresAt) <= Date.now() || !Array.isArray(data.faces)) throw new Error('Invalid or expired returned geometry.')
      setCorrection(data); setMessage('Manual correction received in original model frame. Automated reconstruction remains available unchanged.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not import correction.') }
    finally { setBusy(false); if (input.current) input.current.value = '' }
  }
  const points = correction?.faces.flatMap(face => face.vertices) ?? []
  const [minX, minY, maxX, maxY] = points.reduce((b, p) => [Math.min(b[0], p[0]), Math.min(b[1], p[1]), Math.max(b[2], p[0]), Math.max(b[3], p[1])], [Infinity, Infinity, -Infinity, -Infinity])
  const scale = points.length ? Math.min(310 / Math.max(.01, maxX - minX), 190 / Math.max(.01, maxY - minY)) : 1
  const ringPath = (ring: Ring) => ring.map(([x, y], i) => `${i ? 'L' : 'M'}${25 + (x - minX) * scale},${215 - (y - minY) * scale}`).join(' ') + ' Z'
  return <section className="roof-builder-bridge" aria-label="Manual roof correction" style={{ borderTop: '1px solid #ccd8ce', marginTop: 16, paddingTop: 12 }}>
    <h4>Manual roof correction</h4>
    <button type="button" onClick={() => void open()} disabled={busy}>Edit generated roof</button>{' '}
    <button type="button" onClick={() => input.current?.click()} disabled={busy}>Import corrected case</button>
    <input ref={input} type="file" hidden accept="application/json,.json" onChange={event => void receive(event.target.files?.[0])} aria-label="Corrected roof case file" />
    {link && <p><a href={link} target="_blank" rel="noopener noreferrer">Open roof builder</a></p>}
    {message && <p role="status">{message}</p>}
    {correction && <>
      <p>{correction.faces.length} manually corrected faces · expires {new Date(correction.expiresAt).toLocaleString()}</p>
      <svg viewBox="0 0 360 240" role="img" aria-label="Returned manually corrected roof"><rect width="360" height="240" fill="#f3f7f4" />{correction.faces.map((face, i) => <path key={face.id + ':' + i} d={[ringPath(face.vertices), ...(face.holes ?? []).map(ringPath)].join(' ')} fill={`hsl(${110 + i * 31 % 120},35%,75%)`} fillRule="evenodd" stroke="#314c3b" />)}</svg>
      {correction.faces.some(face => !face.holesKnown) && <p>Opening boundaries are not fully described for some faces.</p>}
      <button type="button" onClick={() => { if (Date.parse(correction.expiresAt) <= Date.now()) { setCorrection(null); setMessage('Returned correction expired.'); return } const url = URL.createObjectURL(new Blob([JSON.stringify(correction, null, 2)], { type: 'application/json' })); const a = document.createElement('a'); a.href = url; a.download = 'roof-correction.json'; a.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000) }}>Download returned geometry</button>
    </>}
  </section>
}
