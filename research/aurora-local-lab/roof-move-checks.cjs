const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
async function runRoofMoveChecks(page,{oblique=false}={}) {
  await page.getByRole('button',{name:oblique?'3D':'2D',exact:true}).click();
  await page.waitForTimeout(800);
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith('default-site'));
  const before=await page.evaluate(snapshot);
  assert.equal(before.roofs.length,1,'Move fixture requires one roof');
  const id=before.roofs[0].id;
  async function startMove() {
    await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);
    await page.getByTestId('roofs-height').waitFor();
    await page.getByRole('button',{name:'Move',exact:true}).click();
    await page.waitForFunction(id=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':move.roof')&&
      window.engine.subsystems.modeManager.model.movedRoofs.some(r=>r.id===id),id);
    await page.waitForTimeout(350);
  }
  async function screenPoint() {
    return page.evaluate(()=>{
      const roof=window.engine.dataStore.findAllHeirs('roof')[0];
      const area=f=>Math.abs(f.nodes.reduce((a,n,i)=>{const p=f.nodes[(i+1)%f.nodes.length];return a+n.x*p.y-p.x*n.y},0));
      const face=[...roof.faces].sort((a,b)=>area(b)-area(a))[0];
      const p=face.nodes.reduce((p,n)=>({x:p.x+n.x/face.nodes.length,y:p.y+n.y/face.nodes.length,z:p.z+n.z/face.nodes.length}),{x:0,y:0,z:0});
      const view=window.engine.viewportManager.getViewportByName('design-3d');
      const v=view.camerasThree.worldSpace.position.clone().set(p.x,p.y,p.z);view.project(v);
      const r=view.canvas.getBoundingClientRect();return {x:r.left+v.x,y:r.bottom-v.y};
    });
  }
  await startMove();
  const point=await screenPoint();
  const previousDraft=await page.evaluate(()=>sessionStorage.getItem('aurora-local-lab:tab-draft:v1'));
  const revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
  await page.mouse.move(point.x,point.y,{steps:8});await page.waitForTimeout(200);
  assert.equal(await page.evaluate(()=>window.engine.subsystems.inputManager.hoverEntity?.tag),'roof','Move target must be the roof');
  await page.mouse.down();await page.waitForTimeout(100);
  await page.mouse.move(point.x+55,point.y+30,{steps:16});await page.waitForTimeout(200);
  await page.mouse.up();
  await page.waitForFunction(revision=>window.engine.state.data.historyData.recentVersion!==revision,revision,{timeout:5000});
  await page.waitForTimeout(400);
  const after=await page.evaluate(snapshot);
  const delta=after.roofs[0].perimeter[0].map((v,i)=>v-before.roofs[0].perimeter[0][i]);
  assert.ok(Math.hypot(...delta)>0.01,'Drag must move whole footprint');
  function points(actual,expected) {
    assert.equal(actual.length,expected.length);
    for(let i=0;i<expected.length;i++) {
      const target=expected[i].map((v,axis)=>v+(axis<2?delta[axis]:0));
      assertSame(actual[i],target,'uniform roof translation');
    }
  }
  assert.equal(after.roofs.length,before.roofs.length);
  for(let i=0;i<before.roofs.length;i++) {
    const a=after.roofs[i],b=before.roofs[i];
    assert.equal(a.id,b.id);assert.equal(a.valid,true);assert.equal(a.constructed,true);assert.ok(!a.error);
    assertSame(a.edges,b.edges,'movement must preserve source pitches and heights');
    points(a.perimeter,b.perimeter);assert.equal(a.faces.length,b.faces.length);
    for(let j=0;j<b.faces.length;j++)points(a.faces[j],b.faces[j]);
    assert.equal(a.walls.length,b.walls.length);
    for(let j=0;j<b.walls.length;j++){assert.equal(a.walls[j].sourceId,b.walls[j].sourceId);points(a.walls[j].nodes,b.walls[j].nodes);}
    assert.equal(a.folds.length,b.folds.length);
    for(let j=0;j<b.folds.length;j++) {
      assert.equal(a.folds[j].id,b.folds[j].id);assert.equal(a.folds[j].pitch,b.folds[j].pitch);
      assertSame(a.folds[j].height,b.folds[j].height);
      assertSame([a.folds[j].x,a.folds[j].y],[b.folds[j].x+delta[0],b.folds[j].y+delta[1]]);
    }
  }
  assert.equal(after.dormers.length,before.dormers.length);
  for(let i=0;i<before.dormers.length;i++) {
    const a=after.dormers[i],b=before.dormers[i];
    assert.equal(a.id,b.id);assert.equal(a.shape,b.shape);assert.equal(a.pitch,b.pitch);assert.equal(a.faces.length,b.faces.length);
    for(let j=0;j<b.faces.length;j++)points(a.faces[j],b.faces[j]);
  }
  await page.waitForFunction(previous=>{
    const current=sessionStorage.getItem('aurora-local-lab:tab-draft:v1');return current&&current!==previous;
  },previousDraft,{timeout:6000});
  assert.ok(await page.evaluate(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':move.roof')),'Idle draft must retain Move mode');
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith('default-site'));
  await page.getByRole('button',{name:'Undo',exact:true}).click();await page.waitForTimeout(500);
  assertSame(await page.evaluate(snapshot),before);
  await page.getByRole('button',{name:'Redo',exact:true}).click();await page.waitForTimeout(500);
  assertSame(await page.evaluate(snapshot),after);
  // Entering and abandoning Move must not add a history entry or move geometry.
  const cancelRevision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
  await startMove();
  await page.keyboard.press('Escape');await page.waitForTimeout(400);
  assertSame(await page.evaluate(snapshot),after);
  assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),cancelRevision);
  await startMove();
  const beforeDraftReload=await page.evaluate(()=>({...window.lab}));
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});
  await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),after);
  assert.equal(await page.evaluate(()=>window.lab.draftRestored),true,'Move must recover without explicit Save or leaving Move mode');
  await page.evaluate(previous=>{
    window.lab.errors.push(...previous.errors);window.lab.blocked.push(...previous.blocked);
    window.lab.originalUi.errors.push(...previous.originalUi.errors);window.lab.originalUi.localMetadataRequests.push(...previous.originalUi.localMetadataRequests);
    for(const key of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(previous[key])window.lab[key]=previous[key];
  },beforeDraftReload);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));
  const previous=await page.evaluate(()=>({...window.lab}));
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);
  await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});
  await page.waitForTimeout(500);assertSame(await page.evaluate(snapshot),after);
  await page.evaluate(({previous,delta,oblique})=>{
    window.lab.errors.push(...previous.errors);window.lab.blocked.push(...previous.blocked);
    window.lab.originalUi.errors.push(...previous.originalUi.errors);window.lab.originalUi.localMetadataRequests.push(...previous.originalUi.localMetadataRequests);
    for(const key of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(previous[key])window.lab[key]=previous[key];
    window.lab.roofMoveVerified={view:oblique?'3d':'2d',deltaMeters:delta,uniformTranslation:true,detailsRetained:true,pitchesRetained:true,
      undoRedo:true,idleMoveModeRetained:true,draftRefresh:true,emptyMoveCancelled:true,reopen:true,toleranceMeters:1e-7};
  },{previous,delta,oblique});
}
module.exports={runRoofMoveChecks};
