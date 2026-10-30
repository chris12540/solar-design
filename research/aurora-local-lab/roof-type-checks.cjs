const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
async function runRoofTypeChecks(page) {
  const before=await page.evaluate(snapshot);
  assert.equal(before.roofs.length,1,'Conversion fixture requires one roof');
  const id=before.roofs[0].id;
  const diagnostics={errors:[],blocked:[],uiErrors:[],queries:[]};
  const evidence=await page.evaluate(()=>({...window.lab}));
  async function select() {
    await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);
    await page.getByTestId('roofs-height').waitFor();
  }
  async function convert(kind) {
    await select();
    const version=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
    await page.locator(`#original-inspector-root button[data-key="${kind}"]`).click();
    await page.waitForFunction(({version,flat})=>{
      const roof=window.engine.dataStore.findAllHeirs('roof')[0];
      return roof.inFlatMode===flat && window.engine.state.data.historyData.recentVersion!==version;
    },{version,flat:kind==='flat'},{timeout:8000});
    await page.waitForTimeout(400);
    await select();
    await page.locator(`#original-inspector-root button[data-key="${kind}"][aria-pressed="true"]`).waitFor();
    const value=await page.evaluate(snapshot);
    assertSame(value.roofs[0].perimeter,before.roofs[0].perimeter,'conversion footprint');
    for(const r of value.roofs) {
      assert.equal(r.valid,true);assert.equal(r.constructed,true);assert.ok(!r.error);
      assert.ok(r.faces.length>0);
    }
    for(const object of [...value.roofs,...value.dormers])for(const face of [...object.faces,...(object.walls||[]).map(w=>w.nodes)]) {
      assert.ok(face.length>=3);assert.ok(face.flat().every(Number.isFinite));
    }
    return value;
  }
  async function history(action,expected) {
    await page.getByRole('button',{name:action,exact:true}).click();
    await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),expected);
  }
  async function reopen(expected,flat) {
    await page.getByRole('button',{name:'Save locally',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));
    const d=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,
      uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));
    for(const key of Object.keys(diagnostics))diagnostics[key].push(...d[key]);
    await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);
    await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});
    await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),expected);
    assert.equal(await page.evaluate(()=>window.engine.dataStore.findAllHeirs('roof')[0].inFlatMode),flat);
  }
  if(before.dormers.length || before.roofs[0].folds.length) {
    await select();
    const history=await page.evaluate(()=>({...window.engine.state.data.historyData}));
    const count=await page.evaluate(()=>window.lab.notifications.length);
    await page.locator('#original-inspector-root button[data-key="flat"]').click();
    await page.waitForFunction(count=>window.lab.notifications.length>count,count);
    const notification=await page.evaluate(()=>window.lab.notifications.at(-1));
    assert.match(notification.message,before.dormers.length?/dormer/i:/fold|kink/i);
    assert.ok((await page.locator('#status').textContent()).includes(notification.message),'Refusal must be visible');
    await page.waitForTimeout(1400);
    assertSame(await page.evaluate(snapshot),before,'rejected conversion');
    assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),history.recentVersion,'Rejected conversion must not add history');
    await reopen(before,false);
    await page.evaluate(({evidence,diagnostics,notification})=>{
      window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);
      window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);
      for(const key of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(evidence[key])window.lab[key]=evidence[key];
      window.lab.roofTypeVerified={detailsRejected:true,notificationVisible:true,geometryUnchanged:true,noHistoryAdded:true,reopen:true,notification};
    },{evidence,diagnostics,notification});
    return;
  }
  const flat=await convert('flat');
  if(!before.dormers.length&&!before.roofs[0].folds.length) {
    assert.equal(flat.roofs[0].faces.length,1,'Plain flat roof must have one face');
    const heights=flat.roofs[0].faces[0].map(n=>n[2]);
    assert.ok(Math.max(...heights)-Math.min(...heights)<1e-7,'Plain flat roof must be horizontal');
  }
  await history('Undo',before);await history('Redo',flat);
  await reopen(flat,true);
  const pitched=await convert('pitched');
  if(!pitched.dormers.length&&!pitched.roofs[0].folds.length) {
    const z=pitched.roofs[0].faces.flat().map(n=>n[2]);
    assert.ok(Math.max(...z)-Math.min(...z)>1e-3,'Pitched conversion must create elevation variation');
  }
  await history('Undo',flat);await history('Redo',pitched);
  await reopen(pitched,false);
  const counts=value=>({faces:value.roofs[0].faces.length,folds:value.roofs[0].folds.length,dormers:value.dormers.length});
  await page.evaluate(({evidence,diagnostics,counts})=>{
    window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);
    window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);
    for(const key of ['interactionCase','drawingEvidence','dragEvidence','roundTrip','caseImportVerified','caseExportVerified','roofPropertiesVerified'])if(evidence[key])window.lab[key]=evidence[key];
    window.lab.roofTypeVerified={flat:true,pitched:true,footprintPreserved:true,undoRedo:true,reopenBoth:true,counts,toleranceMeters:1e-7};
  },{evidence,diagnostics,counts:{before:counts(before),flat:counts(flat),pitched:counts(pitched)}});
}
module.exports={runRoofTypeChecks};
