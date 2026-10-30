const assert = require('node:assert/strict');
const { snapshot, assertSame } = require('./interaction-cases.cjs');
const KEY = 'aurora-local-lab:tab-draft:v1';
async function runDraftChecks(page) {
  const previous = await page.evaluate(() => ({ ...window.lab }));
  const diagnostics = { errors: [], blocked: [], uiErrors: [], queries: [] };
  async function reload() {
    const d = await page.evaluate(() => ({ errors: window.lab.errors, blocked: window.lab.blocked,
      uiErrors: window.lab.originalUi?.errors || [], queries: window.lab.originalUi?.localMetadataRequests || [] }));
    for (const key of Object.keys(diagnostics)) diagnostics[key].push(...d[key]);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => window.lab?.stage === 'ready' && window.lab.tabDrafts, null, {timeout:30000});
    await page.waitForTimeout(500);
  }
  async function edit() {
    await page.evaluate(() => {
      const roof = window.engine.dataStore.findAllHeirs('roof')[0];
      const model = roof.type === 'roof' ? roof.perimeterEdges[0] : roof;
      if (!Number.isFinite(model.height)) throw Error('Finite height required');
      window.engine.bridge.setModelProperty(model.id, 'height', model.height + 0.4);
    });
    await page.waitForTimeout(600);
  }
  async function draftAfter(previousJson) {
    await page.waitForFunction(({KEY,previousJson}) => {
      const value = JSON.parse(sessionStorage.getItem(KEY) || 'null');
      return value && value.json !== previousJson;
    }, { KEY, previousJson }, { timeout: 15000 });
    return page.evaluate(KEY => JSON.parse(sessionStorage.getItem(KEY)), KEY);
  }
  await page.getByLabel('Example name').fill('Draft checkpoint');
  await page.getByRole('button', { name: 'Save locally', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('#status').textContent.startsWith('Saved'));
  const library = await page.evaluate(() => localStorage.getItem('aurora-local-lab:examples:v1'));
  const baseline = await page.evaluate(snapshot);
  const roofId=await page.evaluate(()=>{const r=window.engine.dataStore.findAllHeirs('roof')[0];return r.type==='roof'?r.id:null});
  if(roofId) {
    await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),roofId);
    await page.waitForTimeout(250);
    await page.evaluate(()=>window.engine.triggerAction('enterRoofIsolationMode'));
    await page.waitForFunction(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'));
  }
  const editingMode=await page.evaluate(()=>window.engine.subsystems.modeManager.actualStateMode);
  await edit();
  const edited = await page.evaluate(snapshot);
  assert.notDeepEqual(edited, baseline);
  const first = await draftAfter(null);
  assert.equal(await page.evaluate(()=>window.engine.subsystems.modeManager.actualStateMode),editingMode,'Idle draft must preserve editing mode');
  assert.equal(await page.evaluate(() => localStorage.getItem('aurora-local-lab:examples:v1')), library, 'Draft must not overwrite saved checkpoint');
  await page.getByRole('button', {name:'Undo',exact:true}).click();
  await page.waitForTimeout(600);
  assertSame(await page.evaluate(snapshot), baseline);
  const undoneDraft=await draftAfter(first.json);
  assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.canRedo),true,'Idle draft must preserve Redo');
  await page.getByRole('button',{name:'Redo',exact:true}).click();
  await page.waitForTimeout(500); assertSame(await page.evaluate(snapshot),edited);
  const redoneDraft=await draftAfter(undoneDraft.json);
  await page.getByRole('button',{name:'Undo',exact:true}).click();
  await page.waitForTimeout(500); assertSame(await page.evaluate(snapshot),baseline);
  await draftAfter(redoneDraft.json);
  await reload();
  assertSame(await page.evaluate(snapshot), baseline);
  assert.equal(await page.evaluate(() => window.lab.draftRestored), true);
  await edit();
  await page.getByLabel('Example name').fill('Recovered idle draft');
  const expected = await page.evaluate(snapshot);
  await page.waitForFunction(KEY => JSON.parse(sessionStorage.getItem(KEY)||'null')?.name === 'Recovered idle draft', KEY);
  let last = await page.evaluate(KEY => sessionStorage.getItem(KEY), KEY);
  const viewport = await page.locator('#viewport').boundingBox();
  await page.mouse.move(viewport.x + 15, viewport.y + 15);
  await page.mouse.down();
  await page.evaluate(() => { document.querySelector('#case-name').value = 'Pointer edit pending'; });
  await page.waitForTimeout(2000);
  assert.equal(await page.evaluate(KEY => sessionStorage.getItem(KEY), KEY), last, 'Pointer gesture must defer draft serialization');
  await page.mouse.up();
  await page.getByLabel('Example name').fill('Recovered idle draft');
  await page.waitForTimeout(1800);
  last = await page.evaluate(KEY => sessionStorage.getItem(KEY), KEY);
  await page.evaluate(() => window.labAPI.run('drawPitchedRoof'));
  await page.waitForTimeout(2000);
  assert.equal(await page.evaluate(KEY => sessionStorage.getItem(KEY), KEY), last, 'Active tool preview must not replace draft');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);
  await reload();
  assertSame(await page.evaluate(snapshot), expected);
  assert.equal(await page.getByLabel('Example name').inputValue(), 'Recovered idle draft');
  const restored = await page.evaluate(KEY => JSON.parse(sessionStorage.getItem(KEY)), KEY);
  assert.deepEqual(restored.importedFrom, first.importedFrom);
  await page.getByRole('button', { name: 'Save locally', exact: true }).click();
  await page.waitForFunction(KEY => !sessionStorage.getItem(KEY), KEY);
  await page.waitForTimeout(2000);
  assert.equal(await page.evaluate(KEY => sessionStorage.getItem(KEY), KEY), null, 'Save must not resurrect stale draft');
  await reload();
  assertSame(await page.evaluate(snapshot), expected);
  const savedId = await page.evaluate(() => sessionStorage.getItem('aurora-local-lab:active-example'));
  await page.evaluate(() => window.engine.triggerAction('selectEntitiesByIds', {
    entityIds: window.engine.dataStore.findAllHeirs('roof').map(r => r.id),
  }));
  await page.waitForTimeout(300);
  await page.locator('#viewport').focus();
  await page.keyboard.press('Delete');
  await page.waitForFunction(() => window.engine.dataStore.findAllHeirs('roof').length === 0);
  await draftAfter(null);
  await reload();
  assert.equal(await page.evaluate(() => window.engine.dataStore.findAllHeirs('roof').length), 0, 'Deleting last roof must survive refresh');
  await page.getByLabel('Saved examples').selectOption(savedId);
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}), page.getByRole('button', {name:'Reopen saved',exact:true}).click()]);
  await page.waitForFunction(() => window.lab?.stage === 'ready' && window.lab.tabDrafts, null, {timeout:30000});
  await page.waitForTimeout(500);
  assertSame(await page.evaluate(snapshot), expected);
  await page.evaluate(({previous,diagnostics}) => {
    for (const [key,value] of Object.entries(previous)) if (!['events','errors','blocked','originalUi','tabDrafts','draftRestored'].includes(key)) window.lab[key] = value;
    window.lab.errors.push(...diagnostics.errors); window.lab.blocked.push(...diagnostics.blocked);
    if (window.lab.originalUi) { window.lab.originalUi.errors.push(...diagnostics.uiErrors); window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries); }
    window.lab.draftRecoveryVerified = { refresh: true, editModeRetained:true, idleRedoRetained:true, undoBaseline: true, checkpointSeparate: true, previewDeferred: true, pointerDeferred: true, explicitSaveCleared: true, emptySceneRecovered: true, provenanceRetained: true };
  }, { previous, diagnostics });
}
module.exports = { runDraftChecks };
