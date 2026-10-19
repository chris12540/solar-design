import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('./mapPresentation.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
}).outputText
const { areaPresentation, noticeColor, parcelPresentation } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

const notice = (code, severity = 'warning', message = code.replaceAll('_', ' ')) => ({ code, severity, message })

test('AHJ problems outrank parcel gaps and informational notes', () => {
  const result = areaPresentation([
    notice('construction_year_spread', 'info'),
    notice('ahj_unresolved'),
    notice('coverage_incomplete'),
  ], 'ready')

  assert.equal(result.level, 'problem')
  assert.equal(result.notice.code, 'ahj_unresolved')
  assert.equal(result.color, '#a63745')
  assert.equal(noticeColor(notice('coverage_incomplete')), '#a85e12')
  assert.equal(areaPresentation([notice('ahj_conflict')], 'ready').level, 'problem')
})

test('informational notes never dominate an actionable warning', () => {
  const result = areaPresentation([
    notice('construction_year_spread', 'info'),
    notice('estimated_boundary'),
  ], 'ready')

  assert.equal(result.level, 'review')
  assert.equal(result.notice.code, 'estimated_boundary')
  assert.equal(noticeColor(notice('construction_year_spread', 'info')), '#386d9b')
})

test('unknown warning codes use orange and remain actionable', () => {
  const unknown = notice('future_policy_code')
  const result = areaPresentation([unknown], 'ready')

  assert.equal(noticeColor(unknown), '#a85e12')
  assert.equal(result.level, 'review')
  assert.equal(result.notice, unknown)
})

test('backend info statuses with explicit orange codes remain review notices', () => {
  for (const code of ['ahj_provisional', 'recorded_scope']) {
    const infoNotice = notice(code, 'info')
    const result = areaPresentation([infoNotice], 'ready')
    assert.equal(noticeColor(infoNotice), '#a85e12')
    assert.equal(result.level, 'review')
    assert.equal(result.notice.code, code)
  }
})

test('construction-year and single-parcel notes stay informational', () => {
  for (const code of ['construction_year_spread', 'construction_year_incomplete', 'single_parcel_scope', 'ahj_mixed']) {
    const infoNotice = notice(code, 'info')
    assert.equal(noticeColor(infoNotice), '#386d9b')
    assert.equal(areaPresentation([infoNotice], 'ready').level, 'clear')
  }
})

test('pending and failed review without known warnings never appear clear', () => {
  assert.equal(areaPresentation([], 'pending').level, 'pending')
  assert.equal(areaPresentation([], 'failed').level, 'review')
  assert.equal(areaPresentation([], 'failed').color, '#a85e12')
})

test('a known warning keeps its severity visible while review is pending', () => {
  const result = areaPresentation([notice('ahj_unresolved')], 'pending')
  assert.equal(result.level, 'problem')
  assert.equal(result.color, '#a63745')
})

test('rental styling stays distinct without hiding sample or removed state', () => {
  assert.equal(parcelPresentation('#a85e12', true, false, false).color, '#77549b')
  assert.equal(parcelPresentation('#a85e12', true, true, false).color, '#243d30')
  assert.equal(parcelPresentation('#a85e12', true, true, true).color, '#a3aaa4')
  assert.equal(parcelPresentation('#a85e12', true, false, false).dashArray, '4 3')
  assert.equal(parcelPresentation('#a85e12', true, true, true).dashArray, undefined)
})
