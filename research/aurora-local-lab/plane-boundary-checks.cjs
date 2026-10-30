const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
const area=ring=>Math.abs(ring.reduce((a,p,i)=>{const q=ring[(i+1)%ring.length];return a+p[0]*q[1]-q[0]*p[1]},0))/2;
async function runPlaneBoundaryChecks(page,{corner=false}={}) {
  await page.getByRole('button',{name:'2D',exact:true}).click();await page.waitForTimeout(800);
  const before=await page.evaluate(snapshot),evidence=await page.evaluate(()=>({...window.lab}));
  assert.ok(before.roofs.every(r=>r.type==='roof.plane'));
  const selected=[...before.roofs].sort((a,b)=>area(b.perimeter)-area(a.perimeter))[0],id=selected.id;
  await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);
  await page.getByTestId('roofPlanes-height').waitFor();
  const pitch=await page.evaluate(id=>window.engine.dataStore.find(id).pitch,id);
  const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
  const drag=await page.evaluate(({id,corner})=>{
    const r=window.engine.dataStore.find(id),v=window.engine.viewportManager.getViewportByName('design-3d'),rect=v.canvas.getBoundingClientRect();
    const points=r.faces[0].nodes.map(n=>{const p=v.camerasThree.worldSpace.position.clone().set(n.x,n.y,n.z);v.project(p);return{x:rect.left+p.x,y:rect.bottom-p.y}});
    if(corner){const p=[...points].sort((a,b)=>b.x-a.x)[0],c=points.reduce((c,p)=>({x:c.x+p.x/points.length,y:c.y+p.y/points.length}),{x:0,y:0}),len=Math.hypot(p.x-c.x,p.y-c.y);return{x:p.x,y:p.y,dx:(p.x-c.x)/len*30,dy:(p.y-c.y)/len*30};}
    const edges=points.map((a,i)=>({a,b:points[(i+1)%points.length]})).sort((a,b)=>Math.hypot(b.b.x-b.a.x,b.b.y-b.a.y)-Math.hypot(a.b.x-a.a.x,a.b.y-a.a.y));
    const {a,b}=edges[0],len=Math.hypot(b.x-a.x,b.y-a.y),signed=points.reduce((n,p,i)=>{const q=points[(i+1)%points.length];return n+p.x*q.y-q.x*p.y},0),direction=signed>0?1:-1;
    return {x:(a.x+b.x)/2,y:(a.y+b.y)/2,dx:(b.y-a.y)/len*35*direction,dy:-(b.x-a.x)/len*35*direction};
  },{id,corner});
  await page.mouse.move(drag.x,drag.y,{steps:8});await page.waitForTimeout(200);
  const hover=await page.evaluate(()=>window.engine.subsystems.inputManager.hoverEntity?.tag);
  await page.mouse.down();await page.waitForTimeout(100);await page.mouse.move(drag.x+drag.dx,drag.y+drag.dy,{steps:15});await page.waitForTimeout(200);await page.mouse.up();
  await page.waitForFunction(revision=>window.engine.state.data.historyData.recentVersion!==revision,revision,{timeout:6000});await page.waitForTimeout(350);
  const after=await page.evaluate(snapshot),changed=after.roofs.find(r=>r.id===id);
  assertSame(after.roofs.filter(r=>r.id!==id),before.roofs.filter(r=>r.id!==id),'Other source planes must not change');
  assert.equal(changed.perimeter.length,selected.perimeter.length);
  assert.ok(area(changed.perimeter)>area(selected.perimeter)+0.001,'Outward handle drag must enlarge selected outline');
  assert.ok(selected.perimeter.some(p=>changed.perimeter.some(q=>Math.hypot(p[0]-q[0],p[1]-q[1])<1e-7)),'Reshape must retain a stationary vertex');
  assert.ok(await page.evaluate(id=>window.engine.dataStore.find(id).isValid,id));
  for(const f of changed.faces)assert.ok(f.flat().every(Number.isFinite));
  if(Number.isFinite(pitch))assert.ok(Math.abs(await page.evaluate(id=>window.engine.dataStore.find(id).pitch,id)-pitch)<1e-7);
  await page.getByRole('button',{name:'Undo',exact:true}).click();await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),before);
  await page.getByRole('button',{name:'Redo',exact:true}).click();await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),after);
  await page.waitForTimeout(1800);
  const diagnostics=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));
  await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);
  assert.equal(await page.evaluate(()=>window.lab.draftRestored),true);assertSame(await page.evaluate(snapshot),after);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));
  const d=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));
  for(const key of Object.keys(diagnostics))diagnostics[key].push(...d[key]);
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);
  await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),after);
  await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);await page.getByTestId('roofPlanes-height').waitFor();
  await page.evaluate(({evidence,diagnostics,corner,hover})=>{
    window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);
    window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);
    for(const key of ['interactionCase','drawingEvidence','dragEvidence','roundTrip','roofExplodeVerified'])if(evidence[key])window.lab[key]=evidence[key];
    window.lab.planeBoundaryVerified={kind:corner?'corner':'edge',hover,outlineReshaped:true,otherSourcesUnchanged:true,valid:true,undoRedo:true,draftRefresh:true,savedReopen:true,toleranceMeters:1e-7};
  },{evidence,diagnostics,corner,hover});
}
module.exports={runPlaneBoundaryChecks};
