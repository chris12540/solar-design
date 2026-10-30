const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
const EPS=1e-7;
function sameRing(a,b) {
  if(a.length!==b.length)return false;
  return b.some((_,start)=>[1,-1].some(direction=>a.every((p,i)=>p.every((v,axis)=>
    Math.abs(v-b[(start+direction*i+b.length)%b.length][axis])<=EPS))));
}
function matchedRings(actual,expected) {
  const remaining=[...actual];let matched=0;
  for(const ring of expected){const i=remaining.findIndex(candidate=>sameRing(candidate,ring));if(i>=0){remaining.splice(i,1);matched++;}}
  return {matched,missing:expected.length-matched,extra:remaining.length};
}
function assertRings(actual,expected,label) {
  assert.deepEqual(matchedRings(actual,expected),{matched:expected.length,missing:0,extra:0},label);
}
async function runRoofExplodeChecks(page) {
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith('default-site'));
  const initialEvidence=await page.evaluate(()=>({...window.lab}));
  const diagnostics={errors:[],blocked:[],uiErrors:[],queries:[]};
  async function collect() {
    const d=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,
      uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));
    for(const key of Object.keys(diagnostics))diagnostics[key].push(...d[key]);
  }
  const exported=()=>page.evaluate(async()=>{
    const {geometryFromNative}=await import('/case-export.js');const value=window.engine.bridge.makeDesignJsonToSave();
    return geometryFromNative(typeof value==='string'?JSON.parse(value):value);
  });
  const nativeRings=(geometry,key)=>geometry.buildings.flatMap(b=>key==='holes'?b.faces.flatMap(f=>f.holes||[]):b[key].map(f=>f.vertices));
  const stats=g=>({buildings:g.buildings.length,faces:g.buildings.reduce((n,b)=>n+b.faces.length,0),walls:g.buildings.reduce((n,b)=>n+b.walls.length,0),holes:nativeRings(g,'holes').length,holeTopologyComplete:g.holeTopologyComplete});
  const before=await page.evaluate(snapshot),exportBefore=await exported();
  assert.equal(before.roofs.length,1);assert.equal(before.roofs[0].type,'roof');
  const id=before.roofs[0].id;
  const sourceRings=[...before.roofs.flatMap(r=>r.faces),...before.dormers.flatMap(d=>d.faces)];
  const version=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
  const priorDraft=await page.evaluate(()=>sessionStorage.getItem('aurora-local-lab:tab-draft:v1'));
  await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);
  await page.getByRole('button',{name:'Explode',exact:true}).click();
  await page.waitForFunction(({id,version})=>!window.engine.dataStore.findAllHeirs('roof').some(r=>r.id===id)&&
    window.engine.state.data.historyData.recentVersion!==version,{id,version},{timeout:8000});
  await page.waitForTimeout(500);
  const after=await page.evaluate(snapshot),exportAfter=await exported();
  assert.equal(after.roofs.length,sourceRings.length,'Each source face must become an independent plane');
  assert.equal(after.dormers.length,0,'Dormers become planes, not retained parametric objects');
  for(const roof of after.roofs) {
    assert.equal(roof.type,'roof.plane');assert.equal(roof.faces.length,1);assert.equal(roof.folds.length,0);assert.ok(!roof.error);
    if(roof.valid!==undefined)assert.equal(roof.valid,true);
    if(roof.constructed!==undefined)assert.equal(roof.constructed,true);
    for(const face of roof.faces){assert.ok(face.length>=3);assert.ok(face.flat().every(Number.isFinite));}
  }
  assertRings(after.roofs.flatMap(r=>r.faces),sourceRings,'Source roof/dormer polygon coordinates must survive Explode');
  for(const key of ['faces','holes'])assertRings(nativeRings(exportAfter,key),nativeRings(exportBefore,key),`Explode must retain native roof ${key}`);
  const notification=await page.evaluate(()=>window.lab.notifications.at(-1));
  assert.match(notification.message,/explod/i);
  assert.ok((await page.locator('#status').textContent()).includes(notification.message));
  await page.getByRole('button',{name:'Undo',exact:true}).click();await page.waitForTimeout(500);
  assertSame(await page.evaluate(snapshot),before);
  assertRings(nativeRings(await exported(),'faces'),nativeRings(exportBefore,'faces'),'Undo must restore native roof polygons');
  assertRings(nativeRings(await exported(),'holes'),nativeRings(exportBefore,'holes'),'Undo must restore native holes');
  await page.getByRole('button',{name:'Redo',exact:true}).click();await page.waitForTimeout(500);
  assertSame(await page.evaluate(snapshot),after);
  await page.waitForFunction(previous=>{const value=sessionStorage.getItem('aurora-local-lab:tab-draft:v1');return value&&value!==previous},priorDraft,{timeout:6000});
  // A draft must describe the final redone state, not an earlier Undo snapshot.
  const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
  await page.waitForTimeout(1600);
  assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),revision);
  await collect();await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});
  await page.waitForTimeout(500);assert.equal(await page.evaluate(()=>window.lab.draftRestored),true);
  assertSame(await page.evaluate(snapshot),after);
  for(const key of ['faces','walls','holes'])assertRings(nativeRings(await exported(),key),nativeRings(exportAfter,key),`Draft must restore derived ${key}`);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));
  await collect();
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);
  await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});
  await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),after);
  for(const key of ['faces','walls','holes'])assertRings(nativeRings(await exported(),key),nativeRings(exportAfter,key),`Save must restore derived ${key}`);
  const metrics={before:stats(exportBefore),after:stats(exportAfter),
    visibleRoofRingMatches:matchedRings(nativeRings(exportAfter,'faces'),nativeRings(exportBefore,'faces')),
    holeRingMatches:matchedRings(nativeRings(exportAfter,'holes'),nativeRings(exportBefore,'holes')),
    wallRingMatches:matchedRings(nativeRings(exportAfter,'walls'),nativeRings(exportBefore,'walls')),
    sourceFaces:sourceRings.length,outputPlanes:after.roofs.length,oldDormers:before.dormers.length,oldFolds:before.roofs[0].folds.length};
  await page.evaluate(({initialEvidence,diagnostics,metrics,notification})=>{
    window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);
    window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);
    for(const key of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(initialEvidence[key])window.lab[key]=initialEvidence[key];
    window.lab.roofExplodeVerified={sourceFaceCoordinatesRetained:true,nativeRoofRingsRetained:true,parametricSourcesReplaced:true,undoRedo:true,draftRefresh:true,
      savedReopen:true,derivedGeometryStableAfterReopen:true,notification,metrics,toleranceMeters:1e-7};
  },{initialEvidence,diagnostics,metrics,notification});
}
module.exports={runRoofExplodeChecks};
