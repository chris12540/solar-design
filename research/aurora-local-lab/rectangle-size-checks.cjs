const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
async function runRectangleSizeChecks(page,{rotated=false}={}){
  await page.keyboard.press('Escape');await page.waitForTimeout(300);
  const evidence=await page.evaluate(()=>({...window.lab})),initial=await page.evaluate(snapshot),id=initial.roofs[0].id;
  async function select(){await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);await page.getByRole('button',{name:'Resize rectangle',exact:true}).waitFor();}
  await select();const apply=page.getByRole('button',{name:'Resize rectangle',exact:true}),widthInput=page.getByLabel('Rectangle footprint width',{exact:true}),depthInput=page.getByLabel('Rectangle footprint depth',{exact:true});
  if(initial.dormers.length||initial.roofs[0].folds.length||initial.roofs[0].perimeter.length!==4){
    assert.equal(await apply.isDisabled(),true);assert.equal(await widthInput.isDisabled(),true);assert.equal(await depthInput.isDisabled(),true);const b=await apply.boundingBox();await page.mouse.click(b.x+b.width/2,b.y+b.height/2);await page.waitForTimeout(250);assertSame(await page.evaluate(snapshot),initial);await page.evaluate(()=>window.lab.rectangleSizeVerified={unsupportedGuard:true,geometryUnchanged:true});return;
  }
  const flat=initial.roofs[0].edges.every(e=>e.pitch===90);
  if(!flat){await page.getByLabel('Roof starter shape',{exact:true}).selectOption('gable');await page.getByLabel('Roof starter pitch',{exact:true}).fill('30');await page.getByRole('button',{name:'Apply roof starter',exact:true}).click();await page.waitForFunction(()=>window.engine.dataStore.findAllHeirs('roof')[0].faces.length===2);await page.waitForTimeout(400);}
  if(rotated){
    // Synthetic fixture rotation via native source setters; not a rotation-UI test.
    await page.evaluate(()=>{const e=window.engine,r=e.dataStore.findAllHeirs('roof')[0],nodes=r.perimeterNodes,c=nodes.reduce((p,n)=>({x:p.x+n.x/4,y:p.y+n.y/4}),{x:0,y:0}),angle=37*Math.PI/180,points=nodes.map(n=>{const x=n.x-c.x,y=n.y-c.y;return{n,x:c.x+x*Math.cos(angle)-y*Math.sin(angle),y:c.y+x*Math.sin(angle)+y*Math.cos(angle)}});for(const p of points){p.n.x=p.x;p.n.y=p.y}e.dataStore.commit()});await page.waitForTimeout(500);
  }
  const measure=()=>page.evaluate(()=>{const r=window.engine.dataStore.findAllHeirs('roof')[0],e=r.perimeterEdges[0],[a,b]=e.nodes,d=a.edges.find(x=>x!==e).otherNode(a),width=Math.hypot(b.x-a.x,b.y-a.y),depth=Math.hypot(d.x-a.x,d.y-a.y);return{width,depth,u:[(b.x-a.x)/width,(b.y-a.y)/width],v:[(d.x-a.x)/depth,(d.y-a.y)/depth],center:r.perimeterNodes.reduce((p,n)=>[p[0]+n.x/4,p[1]+n.y/4],[0,0]),ids:r.perimeterNodes.map(n=>n.id)}});
  const before=await page.evaluate(snapshot),basis=await measure();await page.waitForFunction(()=>!!document.querySelector('[aria-label="Rectangle footprint width"]')?.value);
  const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);await apply.click();await page.waitForTimeout(350);assertSame(await page.evaluate(snapshot),before);assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),revision);
  async function verify(w,d){
    const m=await measure(),s=await page.evaluate(snapshot);assert.ok(Math.abs(m.width-w)<1e-7&&Math.abs(m.depth-d)<1e-7);assertSame(m.center,basis.center,'Center stays fixed');assertSame(m.u,basis.u,'Width orientation stays fixed');assertSame(m.v,basis.v,'Depth orientation stays fixed');assert.deepEqual(m.ids,basis.ids);assertSame(s.roofs[0].edges,before.roofs[0].edges,'Source pitches/heights/edge IDs stay fixed');assert.equal(s.roofs[0].faces.length,flat?1:2);assert.ok(s.roofs[0].valid&&s.roofs[0].constructed&&!s.roofs[0].error);for(const f of s.roofs[0].faces)assert.ok(f.flat().every(Number.isFinite));return s;
  }
  async function submit(){const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);await apply.click();await page.waitForFunction(revision=>window.engine.state.data.historyData.recentVersion!==revision,revision,{timeout:6000});await page.waitForTimeout(450);}
  const w=31.123456,d=17.654321;
  await widthInput.fill(String(w));await submit();const oneAxis=await verify(w,basis.depth);
  await page.getByRole('button',{name:'Undo',exact:true}).click();await page.waitForTimeout(450);assertSame(await page.evaluate(snapshot),before);
  await page.getByRole('button',{name:'Redo',exact:true}).click();await page.waitForTimeout(450);assertSame(await page.evaluate(snapshot),oneAxis);
  // Width display rounds, but editing only Depth must retain exact Width.
  await depthInput.fill(String(d));await submit();const complete=await verify(w,d);
  await page.getByRole('button',{name:'Undo',exact:true}).click();await page.waitForTimeout(450);assertSame(await page.evaluate(snapshot),oneAxis);
  await page.getByRole('button',{name:'Redo',exact:true}).click();await page.waitForTimeout(450);assertSame(await page.evaluate(snapshot),complete);
  const finalRevision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);await apply.click();await page.waitForTimeout(350);assertSame(await page.evaluate(snapshot),complete);assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),finalRevision);
  await widthInput.fill('0.01');await apply.click();assert.equal(await widthInput.evaluate(n=>n.checkValidity()),false);assertSame(await page.evaluate(snapshot),complete);assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),finalRevision);await widthInput.fill(String(w));
  await page.waitForTimeout(1800);
  const diagnostics={errors:[],blocked:[],uiErrors:[],queries:[]};async function collect(){const v=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));for(const k of Object.keys(diagnostics))diagnostics[k].push(...v[k]);}
  await collect();await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);assert.equal(await page.evaluate(()=>window.lab.draftRestored),true);assertSame(await page.evaluate(snapshot),complete);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));await collect();await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),complete);await select();await verify(w,d);assert.ok(Math.abs(Number(await widthInput.inputValue())-w)<=0.0005&&Math.abs(Number(await depthInput.inputValue())-d)<=0.0005);
  await page.evaluate(({evidence,diagnostics,w,d,rotated,flat})=>{window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);for(const k of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(evidence[k])window.lab[k]=evidence[k];window.lab.rectangleSizeVerified={width:w,depth:d,rotatedFixture:rotated,flat,centerOrientationAndIdsFixed:true,sourcePitchHeightFixed:true,untouchedAxisPrecision:true,noOpNoHistory:true,invalidSizeBlocked:true,atomicUndoRedo:true,draftRefresh:true,savedReopen:true}}, {evidence,diagnostics,w,d,rotated,flat});
}
module.exports={runRectangleSizeChecks};
