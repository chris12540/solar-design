export type MapMode = 'browse' | 'add' | 'draw' | 'sample'

export type MapInteractionState = {
  mode: MapMode
  focusedAreaId: string
  selectedHouseId: string
  sheetOpen: boolean
  previewOpen: boolean
}

export type MapInteractionAction =
  | { type: 'lookup' }
  | { type: 'close-preview' }
  | { type: 'focus-area'; areaId: string }
  | { type: 'inspect-house'; areaId: string; houseId: string }
  | { type: 'close-sheet' }
  | { type: 'none' }

export type SampleSnapshot = { intent: 'single' | 'sample' | 'all'; samples: string[] }

export function finishSampleSelection(snapshot: SampleSnapshot, current: string[], cancel: boolean) {
  const changed = current.length !== snapshot.samples.length || current.some((id, index) => id !== snapshot.samples[index])
  if (cancel) return { intent: snapshot.intent, samples: [...snapshot.samples], changed: false }
  return { intent: changed && current.length ? 'sample' as const : snapshot.intent, samples: [...current], changed }
}

export function areaClick(_state: MapInteractionState, areaId: string): MapInteractionAction {
  return { type: 'focus-area', areaId }
}

export function houseClick(state: MapInteractionState, areaId: string, houseId: string): MapInteractionAction {
  if (state.mode === 'draw') return { type: 'none' }
  if (!state.focusedAreaId && state.sheetOpen) return { type: 'inspect-house', areaId, houseId }
  if (state.focusedAreaId !== areaId) return { type: 'focus-area', areaId }
  return { type: 'inspect-house', areaId, houseId }
}

export function backgroundClick(state: MapInteractionState): MapInteractionAction {
  if (state.mode === 'draw' || state.mode === 'sample') return { type: 'none' }
  if (state.previewOpen) return { type: 'close-preview' }
  if (state.sheetOpen || state.focusedAreaId || state.selectedHouseId) return { type: 'close-sheet' }
  return state.mode === 'add' ? { type: 'lookup' } : { type: 'none' }
}

/** Search and initial saved-run loading may fit the map; panel changes never do. */
export function shouldFitMap(reason: 'initial' | 'search' | 'load-saved' | 'panel' | 'preview' | 'add' | 'inspect'): boolean {
  return reason === 'initial' || reason === 'search' || reason === 'load-saved'
}
