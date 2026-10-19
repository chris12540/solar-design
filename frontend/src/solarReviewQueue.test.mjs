import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
const source = await readFile(new URL('./solarReviewQueue.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } }).outputText
const { runSolarReviewQueue } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)
const batch = (checked, remaining) => ({ checked_count: checked, remaining_count: remaining, cached_count: 0, failed_count: 0 })

test('one start advances multiple batches and refreshes real results after each', async () => {
  const batches = [batch(10, 12), batch(10, 2), batch(2, 0)]
  const progress = []
  let reads = 0
  const result = await runSolarReviewQueue({ checkBatch: async () => batches.shift(), refresh: async () => ({ version: ++reads }), onProgress: (...args) => progress.push(args), shouldStop: () => false })
  assert.deepEqual(result, { checked: 22, remaining: 0, paused: false })
  assert.deepEqual(progress.map(([report, checked, remaining]) => [report.version, checked, remaining]), [[1,10,12],[2,20,2],[3,22,0]])
})
test('pause finishes in-flight batch and never starts the next', async () => {
  let paused = false, calls = 0, refreshed = false
  const result = await runSolarReviewQueue({ checkBatch: async () => { calls++; paused = true; return batch(10, 12) }, refresh: async () => { refreshed = true; return {} }, onProgress: () => {}, shouldStop: () => paused })
  assert.deepEqual(result, { checked: 10, remaining: 12, paused: true })
  assert.equal(calls, 1); assert.equal(refreshed, true)
})
test('closed review never begins a lookup', async () => {
  let calls = 0
  await runSolarReviewQueue({ checkBatch: async () => { calls++; return batch(1,0) }, refresh: async () => ({}), onProgress: () => {}, shouldStop: () => true })
  assert.equal(calls, 0)
})
test('cache-only completion makes no extra batch requests', async () => {
  let calls = 0
  const result = await runSolarReviewQueue({ checkBatch: async () => { calls++; return batch(0,0) }, refresh: async () => ({}), onProgress: () => {}, shouldStop: () => false })
  assert.equal(calls, 1); assert.equal(result.paused, false)
})
test('failure stops queue instead of silently repeating paid requests', async () => {
  let calls = 0
  await assert.rejects(runSolarReviewQueue({ checkBatch: async () => { calls++; throw new Error('Quota reached') }, refresh: async () => ({}), onProgress: () => {}, shouldStop: () => false }), /Quota reached/)
  assert.equal(calls, 1)
})
test('non-advancing batch stops with retained results', async () => {
  let calls = 0, progress = 0
  await assert.rejects(runSolarReviewQueue({ checkBatch: async () => { calls++; return batch(0,3) }, refresh: async () => ({}), onProgress: () => progress++, shouldStop: () => false }), /no homes advanced/)
  assert.equal(calls, 1); assert.equal(progress, 1)
})

test('repeated attempts cannot loop indefinitely without reducing remaining homes', async () => {
  let calls = 0
  await assert.rejects(runSolarReviewQueue({ checkBatch: async () => { calls++; return batch(10,20) }, refresh: async () => ({}), onProgress: () => {}, shouldStop: () => false }), /remaining homes did not decrease/)
  assert.equal(calls, 2)
})
