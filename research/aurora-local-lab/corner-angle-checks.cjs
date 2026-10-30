const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
async function runCornerAngleChecks(page,{inner=false}={}) {
  await page.getByRole('button',{name:'2D',exact:true}).click();await page.waitForTimeout(800);
  const initial=await page.evaluate(snapshot),evidence=await page.evaluate(()=>({...window.lab}));
  assert.equal(initial.roofs[0].type,'roof');const roofId=initial.roofs[0].id;
  async function enterEdit() {
    if(!await page.evaluate(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'))) {
      await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),roofId);
      await page.getByRole('button',{name:'Edit roof',exact:true}).click();
      await page.waitForFunction(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'));
    }
  }
  await enterEdit();
  // Existing native Length control is a usable precision input; do not duplicate it.
  const edge=await page.evaluate(()=>{const e=window.engine.dataStore.findAllHeirs('roof')[0].perimeterEdges[0];return{id:e.id,length:e.length}});
  await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),edge.id);
  await page.getByTestId('perimeterEdges-length').fill(String(edge.length+0.5));await page.getByTestId('perimeterEdges-length').blur();
  await page.waitForFunction(({id,length})=>Math.abs(window.engine.dataStore.find(id).length-length)<1e-7,{id:edge.id,length:edge.length+0.5});
  await page.getByRole('button',{name:'Undo',exact:true}).click();await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),initial);
  await enterEdit();await page.waitForTimeout(400);
  console.log('Corner source angles',await page.evaluate(()=>window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes.map(n=>n.angle)));
  const nodeInfo=await page.evaluate(inner=>{
    const list=window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes;
    const signed=list.reduce((a,p,i)=>{const q=list[(i+1)%list.length];return a+p.x*q.y-q.x*p.y},0);
    const n=inner?list.find((p,i)=>{const a=list[(i+list.length-1)%list.length],b=list[(i+1)%list.length];return ((p.x-a.x)*(b.y-p.y)-(p.y-a.y)*(b.x-p.x))*signed<0}):list[0];
    if(!n)throw Error('Fixture has no concave corner');
    const neighbors=[...new Set(n.edges.flatMap(e=>e.nodes).filter(p=>p!==n))],vectors=neighbors.map(p=>({x:p.x-n.x,y:p.y-n.y})),[a,b]=vectors;
    const angle=Math.atan2(Math.abs(a.x*b.y-a.y*b.x),a.x*b.x+a.y*b.y)*180/Math.PI;
    const v=window.engine.viewportManager.getViewportByName('design-3d'),p=v.camerasThree.worldSpace.position.clone().set(n.x,n.y,n.z);v.project(p);const r=v.canvas.getBoundingClientRect();
    return{id:n.id,angle,x:r.left+p.x,y:r.bottom-p.y,neighbors:neighbors.map(p=>p.id)};
  },inner);
  await page.mouse.move(nodeInfo.x,nodeInfo.y,{steps:8});await page.mouse.click(nodeInfo.x,nodeInfo.y,{delay:100});
  await page.getByTestId('corner-angle').waitFor();
  const id=nodeInfo.id,target=nodeInfo.angle<170?nodeInfo.angle+5.123:nodeInfo.angle-5.123;
  const nodes=()=>page.evaluate(()=>window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes.map(n=>({id:n.id,x:n.x,y:n.y})));
  const beforeNodes=await nodes();
  async function select(){await enterEdit();await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);await page.getByTestId('corner-angle').waitFor();}
  async function apply(opposite) {
    await select();await page.getByLabel('Move opposite adjacent corner').setChecked(opposite);
    const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
    await page.getByTestId('corner-angle').fill(String(target));await page.getByRole('button',{name:'Apply angle',exact:true}).click();
    await page.waitForFunction(({id,target,revision})=>{
      const n=window.engine.dataStore.find(id),[a,b]=n.edges.map(e=>{const p=e.nodes.find(p=>p!==n);return{x:p.x-n.x,y:p.y-n.y}});
      const measured=Math.atan2(Math.abs(a.x*b.y-a.y*b.x),a.x*b.x+a.y*b.y)*180/Math.PI;
      return Math.abs(measured-target)<1e-7&&window.engine.state.data.historyData.recentVersion!==revision;
    },{id,target,revision},{timeout:5000});
    await page.waitForTimeout(350);
    const current=await nodes(),selected=current.find(n=>n.id===id);assertSame(selected,beforeNodes.find(n=>n.id===id),'Selected corner must stay fixed');
    const changed=current.filter(n=>{const b=beforeNodes.find(b=>b.id===n.id);return Math.hypot(n.x-b.x,n.y-b.y)>1e-7});
    assert.equal(changed.length,1);assert.ok(nodeInfo.neighbors.includes(changed[0].id));
    const vectors=nodeInfo.neighbors.map(nid=>{const n=current.find(n=>n.id===nid);return{x:n.x-selected.x,y:n.y-selected.y}}),[a,b]=vectors;
    const measured=Math.atan2(Math.abs(a.x*b.y-a.y*b.x),a.x*b.x+a.y*b.y)*180/Math.PI;
    assert.ok(Math.abs(measured-target)<1e-7,'Geometry must match requested plan angle');
    assert.ok(await page.evaluate(()=>window.engine.dataStore.findAllHeirs('roof')[0].isValid));
    const state=await page.evaluate(snapshot);assertSame(state.roofs[0].edges,initial.roofs[0].edges,'Source height/pitch must stay fixed');
    for(const r of state.roofs)for(const f of r.faces)assert.ok(f.flat().every(Number.isFinite));
    return {state,movedId:changed[0].id};
  }
  async function history(action,expected){
    await page.getByRole('button',{name:action,exact:true}).click();await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),expected);
    await select();await page.waitForTimeout(200);
    const expectedAngle=expected===initial?nodeInfo.angle:target;
    assert.ok(Math.abs(Number(await page.getByTestId('corner-angle').inputValue())-expectedAngle)<0.005,'Inspector must reflect Undo/Redo geometry');
  }
  const first=await apply(false);await history('Undo',initial);await history('Redo',first.state);await history('Undo',initial);
  const second=await apply(true);assert.notEqual(second.movedId,first.movedId,'Opposite-side option must move other neighbor');
  await history('Undo',initial);await history('Redo',second.state);
  await select();
  const unchangedRevision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
  await page.getByRole('button',{name:'Apply angle',exact:true}).click();await page.waitForTimeout(300);
  assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),unchangedRevision,'Unchanged angle must not add history');
  await page.getByTestId('corner-angle').fill('181');await page.getByRole('button',{name:'Apply angle',exact:true}).click();
  assert.equal(await page.getByTestId('corner-angle').evaluate(n=>n.checkValidity()),false);
  await page.waitForTimeout(300);assertSame(await page.evaluate(snapshot),second.state);
  assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),unchangedRevision);
  await page.getByTestId('corner-angle').fill(String(target));await page.waitForTimeout(1800);
  const diagnostics={errors:[],blocked:[],uiErrors:[],queries:[]};
  async function collect(){const d=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));for(const k of Object.keys(diagnostics))diagnostics[k].push(...d[k]);}
  await collect();await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);
  assert.equal(await page.evaluate(()=>window.lab.draftRestored),true);assertSame(await page.evaluate(snapshot),second.state);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));await collect();
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);
  await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),second.state);
  await enterEdit();await select();assert.ok(Math.abs(Number(await page.getByTestId('corner-angle').inputValue())-target)<0.005);
  await page.evaluate(({evidence,diagnostics,target,inner})=>{
    window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);
    for(const k of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(evidence[k])window.lab[k]=evidence[k];
    window.lab.cornerAngleVerified={target,innerCorner:inner,pointerSelected:true,existingLengthInput:true,selectedCornerFixed:true,oppositeSide:true,invalidInputBlocked:true,undoRedo:true,draftRefresh:true,savedReopen:true,fractionalAngle:true,unchangedApplyNoHistory:true};
  },{evidence,diagnostics,target,inner});
}
module.exports={runCornerAngleChecks};
