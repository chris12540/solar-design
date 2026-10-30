const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
async function runPlaneEditChecks(page) {
  const initial=await page.evaluate(snapshot),evidence=await page.evaluate(()=>({...window.lab}));
  assert.ok(initial.roofs.length&&initial.roofs.every(r=>r.type==='roof.plane'),'Requires exploded source planes');
  await page.getByRole('button',{name:'2D',exact:true}).click();await page.waitForTimeout(800);
  const point=await page.evaluate(()=>{
    const planes=window.engine.dataStore.findAllHeirs('roof');
    const area=r=>Math.abs(r.faces[0].nodes.reduce((a,n,i)=>{const nodes=r.faces[0].nodes,p=nodes[(i+1)%nodes.length];return a+n.x*p.y-p.x*n.y},0));
    const face=[...planes].sort((a,b)=>area(b)-area(a))[0].faces[0];
    const center=face.nodes.reduce((p,n)=>({x:p.x+n.x/face.nodes.length,y:p.y+n.y/face.nodes.length,z:p.z+n.z/face.nodes.length}),{x:0,y:0,z:0});
    const view=window.engine.viewportManager.getViewportByName('design-3d'),v=view.camerasThree.worldSpace.position.clone().set(center.x,center.y,center.z);
    view.project(v);const rect=view.canvas.getBoundingClientRect();return {x:rect.left+v.x,y:rect.bottom-v.y};
  });
  await page.mouse.move(point.x,point.y,{steps:8});await page.waitForTimeout(150);await page.mouse.click(point.x,point.y,{delay:100});
  await page.waitForFunction(()=>window.engine.state.data.selectionData.roofPlanes.count===1);
  const id=await page.evaluate(()=>window.engine.bridge.serializeSelection().find(s=>s.type==='roof.plane').data.id);
  assert.ok(initial.roofs.some(r=>r.id===id),'Pointer must select an exploded plane');
  const diagnostics={errors:[],blocked:[],uiErrors:[],queries:[]};
  async function collect() {
    const d=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));
    for(const key of Object.keys(diagnostics))diagnostics[key].push(...d[key]);
  }
  async function select() {
    await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);
    await page.getByTestId('roofPlanes-height').waitFor();
  }
  async function edit(field,value) {
    await select();const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
    await page.getByTestId(field).fill(String(value));await page.getByTestId(field).blur();
    await page.waitForFunction(revision=>window.engine.state.data.historyData.recentVersion!==revision,revision,{timeout:6000});
    await page.waitForTimeout(350);
  }
  const target=v=>v.roofs.find(r=>r.id===id);
  const others=v=>v.roofs.filter(r=>r.id!==id);
  function verifyIndependent(current) {
    assert.equal(current.roofs.length,initial.roofs.length);assertSame(others(current),others(initial),'Other source planes must remain unchanged');
    for(const roof of current.roofs)for(const face of roof.faces){assert.ok(face.length>=3);assert.ok(face.flat().every(Number.isFinite));assert.ok(!roof.error);}
  }
  async function history(action,expected) {
    await page.getByRole('button',{name:action,exact:true}).click();await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),expected);
  }
  await select();
  const height=Number(await page.getByTestId('roofPlanes-height').inputValue());assert.ok(Number.isFinite(height));
  const originalHeight=await page.evaluate(id=>window.engine.dataStore.find(id).height,id);
  const heightDelta=height+0.4-originalHeight;
  await edit('roofPlanes-height',height+0.4);
  const raised=await page.evaluate(snapshot);verifyIndependent(raised);
  assertSame(target(raised).perimeter,target(initial).perimeter);
  for(let j=0;j<target(initial).faces.length;j++)for(let k=0;k<target(initial).faces[j].length;k++) {
    const p=target(initial).faces[j][k];assertSame(target(raised).faces[j][k],[p[0],p[1],p[2]+heightDelta],'Selected face height');
  }
  await history('Undo',initial);await history('Redo',raised);
  await select();
  const pitch=Number(await page.getByTestId('roofPlanes-pitchProxy').inputValue());assert.ok(Number.isFinite(pitch));
  const nextPitch=pitch<80?pitch+5:pitch-5;
  await edit('roofPlanes-pitchProxy',nextPitch);
  const tilted=await page.evaluate(snapshot);verifyIndependent(tilted);
  assert.notDeepEqual(target(tilted).faces,target(raised).faces,'Pitch must change selected plane geometry');
  await history('Undo',raised);await history('Redo',tilted);
  await select();assert.ok(Math.abs(Number(await page.getByTestId('roofPlanes-pitchProxy').inputValue())-nextPitch)<1e-7);
  const expectedHeight=Number(await page.getByTestId('roofPlanes-height').inputValue());
  await page.waitForTimeout(1800);
  await collect();await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);
  assert.equal(await page.evaluate(()=>window.lab.draftRestored),true);assertSame(await page.evaluate(snapshot),tilted);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));
  await collect();
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);
  await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);
  assertSame(await page.evaluate(snapshot),tilted);
  await select();assert.equal(Number(await page.getByTestId('roofPlanes-height').inputValue()),expectedHeight);
  assert.ok(Math.abs(Number(await page.getByTestId('roofPlanes-pitchProxy').inputValue())-nextPitch)<1e-7);
  await page.evaluate(({evidence,diagnostics,id,nextPitch})=>{
    window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);
    window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);
    for(const key of ['interactionCase','drawingEvidence','dragEvidence','roundTrip','roofExplodeVerified'])if(evidence[key])window.lab[key]=evidence[key];
    window.lab.planeEditVerified={id,nextPitch,planeCount:window.engine.dataStore.findAllHeirs('roof').length,
      pointerSelected:true,heightGeometry:true,pitchGeometry:true,fieldsRetained:true,otherSourcesUnchanged:true,undoRedo:true,draftRefresh:true,savedReopen:true,toleranceMeters:1e-7};
  },{evidence,diagnostics,id,nextPitch});
}
module.exports={runPlaneEditChecks};
