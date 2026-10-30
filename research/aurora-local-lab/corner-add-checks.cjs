const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
const normalized=value=>({...value,roofs:value.roofs.map(r=>({...r,walls:[...r.walls].sort((a,b)=>String(a.sourceId).localeCompare(String(b.sourceId)))}))});
const assertState=(a,b)=>assertSame(normalized(a),normalized(b));
const projectedArea=faces=>faces.reduce((sum,ring)=>sum+Math.abs(ring.reduce((v,p,i)=>{const q=ring[(i+1)%ring.length];return v+p[0]*q[1]-q[0]*p[1]},0))/2,0);
async function runCornerAddChecks(page){
  await page.getByRole('button',{name:'2D',exact:true}).click();await page.waitForTimeout(700);
  const before=await page.evaluate(snapshot),evidence=await page.evaluate(()=>({...window.lab})),roofId=before.roofs[0].id;
  if(!await page.evaluate(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'))){
    await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),roofId);
    await page.getByRole('button',{name:'Edit roof',exact:true}).click();await page.waitForTimeout(400);
  }
  const target=await page.evaluate(()=>{
    const r=window.engine.dataStore.findAllHeirs('roof')[0],e=r.perimeterEdges[0],[a,b]=e.nodes;
    const v=window.engine.viewportManager.getViewportByName('design-3d'),p=v.camerasThree.worldSpace.position.clone().set((a.x+b.x)/2,(a.y+b.y)/2,(a.z+b.z)/2);v.project(p);const rect=v.canvas.getBoundingClientRect();
    return{id:e.id,a:a.id,b:b.id,pitch:e.pitch,height:e.height,mid:[(a.x+b.x)/2,(a.y+b.y)/2],x:rect.left+p.x,y:rect.bottom-p.y};
  });
  await page.mouse.move(target.x,target.y,{steps:8});await page.mouse.click(target.x,target.y,{delay:100});
  if(before.dormers.length||before.roofs[0].folds.length){
    const button=page.getByRole('button',{name:'Add corner at midpoint',exact:true});
    await button.waitFor();assert.equal(await button.isDisabled(),true);
    const box=await button.boundingBox();await page.mouse.click(box.x+box.width/2,box.y+box.height/2);await page.waitForTimeout(250);assertState(await page.evaluate(snapshot),before);
    await page.evaluate(()=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes[0].id]}));
    await page.getByTestId('corner-angle').waitFor();assert.equal(await page.getByRole('button',{name:'Remove corner',exact:true}).isDisabled(),true);
    await page.evaluate(()=>window.lab.cornerAddVerified={blockedWithDetails:true,removeAlsoBlocked:true,geometryUnchanged:true});
    return;
  }
  await page.getByRole('button',{name:'Add corner at midpoint',exact:true}).click();await page.getByTestId('corner-angle').waitFor();await page.waitForTimeout(500);
  const inserted=await page.evaluate(snapshot);
  assert.equal(inserted.roofs[0].perimeter.length,before.roofs[0].perimeter.length+1);
  const added=await page.evaluate(({target})=>{
    const r=window.engine.dataStore.findAllHeirs('roof')[0],n=r.perimeterNodes.find(n=>Math.hypot(n.x-target.mid[0],n.y-target.mid[1])<1e-8);
    if(!n)return null;
    return{id:n.id,selected:window.engine.bridge.serializeSelection().some(s=>s.data.id===n.id),ends:n.edges.map(e=>({other:e.otherNode(n).id,height:e.height,pitch:e.pitch})),valid:r.isValid&&r.isConstructed&&r.isLoop&&!r.error};
  },{target});
  assert.ok(added?.valid&&added.selected);assert.equal(added.ends.length,2);
  assert.deepEqual(added.ends.map(e=>e.other).sort(),[target.a,target.b].sort());
  for(const e of added.ends){assert.equal(e.height,target.height);assert.equal(e.pitch,target.pitch);}
  for(const p of before.roofs[0].perimeter)assert.ok(inserted.roofs[0].perimeter.some(q=>Math.hypot(q[0]-p[0],q[1]-p[1])<1e-7));
  assert.ok(Math.abs(projectedArea(inserted.roofs[0].faces)-projectedArea(before.roofs[0].faces))<1e-7,'Midpoint insertion must keep roof projected area');
  for(const face of inserted.roofs[0].faces)for(const p of face){
    assert.ok(p.every(Number.isFinite));
    assert.ok(before.roofs[0].faces.some(ring=>{
      const a=ring[0];let normal;
      for(let i=1;i<ring.length-1;i++){const u=ring[i].map((v,k)=>v-a[k]),v=ring[i+1].map((v,k)=>v-a[k]);normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];if(Math.hypot(...normal)>1e-9)break;}
      return normal&&Math.abs(normal.reduce((sum,v,k)=>sum+v*(p[k]-a[k]),0))/Math.hypot(...normal)<1e-7;
    }),'Inserted roof vertex must stay on an original face plane');
  }
  await page.getByRole('button',{name:'Undo',exact:true}).click();await page.waitForTimeout(500);assertState(await page.evaluate(snapshot),before);
  await page.getByRole('button',{name:'Redo',exact:true}).click();await page.waitForTimeout(500);assertState(await page.evaluate(snapshot),inserted);
  // Drag the newly inserted point away from its edge: practical footprint editing.
  const drag=await page.evaluate(({id})=>{
    const n=window.engine.dataStore.find(id),[a,b]=n.edges.map(e=>e.otherNode(n)),r=n.roof;
    const center=r.perimeterNodes.reduce((p,q)=>({x:p.x+q.x/r.perimeterNodes.length,y:p.y+q.y/r.perimeterNodes.length}),{x:0,y:0});
    let dx=-(b.y-a.y),dy=b.x-a.x;const len=Math.hypot(dx,dy);dx/=len;dy/=len;if(dx*(n.x-center.x)+dy*(n.y-center.y)<0){dx=-dx;dy=-dy;}
    const v=window.engine.viewportManager.getViewportByName('design-3d'),rect=v.canvas.getBoundingClientRect();
    const project=(x,y)=>{const p=v.camerasThree.worldSpace.position.clone().set(x,y,n.z);v.project(p);return{x:rect.left+p.x,y:rect.bottom-p.y}};
    return{from:project(n.x,n.y),to:project(n.x+dx,n.y+dy),world:[n.x+dx,n.y+dy]};
  },{id:added.id});
  await page.mouse.move(drag.from.x,drag.from.y,{steps:8});await page.mouse.down();await page.waitForTimeout(80);await page.mouse.move(drag.to.x,drag.to.y,{steps:16});await page.mouse.up();await page.waitForTimeout(700);
  const shaped=await page.evaluate(snapshot),newPoint=await page.evaluate(id=>{const n=window.engine.dataStore.find(id);return[n.x,n.y]},added.id);
  assert.ok(Math.hypot(newPoint[0]-target.mid[0],newPoint[1]-target.mid[1])>0.2,'Inserted corner must move through real pointer drag');
  assert.ok(shaped.roofs[0].valid&&shaped.roofs[0].constructed&&!shaped.roofs[0].error);assert.equal(shaped.roofs[0].perimeter.length,inserted.roofs[0].perimeter.length);
  await page.getByRole('button',{name:'Undo',exact:true}).click();await page.waitForTimeout(500);assertState(await page.evaluate(snapshot),inserted);
  await page.getByRole('button',{name:'Redo',exact:true}).click();await page.waitForTimeout(500);assertState(await page.evaluate(snapshot),shaped);
  await page.waitForTimeout(1800);
  const diagnostics={errors:[],blocked:[],uiErrors:[],queries:[]};
  async function collect(){const d=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));for(const k of Object.keys(diagnostics))diagnostics[k].push(...d[k]);}
  await collect();await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);
  assert.equal(await page.evaluate(()=>window.lab.draftRestored),true);assertState(await page.evaluate(snapshot),shaped);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));await collect();
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);assertState(await page.evaluate(snapshot),shaped);
  await page.evaluate(({evidence,diagnostics,before,added})=>{
    window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);
    for(const k of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(evidence[k])window.lab[k]=evidence[k];
    window.lab.cornerAddVerified={before:before.roofs[0].perimeter.length,after:before.roofs[0].perimeter.length+1,pointerSelectedEdge:true,newCornerSelected:true,edgeParametersRetained:true,projectedAreaRetained:true,originalFacePlanes:true,draggedNewCorner:true,undoRedo:true,draftRefresh:true,savedReopen:true};
  },{evidence,diagnostics,before,added});
}
module.exports={runCornerAddChecks};
