import { useId } from 'react'
import { GeoJSON, Pane } from 'react-leaflet'
import type { Geometry } from 'geojson'

export type DesignProgressState =
  | { scope: 'none' }
  | { scope: 'area'; areaId: string }
  | { scope: 'samples'; areaId: string; parcelIds: string[] }

type ProgressArea = {
  id: string
  geometry: Geometry | null
  parcels: { id: string; geometry: Geometry | null }[]
}

type Props = {
  area: ProgressArea
  progress: DesignProgressState
}

/** Map-only progress overlay. It does not create or advance design work. */
export default function DesignProgress({ area, progress }: Props) {
  const patternId = `design-progress-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  if (progress.scope === 'none' || progress.areaId !== area.id) return null

  const geometries = progress.scope === 'area'
    ? area.geometry ? [{ key: `area-${area.id}`, geometry: area.geometry }] : []
    : area.parcels
      .filter(parcel => progress.parcelIds.includes(parcel.id) && parcel.geometry !== null)
      .map(parcel => ({ key: `parcel-${parcel.id}`, geometry: parcel.geometry as Geometry }))

  if (!geometries.length) return null

  return (
    <Pane name="designProgressPane" className="design-progress-pane" style={{ pointerEvents: 'none' }}>
      <svg className="design-progress-defs" aria-hidden="true" focusable="false">
        <defs>
          <pattern id={`${patternId}-stripes`} width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="14" height="14" fill="rgba(255,255,255,.20)" />
            <rect className="design-progress-stripe" width="5" height="14" fill="rgba(255,255,255,.76)" />
          </pattern>
        </defs>
      </svg>
      {geometries.map(({ key, geometry }) => (
        <GeoJSON
          key={key}
          data={geometry as never}
          interactive={false}
          bubblingMouseEvents={false}
          pathOptions={{
            className: 'design-progress-shape',
            color: 'transparent',
            weight: 0,
            fillColor: `url(#${patternId}-stripes)`,
            fillOpacity: 1,
          }}
        />
      ))}
    </Pane>
  )
}
