const assert=require('node:assert/strict');
const {snapshot,assertSame}=require('./interaction-cases.cjs');
async function runViewFitChecks(page){
  const count=await page.evaluate(()=>window.engine.dataStore.findAllHeirs('roof').length);
  async function settle(){await page.waitForFunction(()=>{const e=window.engine,m=e.viewportManager.activeViewport.cameraModel,c=e.subsystems.entityManager.getEntities(m)?.[0]?.getComponent('CameraAnimationController');return !c?.isAnimating},null,{timeout:8000});await page.waitForTimeout(200);}
  async function fit(){await page.getByRole('button',{name:'Fit',exact:true}).click();await page.waitForFunction(()=>window.lab.cameraFit?.status==='ready',null,{timeout:10000});await settle();return page.evaluate(()=>window.lab.cameraFit);}
  if(!count){const before=await page.evaluate(snapshot),revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);assert.equal((await fit()).kind,'empty');assertSame(await page.evaluate(snapshot),before);assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),revision);await page.evaluate(()=>window.lab.viewFitVerified={emptyScene:true,geometryAndHistoryUnchanged:true});return;}
  await page.keyboard.press('Escape');await page.waitForTimeout(300);
  const source=await page.evaluate(()=>{const r=window.engine.dataStore.findAllHeirs('roof')[0];return{id:r.id,canShed:r.perimeterNodes.length===4&&!r.kinks.length&&!r.dormers.length}});
  if(count===1&&source.canShed){
    await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),source.id);
    await page.getByLabel('Roof starter shape',{exact:true}).selectOption('shed');await page.getByLabel('Roof starter pitch',{exact:true}).fill('30');await page.getByRole('button',{name:'Apply roof starter',exact:true}).click();await page.waitForTimeout(1300);
  }
  const geometry=await page.evaluate(snapshot),revision=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),checks=[];
  const view=()=>page.evaluate(()=>{const e=window.engine,v=e.viewportManager.activeViewport,m=v.cameraModel,c=v.camerasThree.worldSpace;return{vertical:m.verticalAngle,horizontal:m.horizontalAngle,radius:m.radius,width:v.canvas.width,height:v.canvas.height,perspective:!!c.isPerspectiveCamera}});
  async function contained(label){
    const result=await page.evaluate(()=>{
      const e=window.engine,v=e.viewportManager.activeViewport,c=v.camerasThree.worldSpace,points=[];
      for(const o of [...e.dataStore.findAllHeirs('roof'),...e.dataStore.findAll('dormer')])for(const f of o.faces||[])for(const p of f.nodes)points.push([p.x,p.y,p.z]);
      for(const w of e.dataStore.findAll('wall.implicit'))for(const p of w.nodes)points.push([p.x,p.y,p.z]);
      const projected=points.map(p=>{const n=c.position.clone().set(...p).project(c);return[n.x,n.y,n.z]});
      return{count:points.length,maxX:Math.max(...projected.map(p=>Math.abs(p[0]))),maxY:Math.max(...projected.map(p=>Math.abs(p[1]))),depthMin:Math.min(...projected.map(p=>p[2])),depthMax:Math.max(...projected.map(p=>p[2])),finite:projected.flat().every(Number.isFinite),fit:window.lab.cameraFit,view:{vertical:v.cameraModel.verticalAngle,horizontal:v.cameraModel.horizontalAngle}};
    });
    assert.ok(result.count>0&&result.finite);assert.ok(result.maxX<0.98&&result.maxY<0.98,`${label}: geometry clipped ${JSON.stringify(result)}`);assert.ok(result.depthMin>-1&&result.depthMax<1,`${label}: geometry outside depth clipping planes`);
    assertSame(await page.evaluate(snapshot),geometry,'Framing must not edit roof geometry');assert.equal(await page.evaluate(()=>window.engine.state.data.historyData.recentVersion),revision,'Framing must not add design history');checks.push({label,...result});await page.evaluate(checks=>window.lab.viewFitProgress=checks,checks);return result;
  }
  await page.getByRole('button',{name:'3D',exact:true}).click();await settle();let angles=await view();
  const first=await fit();assert.equal(first.kind,'height-aware');let result=await contained('3D');assert.ok(Math.abs(result.view.vertical-angles.vertical)<1e-7&&Math.abs(result.view.horizontal-angles.horizontal)<1e-7);
  const mode=await page.evaluate(()=>window.engine.subsystems.modeManager.actualStateMode),selection=await page.evaluate(()=>window.engine.bridge.serializeSelection());await fit();await contained('repeat');assert.equal(await page.evaluate(()=>window.engine.subsystems.modeManager.actualStateMode),mode);assert.deepEqual(await page.evaluate(()=>window.engine.bridge.serializeSelection()),selection);
  // Queue Fit immediately after native view animation; do not discard the request.
  await page.getByRole('button',{name:'2D',exact:true}).click();await fit();result=await contained('2D');assert.ok(Math.abs(result.view.vertical-90)<1e-7);
  await page.getByRole('button',{name:'3D',exact:true}).click();await settle();
  await page.evaluate(()=>window.labAPI.run('setCameraPosition',{verticalAngle:55,horizontalAngle:145}));await settle();angles=await view();assert.ok(angles.perspective&&Math.abs(angles.vertical-55)<1e-7&&Math.abs(angles.horizontal-145)<1e-7,'Orbit fixture must enter requested 3D pose');await fit();result=await contained('orbit');assert.ok(Math.abs(result.view.vertical-angles.vertical)<1e-7&&Math.abs(result.view.horizontal-angles.horizontal)<1e-7);
  const viewport=page.locator('#viewport'),rect=await viewport.boundingBox(),radius=(await view()).radius;await page.mouse.move(rect.x+rect.width/2,rect.y+rect.height/2,{steps:8});await page.waitForTimeout(200);await page.mouse.wheel(0,500);await page.waitForFunction(radius=>Math.abs(window.engine.viewportManager.activeViewport.cameraModel.radius-radius)>1e-6,radius,{timeout:5000});await fit();await contained('zoom-refit');
  await page.setViewportSize({width:720,height:900});await page.waitForTimeout(700);await fit();await contained('portrait');
  await page.setViewportSize({width:1280,height:900});await page.waitForTimeout(700);await fit();await contained('wide-restored');
  await page.evaluate(({checks,count})=>window.lab.viewFitVerified={roofCount:count,checks,geometryAndHistoryUnchanged:true,anglesRetained:true,modeAndSelectionRetained:true,nativeZoomAndOrbit:true,portraitResize:true}, {checks,count});
}
module.exports={runViewFitChecks};
