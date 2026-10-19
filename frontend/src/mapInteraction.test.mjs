import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('./mapInteraction.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
}).outputText
const { areaClick, backgroundClick, finishSampleSelection, houseClick, shouldFitMap } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const state = (overrides = {}) => ({ mode: 'browse', focusedAreaId: '', selectedHouseId: '', sheetOpen: false, previewOpen: false, ...overrides })

test('first house click focuses its neighborhood; next click inspects the house', () => {
  const first = houseClick(state(), 'north', 'house-1')
  assert.deepEqual(first, { type: 'focus-area', areaId: 'north' })
  assert.deepEqual(houseClick(state({ focusedAreaId: 'north', sheetOpen: true }), 'north', 'house-1'), {
    type: 'inspect-house', areaId: 'north', houseId: 'house-1',
  })
})

test('group-focused house inspection keeps the whole group in focus', () => {
  assert.deepEqual(houseClick(state({ sheetOpen: true }), 'north', 'house-1'), {
    type: 'inspect-house', areaId: 'north', houseId: 'house-1',
  })
})

test('clicking another neighborhood changes focus and map background closes without lookup', () => {
  assert.deepEqual(areaClick(state({ focusedAreaId: 'north' }), 'south'), { type: 'focus-area', areaId: 'south' })
  assert.deepEqual(backgroundClick(state({ focusedAreaId: 'north', sheetOpen: true })), { type: 'close-sheet' })
  assert.deepEqual(backgroundClick(state()), { type: 'none' })
})

test('add mode looks up empty map clicks, while empty click cancels only a preview', () => {
  assert.deepEqual(backgroundClick(state({ mode: 'add' })), { type: 'lookup' })
  assert.deepEqual(backgroundClick(state({ mode: 'add', previewOpen: true })), { type: 'close-preview' })
})

test('empty clicks do not leave drawing or sample selection modes', () => {
  assert.deepEqual(backgroundClick(state({ mode: 'draw', focusedAreaId: 'north' })), { type: 'none' })
  assert.deepEqual(backgroundClick(state({ mode: 'sample', focusedAreaId: 'north' })), { type: 'none' })
})

test('canceling sample selection restores the prior intent and IDs without committing edits', () => {
  assert.deepEqual(finishSampleSelection({ intent: 'single', samples: ['old'] }, ['new'], true), {
    intent: 'single', samples: ['old'], changed: false,
  })
})

test('only initial view, search, and loading a saved set may fit the map', () => {
  for (const reason of ['initial', 'search', 'load-saved']) assert.equal(shouldFitMap(reason), true)
  for (const reason of ['panel', 'preview', 'add', 'inspect']) assert.equal(shouldFitMap(reason), false)
})
