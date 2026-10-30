const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
// Topology edits can recreate identical walls in a different registry order.
const normalized=value=>({...value,roofs:value.roofs.map(r=>({...r,walls:[...r.walls].sort((a,b)=>String(a.sourceId).localeCompare(String(b.sourceId)))}))});
const assertState=(a,b)=>assertSame(normalized(a),normalized(b));
async function runCornerRemoveChecks(page) {
  await page.getByRole('button',{name:'2D',exact:true}).click();await page.waitForTimeout(800);
  const before=await page.evaluate(snapshot),evidence=await page.evaluate(()=>({...window.lab})),roofId=before.roofs[0].id;
  async function editRoof(){if(!await page.evaluate(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'))){await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),roofId);await page.getByRole('button',{name:'Edit roof',exact:true}).click();await page.waitForFunction(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'));await page.waitForTimeout(350);}}
  await editRoof();
  const target=await page.evaluate(()=>{const roof=window.engine.dataStore.findAllHeirs('roof')[0],n=roof.perimeterNodes[0],v=window.engine.viewportManager.getViewportByName('design-3d'),p=v.camerasThree.worldSpace.position.clone().set(n.x,n.y,n.z);v.project(p);const r=v.canvas.getBoundingClientRect();return{id:n.id,count:roof.perimeterNodes.length,x:r.left+p.x,y:r.bottom-p.y}});
  await page.mouse.move(target.x,target.y,{steps:8});await page.mouse.click(target.x,target.y,{delay:100});await page.getByTestId('corner-angle').waitFor();
  const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
  await page.getByRole('button',{name:'Remove corner',exact:true}).click();
  await page.waitForFunction(({count,revision})=>window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes.length===count-1&&window.engine.state.data.historyData.recentVersion!==revision,{count:target.count,revision},{timeout:6000});await page.waitForTimeout(500);
  const removed=await page.evaluate(snapshot);
  assert.equal(await page.evaluate(id=>!!window.engine.dataStore.find(id),target.id),false);
  assert.ok(await page.evaluate(()=>{const r=window.engine.dataStore.findAllHeirs('roof')[0];return r.isLoop&&r.isValid&&!r.error}));
  assert.equal(removed.roofs[0].perimeter.length,before.roofs[0].perimeter.length-1);
  for(const p of removed.roofs[0].perimeter)assert.ok(before.roofs[0].perimeter.some(b=>Math.hypot(p[0]-b[0],p[1]-b[1])<1e-7),'Remaining corners must keep positions');
  for(const r of removed.roofs)for(const f of r.faces)assert.ok(f.flat().every(Number.isFinite));
  if(target.count===4){await page.getByTestId('corner-angle').waitFor();assert.equal(await page.getByRole('button',{name:'Remove corner',exact:true}).isDisabled(),true);}
  await page.getByRole('button',{name:'Undo',exact:true}).click();await page.waitForTimeout(500);assertState(await page.evaluate(snapshot),before);
  assert.equal(await page.evaluate(id=>!!window.engine.dataStore.find(id),target.id),true);
  await page.getByRole('button',{name:'Redo',exact:true}).click();await page.waitForTimeout(500);assertState(await page.evaluate(snapshot),removed);
  await page.waitForTimeout(1800);
  const diagnostics={errors:[],blocked:[],uiErrors:[],queries:[]};
  async function collect(){const d=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));for(const k of Object.keys(diagnostics))diagnostics[k].push(...d[k]);}
  await collect();await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);
  assert.equal(await page.evaluate(()=>window.lab.draftRestored),true);assertState(await page.evaluate(snapshot),removed);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));await collect();
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);assertState(await page.evaluate(snapshot),removed);
  await editRoof();await page.evaluate(()=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes[0].id]}));await page.getByTestId('corner-angle').waitFor();
  if(target.count===4)assert.equal(await page.getByRole('button',{name:'Remove corner',exact:true}).isDisabled(),true);
  await page.evaluate(({evidence,diagnostics,target})=>{
    window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);
    for(const k of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(evidence[k])window.lab[k]=evidence[k];
    window.lab.cornerRemoveVerified={before:target.count,after:target.count-1,pointerSelected:true,closedValidRoof:true,remainingCornersFixed:true,minimumThreeGuard:target.count===4,undoRedo:true,draftRefresh:true,savedReopen:true};
  },{evidence,diagnostics,target});
}
module.exports={runCornerRemoveChecks};
