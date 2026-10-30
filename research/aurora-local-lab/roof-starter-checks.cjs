const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
async function runRoofStarterChecks(page){
  await page.keyboard.press('Escape');await page.waitForTimeout(300);
  const initial=await page.evaluate(snapshot),evidence=await page.evaluate(()=>({...window.lab})),id=initial.roofs[0].id;
  await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);
  const apply=page.getByRole('button',{name:'Apply roof starter',exact:true});await apply.waitFor();
  if(initial.dormers.length||initial.roofs[0].folds.length||initial.roofs[0].perimeter.length!==4){
    assert.equal(await apply.isDisabled(),true);assert.equal(await page.getByRole('button',{name:'Turn starter 90°',exact:true}).isDisabled(),true);
    const rect=await apply.boundingBox();await page.mouse.click(rect.x+rect.width/2,rect.y+rect.height/2);await page.waitForTimeout(300);assertSame(await page.evaluate(snapshot),initial);
    await page.evaluate(()=>window.lab.roofStarterVerified={unsupportedGuard:true,geometryUnchanged:true});return;
  }
  const pitch=31.25,checks=[];
  async function stateCheck(kind){
    const current=await page.evaluate(snapshot),native=await page.evaluate(()=>{const r=window.engine.dataStore.findAllHeirs('roof')[0];return{faces:r.faces.map(f=>({pitch:f.pitch,nodes:f.nodes.map(n=>[n.x,n.y,n.z])})),edges:r.perimeterEdges.map(e=>({id:e.id,pitch:e.pitch,height:e.height,nodes:e.nodes.map(n=>({id:n.id,x:n.x,y:n.y}))}))}});
    const roof=current.roofs[0];assert.ok(roof.valid&&roof.constructed&&!roof.error);assertSame(roof.perimeter,initial.roofs[0].perimeter,'Preset keeps footprint');
    assert.equal(roof.faces.length,{hip:4,gable:2,shed:1}[kind]);
    assert.deepEqual(native.edges.map(e=>({id:e.id,height:e.height})),initial.roofs[0].edges.map(e=>({id:e.id,height:e.height})));
    assert.equal(native.edges.filter(e=>e.pitch===pitch).length,{hip:4,gable:2,shed:1}[kind]);for(const e of native.edges)assert.ok(e.pitch===pitch||e.pitch===90);
    for(const face of native.faces){assert.ok(Math.abs(face.pitch-pitch)<1e-7);assert.ok(face.nodes.flat().every(Number.isFinite));}
    let ridge;
    if(kind==='gable'){
      const [a,b]=native.faces,shared=a.nodes.filter(p=>b.nodes.some(q=>Math.hypot(...p.map((v,i)=>v-q[i]))<1e-7));assert.equal(shared.length,2,'Gable faces meet at one two-ended ridge');assert.ok(Math.abs(shared[0][2]-shared[1][2])<1e-7);assert.ok(shared[0][2]>native.edges[0].height);
      const edge=native.edges.find(e=>e.pitch===pitch),[n,m]=edge.nodes,dx=shared[1][0]-shared[0][0],dy=shared[1][1]-shared[0][1],ex=m.x-n.x,ey=m.y-n.y;assert.ok(Math.abs(dx*ey-dy*ex)/(Math.hypot(dx,dy)*Math.hypot(ex,ey))<1e-7,'Ridge must parallel pitched eaves');ridge=[dx,dy];
    }
    return{current,native,ridge};
  }
  let last;
  for(const kind of ['hip','shed','gable']){
    await page.getByLabel('Roof starter shape',{exact:true}).selectOption(kind);await page.getByLabel('Roof starter pitch',{exact:true}).fill(String(pitch));
    const turns={hip:0,shed:3,gable:1}[kind];let priorRidge;
    for(let turn=0;turn<=turns;turn++){
      const before=await page.evaluate(snapshot),revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
      await page.getByRole('button',{name:turn?'Turn starter 90°':'Apply roof starter',exact:true}).click();
      await page.waitForFunction(revision=>window.engine.state.data.historyData.recentVersion!==revision,revision,{timeout:6000});await page.waitForTimeout(400);
      last=await stateCheck(kind);
      if(kind==='gable'&&turn){assert.ok(Math.abs(last.ridge[0]*priorRidge[0]+last.ridge[1]*priorRidge[1])/(Math.hypot(...last.ridge)*Math.hypot(...priorRidge))<1e-7,'Turn swaps gable ridge axis');}priorRidge=last.ridge;
      await page.getByRole('button',{name:'Undo',exact:true}).click();await page.waitForTimeout(450);assertSame(await page.evaluate(snapshot),before);
      await page.getByRole('button',{name:'Redo',exact:true}).click();await page.waitForTimeout(450);assertSame(await page.evaluate(snapshot),last.current);
      checks.push({kind,turn,faces:last.current.roofs[0].faces.length,pitchedEdges:last.native.edges.filter(e=>e.pitch===pitch).map(e=>e.id)});
    }
  }
  // Geometry, not proposed form settings, remains authoritative through history.
  const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);await apply.click();await page.waitForTimeout(1200);assertSame(await page.evaluate(snapshot),last.current);assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),revision);
  await page.getByLabel('Roof starter pitch',{exact:true}).fill('81');await apply.click();assert.equal(await page.getByLabel('Roof starter pitch',{exact:true}).evaluate(n=>n.checkValidity()),false);assertSame(await page.evaluate(snapshot),last.current);await page.getByLabel('Roof starter pitch',{exact:true}).fill(String(pitch));
  await page.waitForTimeout(1800);
  const diagnostics={errors:[],blocked:[],uiErrors:[],queries:[]};async function collect(){const d=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));for(const k of Object.keys(diagnostics))diagnostics[k].push(...d[k]);}
  await collect();await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);assert.equal(await page.evaluate(()=>window.lab.draftRestored),true);assertSame(await page.evaluate(snapshot),last.current);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));await collect();await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),last.current);
  await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);await apply.waitFor();
  await page.evaluate(({evidence,diagnostics,checks,pitch})=>{window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);for(const k of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(evidence[k])window.lab[k]=evidence[k];window.lab.roofStarterVerified={pitch,checks,footprintAndEdgeHeightsFixed:true,sourceFacePitches:true,gableRidge:true,singleUndoSteps:true,noOpNoHistory:true,invalidPitchBlocked:true,draftRefresh:true,savedReopen:true}}, {evidence,diagnostics,checks,pitch});
}
module.exports={runRoofStarterChecks};
