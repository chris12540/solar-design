const assert = require('node:assert/strict');
const { snapshot, assertSame } = require('./interaction-cases.cjs');

async function runReopenChecks(page) {
  const previous = await page.evaluate(() => ({ errors: [], blocked: [], ui: window.lab.originalUi && { ...window.lab.originalUi, errors: [], localMetadataRequests: [] },
    interactionCase: window.lab.interactionCase, drawingEvidence: window.lab.drawingEvidence,
    dragEvidence: window.lab.dragEvidence, roundTrip: window.lab.roundTrip,
    caseImportVerified: window.lab.caseImportVerified, caseExportVerified: window.lab.caseExportVerified }));
  async function collect() {
    const e = await page.evaluate(() => ({ errors: window.lab.errors, blocked: window.lab.blocked, ui: window.lab.originalUi }));
    previous.errors.push(...e.errors); previous.blocked.push(...e.blocked);
    if (previous.ui && e.ui) { previous.ui.errors.push(...e.ui.errors); previous.ui.localMetadataRequests.push(...e.ui.localMetadataRequests); }
  }
  async function reopen(id) {
    await page.getByLabel('Saved examples').selectOption(id);
    await collect();
    await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }), page.getByRole('button', { name: 'Reopen saved', exact: true }).click()]);
    await page.waitForFunction(() => window.lab?.stage === 'ready');
    await page.waitForTimeout(700);
  }
  async function edit(amount) {
    await page.evaluate(amount => {
      const roof = window.engine.dataStore.findAllHeirs('roof')[0], model = roof.type === 'roof' ? roof.perimeterEdges[0] : roof;
      if (!Number.isFinite(model.height)) throw new Error('Edit fixture needs a finite height');
      window.engine.bridge.setModelProperty(model.id, 'height', model.height + amount);
    }, amount);
    await page.waitForTimeout(500);
  }
  await page.getByLabel('Example name').fill('Saved checkpoint');
  await page.getByRole('button', { name: 'Save locally', exact: true }).click();
  await page.waitForFunction(() => Object.values(JSON.parse(localStorage.getItem('aurora-local-lab:examples:v1') || '{}')).some(r => r.name === 'Saved checkpoint'));
  const original = await page.evaluate(() => {
    const id = sessionStorage.getItem('aurora-local-lab:active-example');
    return { id, record: JSON.parse(localStorage.getItem('aurora-local-lab:examples:v1'))[id] };
  });
  const checkpoint = await page.evaluate(snapshot);
  const countBefore = await page.evaluate(() => Object.keys(JSON.parse(localStorage.getItem('aurora-local-lab:examples:v1'))).length);
  await reopen(original.id); await reopen(original.id);
  assertSame(await page.evaluate(snapshot), checkpoint);
  assert.equal(await page.evaluate(() => Object.keys(JSON.parse(localStorage.getItem('aurora-local-lab:examples:v1'))).length), countBefore, 'Unchanged reloads must not create recovery duplicates');
  await page.getByLabel('Example name').fill('Uncommitted edits');
  await edit(0.75);
  const edited = await page.evaluate(snapshot);
  assert.notDeepEqual(edited, checkpoint);
  await reopen(original.id);
  assertSame(await page.evaluate(snapshot), checkpoint);
  const recovery = await page.evaluate(id => Object.entries(JSON.parse(localStorage.getItem('aurora-local-lab:examples:v1')))
    .find(([key, record]) => key !== id && record.recoveredFrom === id && record.name === 'Uncommitted edits (recovery)'), original.id);
  assert.ok(recovery, 'Reverting the active example must retain an unsaved recovery copy');
  if (original.record.importedFrom) assert.deepEqual(recovery[1].importedFrom, original.record.importedFrom);
  await reopen(recovery[0]);
  assertSame(await page.evaluate(snapshot), edited);
  await page.getByLabel('Example name').fill('Edited recovered case');
  await edit(0.25);
  const latest = await page.evaluate(snapshot);
  const native = await page.evaluate(async () => {
    const value = await window.engine.bridge.getJsonToSave(); return typeof value === 'string' ? value : JSON.stringify(value);
  });
  await reopen(original.id);
  assertSame(await page.evaluate(snapshot), checkpoint);
  const saved = await page.evaluate(id => JSON.parse(localStorage.getItem('aurora-local-lab:examples:v1'))[id], recovery[0]);
  assert.equal(saved.name, 'Edited recovered case');
  assert.equal(saved.json, native, 'Switching examples must save the outgoing current state');
  assert.equal(saved.recoveredFrom, original.id, 'Saving must retain recovery metadata');
  if (original.record.importedFrom) assert.deepEqual(saved.importedFrom, original.record.importedFrom);
  await reopen(recovery[0]);
  assertSame(await page.evaluate(snapshot), latest);
  await page.evaluate(previous => {
    window.lab.errors.push(...previous.errors); window.lab.blocked.push(...previous.blocked);
    if (previous.ui) {
      window.lab.originalUi.errors.push(...previous.ui.errors);
      window.lab.originalUi.localMetadataRequests.push(...previous.ui.localMetadataRequests);
    }
    for (const key of ['interactionCase','drawingEvidence','dragEvidence','roundTrip','caseImportVerified','caseExportVerified']) if (previous[key]) window.lab[key] = previous[key];
    window.lab.reopenRecoveryVerified = { activeRevertRecovered: true, outgoingEditsSaved: true, recoveryMetadataRetained: true };
  }, previous);
}

module.exports = { runReopenChecks };
