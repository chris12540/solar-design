const assert = require('node:assert/strict');
const fs = require('node:fs');
const { createHash } = require('node:crypto');
const { snapshot, assertSame } = require('./interaction-cases.cjs');

async function runImportChecks(page, packet) {
  const expected = await page.evaluate(snapshot);
  const libraryBefore = await page.evaluate(() => localStorage.getItem('aurora-local-lab:examples:v1'));
  async function choose(value, navigate = false) {
    const waiting = page.waitForEvent('filechooser');
    await page.getByRole('button', { name: 'Open test case', exact: true }).click();
    const chooser = await waiting;
    const files = { name: 'manual-case.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(value)) };
    if (navigate) await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }), chooser.setFiles(files)]);
    else await chooser.setFiles(files);
  }
  const invalid = [];
  const checksum = structuredClone(packet); checksum.nativeDesignJson += ' '; invalid.push(checksum);
  const engine = structuredClone(packet); engine.provenance.engineArtifacts['cad-bundle.js'] = '0'.repeat(64); invalid.push(engine);
  const geometry = structuredClone(packet); geometry.geometry.buildings[0].faces[0].vertices[0][0] += 1; invalid.push(geometry);
  const external = structuredClone(packet); external.provenance.externalInputsRegistered = true; invalid.push(external);
  const schema = structuredClone(packet); schema.schema = 'unrecognized'; invalid.push(schema);
  const missingNative = structuredClone(packet);
  const model = JSON.parse(missingNative.nativeDesignJson); delete model.format_version;
  missingNative.nativeDesignJson = JSON.stringify(model);
  missingNative.nativeDesignSha256 = createHash('sha256').update(missingNative.nativeDesignJson).digest('hex');
  invalid.push(missingNative);
  for (const bad of invalid) {
    await choose(bad);
    await page.waitForFunction(() => typeof window.lab.caseImportError === 'string');
    assertSame(await page.evaluate(snapshot), expected);
    assert.equal(await page.evaluate(() => localStorage.getItem('aurora-local-lab:examples:v1')), libraryBefore,
      'Rejected file must not mutate saved examples');
  }
  await page.getByLabel('Example name').fill('Unsaved before file import');
  await page.evaluate(() => {
    const roof = window.engine.dataStore.findAllHeirs('roof')[0];
    const model = roof.type === 'roof' ? roof.perimeterEdges[0] : roof;
      if (!Number.isFinite(model.height)) throw new Error('Edit fixture needs a finite height');
    window.engine.bridge.setModelProperty(model.id, 'height', model.height + 0.5);
  });
  await page.waitForTimeout(500);
  const changed = await page.evaluate(snapshot);
  assert.notDeepEqual(changed, expected, 'Preservation check must have an edited current model');
  const nativeBefore = await page.evaluate(async () => {
    const json = await window.engine.bridge.getJsonToSave(); return typeof json === 'string' ? json : JSON.stringify(json);
  });
  const previous = await page.evaluate(() => ({ ui: window.lab.originalUi, errors: window.lab.errors, blocked: window.lab.blocked,
    interactionCase: window.lab.interactionCase, drawingEvidence: window.lab.drawingEvidence,
    dragEvidence: window.lab.dragEvidence, roundTrip: window.lab.roundTrip }));
  async function collectEvidence() {
    const current = await page.evaluate(() => ({ errors: window.lab.errors, blocked: window.lab.blocked, ui: window.lab.originalUi }));
    previous.errors.push(...current.errors); previous.blocked.push(...current.blocked);
    if (previous.ui && current.ui) {
      previous.ui.errors.push(...current.ui.errors);
      previous.ui.localMetadataRequests.push(...current.ui.localMetadataRequests);
    }
  }
  await choose(packet, true);
  await page.waitForFunction(() => window.lab?.stage === 'ready');
  await page.waitForTimeout(700);
  assertSame(await page.evaluate(snapshot), expected);
  const storage = await page.evaluate(() => ({
    active: sessionStorage.getItem('aurora-local-lab:active-example'),
    library: JSON.parse(localStorage.getItem('aurora-local-lab:examples:v1')),
  }));
  const preserved = Object.values(storage.library).find(r => r.name === 'Unsaved before file import');
  assert.ok(preserved, 'Current example must be preserved before import');
  assert.equal(preserved.json, nativeBefore, 'Preservation must retain the edited native payload');
  assert.notEqual(storage.active, packet.caseId, 'Import must fork a local identity');
  assert.equal(storage.library[storage.active].importedFrom.nativeDesignSha256, packet.nativeDesignSha256);
  await page.getByLabel('Example name').fill('Imported after save');
  await page.getByRole('button', { name: 'Save locally', exact: true }).click();
  await page.waitForFunction(id => JSON.parse(localStorage.getItem('aurora-local-lab:examples:v1'))[id]?.name === 'Imported after save', storage.active);
  assert.equal(await page.evaluate(id => JSON.parse(localStorage.getItem('aurora-local-lab:examples:v1'))[id].importedFrom.nativeDesignSha256, storage.active), packet.nativeDesignSha256);
  await collectEvidence();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.lab?.stage === 'ready');
  await page.waitForTimeout(700);
  assertSame(await page.evaluate(snapshot), expected);
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export test case', exact: true }).click()]);
  const filename = await download.path();
  const again = JSON.parse(fs.readFileSync(filename, 'utf8'));
  assert.equal(again.importedFrom.caseId, packet.caseId);
  assert.equal(again.importedFrom.nativeDesignSha256, packet.nativeDesignSha256);
  await collectEvidence();
  await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }), page.getByRole('button', { name: 'New example', exact: true }).click()]);
  await page.waitForFunction(() => window.lab?.stage === 'ready');
  await page.waitForTimeout(700);
  assert.equal((await page.evaluate(snapshot)).roofs.length, 0, 'New example must open an empty scene');
  await page.getByLabel('Saved examples').selectOption(storage.active);
  await collectEvidence();
  await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }), page.getByRole('button', { name: 'Reopen saved', exact: true }).click()]);
  await page.waitForFunction(() => window.lab?.stage === 'ready');
  await page.waitForTimeout(700);
  assertSame(await page.evaluate(snapshot), expected);
  await page.evaluate(() => window.lab.caseImportVerified = {
    rejectedFiles: 6, currentExamplePreserved: true, geometryRestored: true,
    refreshRetained: true, provenanceReexported: true, provenanceSaved: true, newExampleAndReopen: true,
  });
  return previous;
}

module.exports = { runImportChecks };
