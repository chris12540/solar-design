const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
async function runEdgeLengthChecks(page){
  await page.getByRole('button',{name:'2D',exact:true}).click();await page.waitForTimeout(700);
  const initial=await page.evaluate(snapshot),evidence=await page.evaluate(()=>({...window.lab})),roofId=initial.roofs[0].id;
  async function edit(){if(!await page.evaluate(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'))){await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),roofId);await page.getByRole('button',{name:'Edit roof',exact:true}).click();await page.waitForTimeout(400);}}
  await edit();
  const target=await page.evaluate(()=>{
    const r=window.engine.dataStore.findAllHeirs('roof')[0],e=r.perimeterEdges[0],[a,b]=e.nodes,v=window.engine.viewportManager.getViewportByName('design-3d'),p=v.camerasThree.worldSpace.position.clone().set((a.x+b.x)/2,(a.y+b.y)/2,(a.z+b.z)/2);v.project(p);const rect=v.canvas.getBoundingClientRect();
    return{id:e.id,length:e.length,endIds:e.nodes.map(n=>n.id),nodes:r.perimeterNodes.map(n=>({id:n.id,x:n.x,y:n.y})),x:rect.left+p.x,y:rect.bottom-p.y};
  });
  await page.mouse.move(target.x,target.y,{steps:8});await page.mouse.click(target.x,target.y,{delay:100});
  const input=page.getByRole('spinbutton',{name:'Roof edge length in meters',exact:true});await input.waitFor();
  async function select(){await edit();await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),target.id);await input.waitFor();}
  async function history(name,expected){await page.getByRole('button',{name,exact:true}).click();await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),expected);}
  const desired=target.length+1.2345,results=[];
  assert.equal(await input.getAttribute('aria-describedby'),'local-edge-length-help');
  for(const anchor of ['anchorLeft','anchorRight']){
    await select();await page.getByRole('button',{name:anchor==='anchorLeft'?'Keep second corner fixed':'Keep first corner fixed',exact:true}).click();
    const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
    await input.fill(String(desired));await input.blur();
    await page.waitForFunction(({id,desired,revision})=>Math.abs(window.engine.dataStore.find(id).length-desired)<1e-7&&window.engine.state.data.historyData.recentVersion!==revision,{id:target.id,desired,revision},{timeout:6000});await page.waitForTimeout(300);
    const state=await page.evaluate(snapshot),nodes=await page.evaluate(()=>window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes.map(n=>({id:n.id,x:n.x,y:n.y})));
    const changed=nodes.filter(n=>{const b=target.nodes.find(b=>b.id===n.id);return Math.hypot(n.x-b.x,n.y-b.y)>1e-7});
    assert.equal(changed.length,1,'Exactly one endpoint must move');assert.ok(target.endIds.includes(changed[0].id));
    assert.equal(changed[0].id,target.endIds[anchor==='anchorLeft'?0:1],'Endpoint label must match native motion');
    const beforePoint=target.nodes.find(n=>n.id===changed[0].id),other=target.nodes.find(n=>target.endIds.includes(n.id)&&n.id!==beforePoint.id),dx=beforePoint.x-other.x,dy=beforePoint.y-other.y;
    const expected={...beforePoint,x:other.x+dx*desired/target.length,y:other.y+dy*desired/target.length};assertSame(changed[0],expected,'Endpoint must move along original edge');
    assert.ok(state.roofs[0].valid&&state.roofs[0].constructed&&!state.roofs[0].error);assertSame(state.roofs[0].edges,initial.roofs[0].edges,'Source pitches/heights stay fixed');
    for(const r of state.roofs)for(const face of r.faces)assert.ok(face.flat().every(Number.isFinite));
    results.push({anchor,movedId:changed[0].id,fixedId:other.id,state});
    await history('Undo',initial);await history('Redo',state);
    await select();assert.ok(Math.abs(Number(await input.inputValue())-desired)<=0.005,'Length display must match geometry within rounding');
    if(anchor==='anchorLeft')await history('Undo',initial);
  }
  assert.notEqual(results[0].movedId,results[1].movedId,'Arrow choices must move different endpoints');
  const final=results[1].state;
  await select();const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
  await input.focus();await input.blur();await page.waitForTimeout(1300);
  assertSame(await page.evaluate(snapshot),final,'Untouched blur must not round source geometry');
  assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),revision,'Untouched field must not add history');
  await page.waitForTimeout(1800);
  const diagnostics={errors:[],blocked:[],uiErrors:[],queries:[]};
  async function collect(){const d=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));for(const k of Object.keys(diagnostics))diagnostics[k].push(...d[k]);}
  await collect();await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);assert.equal(await page.evaluate(()=>window.lab.draftRestored),true);assertSame(await page.evaluate(snapshot),final);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));await collect();
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),final);await select();assert.ok(Math.abs(Number(await input.inputValue())-desired)<=0.005);
  await page.evaluate(({evidence,diagnostics,desired,results})=>{
    window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);
    for(const k of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(evidence[k])window.lab[k]=evidence[k];
    window.lab.edgeLengthVerified={desired,pointerSelected:true,anchors:results.map(({anchor,movedId,fixedId})=>({anchor,movedId,fixedId})),oneEndpointAlongEdge:true,otherNodesFixed:true,sourcePitchHeightRetained:true,untouchedBlurNoHistory:true,undoRedo:true,draftRefresh:true,savedReopen:true};
  },{evidence,diagnostics,desired,results});
}
module.exports={runEdgeLengthChecks};
