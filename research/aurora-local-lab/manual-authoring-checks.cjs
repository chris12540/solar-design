const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {createHash}=require('node:crypto');
const {snapshot,assertSame,place}=require('./interaction-cases.cjs');
async function runManualAuthoringChecks(page,{starter=null}={}){
  const diagnostics={errors:[],blocked:[],uiErrors:[],queries:[]};
  async function collect(){const d=await page.evaluate(()=>({errors:window.lab.errors,blocked:window.lab.blocked,uiErrors:window.lab.originalUi.errors,queries:window.lab.originalUi.localMetadataRequests}));for(const k of Object.keys(diagnostics))diagnostics[k].push(...d[k]);}
  async function ready(){await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});await page.waitForTimeout(500);}
  async function select(id){await page.evaluate(id=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}),id);await page.waitForTimeout(250);}
  async function project(point){return page.evaluate(point=>{const v=window.engine.viewportManager.getViewportByName('design-3d'),p=v.camerasThree.worldSpace.position.clone().set(point.x,point.y,point.z);v.project(p);const r=v.canvas.getBoundingClientRect();return{x:r.left+p.x,y:r.bottom-p.y}},point);}
  async function clickModelPoint(point){const p=await project(point);await page.mouse.move(p.x,p.y,{steps:8});await page.mouse.click(p.x,p.y,{delay:100});await page.waitForTimeout(250);}
  const source=await page.evaluate(()=>{const r=window.engine.dataStore.findAllHeirs('roof')[0],e=r.perimeterEdges[0],[a,b]=e.nodes;return{roofId:r.id,edgeId:e.id,count:r.perimeterNodes.length,length:e.length,point:{x:(a.x+b.x)/2,y:(a.y+b.y)/2,z:(a.z+b.z)/2}}});
  let length=null;
  if(starter){
    await page.keyboard.press('Escape');await page.waitForTimeout(300);await select(source.roofId);
    await page.getByLabel('Roof starter shape',{exact:true}).selectOption(starter);await page.getByLabel('Roof starter pitch',{exact:true}).fill('30');
    await page.getByRole('button',{name:'Apply roof starter',exact:true}).click();
    await page.waitForFunction(faces=>{const r=window.engine.dataStore.findAllHeirs('roof')[0];return r.isValid&&r.isConstructed&&r.faces.length===faces},starter==='gable'?2:1);await page.waitForTimeout(400);
    await page.getByRole('button',{name:'2D',exact:true}).click();await page.waitForTimeout(600);await select(source.roofId);await page.getByRole('button',{name:'Edit roof',exact:true}).click();await page.waitForTimeout(400);
  }else{
  await page.getByRole('button',{name:'2D',exact:true}).click();await page.waitForTimeout(400);
  if(!await page.evaluate(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'))){await select(source.roofId);await page.getByRole('button',{name:'Edit roof',exact:true}).click();await page.waitForTimeout(400);}
  await clickModelPoint(source.point);
  await page.getByRole('button',{name:'Keep first corner fixed',exact:true}).click();
  length=source.length+0.875;
  await page.getByRole('spinbutton',{name:'Roof edge length in meters',exact:true}).fill(String(length));await page.getByRole('spinbutton',{name:'Roof edge length in meters',exact:true}).blur();
  await page.waitForFunction(({id,length})=>Math.abs(window.engine.dataStore.find(id).length-length)<1e-7,{id:source.edgeId,length});await page.waitForTimeout(1200);
  await page.getByRole('button',{name:'Add corner at midpoint',exact:true}).click();await page.getByTestId('corner-angle').waitFor();
  const corner=await page.evaluate(()=>{const item=window.engine.bridge.serializeSelection().find(s=>s.type==='node.perimeter'),n=window.engine.dataStore.find(item.data.id),r=n.roof,[a,b]=n.edges.map(e=>e.otherNode(n));const c=r.perimeterNodes.reduce((p,n)=>({x:p.x+n.x/r.perimeterNodes.length,y:p.y+n.y/r.perimeterNodes.length}),{x:0,y:0});let dx=-(b.y-a.y),dy=b.x-a.x;const l=Math.hypot(dx,dy);dx/=l;dy/=l;if(dx*(n.x-c.x)+dy*(n.y-c.y)<0){dx=-dx;dy=-dy;}return{id:n.id,from:{x:n.x,y:n.y,z:n.z},to:{x:n.x+dx,y:n.y+dy,z:n.z}}});
  const a=await project(corner.from),b=await project(corner.to);await page.mouse.move(a.x,a.y,{steps:8});await page.mouse.down();await page.waitForTimeout(80);await page.mouse.move(b.x,b.y,{steps:16});await page.mouse.up();await page.waitForTimeout(700);
  const outlined=await page.evaluate(snapshot);assert.equal(outlined.roofs[0].perimeter.length,source.count+1);assert.ok(outlined.roofs[0].valid&&outlined.roofs[0].constructed);
  const moved=await page.evaluate(id=>{const n=window.engine.dataStore.find(id);return {x:n.x,y:n.y}},corner.id);assert.ok(Math.hypot(moved.x-corner.from.x,moved.y-corner.from.y)>0.2,'New corner must move through pointer drag');
  }
  const preDetails=await page.evaluate(snapshot);
  // Separate faces for Gable; separated uphill positions for the single Shed face.
  const points=await page.evaluate(()=>{
    const r=window.engine.dataStore.findAllHeirs('roof')[0],area=f=>Math.abs(f.nodes.reduce((s,n,i)=>{const q=f.nodes[(i+1)%f.nodes.length];return s+n.x*q.y-q.x*n.y},0)),faces=[...r.faces].sort((a,b)=>area(b)-area(a));
    const center=f=>f.nodes.reduce((p,n)=>({x:p.x+n.x/f.nodes.length,y:p.y+n.y/f.nodes.length,z:p.z+n.z/f.nodes.length}),{x:0,y:0,z:0});
    if(faces.length>1)return faces.slice(0,2).map(center);
    const f=faces[0],c=center(f),[a,b,d]=f.nodes,u=[b.x-a.x,b.y-a.y,b.z-a.z],v=[d.x-a.x,d.y-a.y,d.z-a.z],normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];
    const gradient=[-normal[0]/normal[2],-normal[1]/normal[2]],slope=Math.hypot(...gradient),direction=gradient.map(n=>n/slope),along=f.nodes.map(n=>n.x*direction[0]+n.y*direction[1]),offset=(Math.max(...along)-Math.min(...along))*0.22;
    if(!Number.isFinite(slope)||slope<=0)throw new Error('Single-face fixture needs a sloping host');
    return[-1,1].map(sign=>({x:c.x+sign*direction[0]*offset,y:c.y+sign*direction[1]*offset,z:c.z+sign*slope*offset}));
  });
  await place(page,3,points[0],'dormer');await place(page,1,points[1],'kink');
  const detailed=await page.evaluate(snapshot);assert.equal(detailed.dormers.length,1);assert.equal(detailed.roofs[0].folds.length,1);assert.equal(detailed.roofs[0].perimeter.length,starter?source.count:source.count+1);assertSame(detailed.roofs[0].perimeter,preDetails.roofs[0].perimeter,'Details keep source outline');assertSame(detailed.roofs[0].edges,preDetails.roofs[0].edges,'Details keep source edge pitch/height');assert.ok(detailed.roofs[0].valid&&detailed.roofs[0].constructed&&!detailed.roofs[0].error);
  const name=starter?`Manual ${starter} - dormer and fold`:'Manual outline-first - dormer and fold';await page.getByLabel('Example name').fill(name);await page.getByRole('button',{name:'Save locally',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));
  const saved=await page.evaluate(snapshot);await collect();await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);await ready();assertSame(await page.evaluate(snapshot),saved);assert.equal(await page.getByLabel('Example name').inputValue(),name);
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Export test case',exact:true}).click()]);
  assert.ok(download.suggestedFilename().startsWith(starter?`Manual-${starter}-dormer-and-fold-`:'Manual-outline-first-dormer-and-fold-'));
  const output=path.join(__dirname,'runtime',starter?`manual-${starter}-details.roofcase.json`:'manual-outline-first.roofcase.json');await download.saveAs(output);const packet=JSON.parse(fs.readFileSync(output,'utf8'));
  assert.equal(packet.name,name);assert.equal(packet.schema,'roof-lab-case/v1');assert.equal(packet.benchmarkCompatible,false);assert.equal(packet.coordinates.georeferenced,false);assert.equal(packet.nativeDesignSha256,createHash('sha256').update(packet.nativeDesignJson).digest('hex'));
  // Optional metadata remains backwards compatible with unnamed original v1 files.
  const names=await page.evaluate(async packet=>{const {validateTestCase}=await import('/case-export.js'),old=structuredClone(packet);delete old.name;const unnamed=await validateTestCase(old,window.lab.engineArtifacts);const invalid=structuredClone(packet);invalid.name={bad:true};let rejected=false;try{await validateTestCase(invalid,window.lab.engineArtifacts)}catch{rejected=true}return{fallback:unnamed.name,rejected}},packet);
  assert.equal(names.fallback,'Imported test case');assert.equal(names.rejected,true);
  await collect();await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'New example',exact:true}).click()]);await ready();assert.equal(await page.evaluate(()=>window.engine.dataStore.findAllHeirs('roof').length),0);
  const choosing=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Open test case',exact:true}).click();const chooser=await choosing;await collect();await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),chooser.setFiles(output)]);await ready();assertSame(await page.evaluate(snapshot),saved);assert.equal(await page.getByLabel('Example name').inputValue(),name);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));await collect();await page.reload({waitUntil:'domcontentloaded'});await ready();assertSame(await page.evaluate(snapshot),saved);assert.equal(await page.getByLabel('Example name').inputValue(),name);
  await page.evaluate(({diagnostics,source,length,name,starter})=>{window.lab.errors.push(...diagnostics.errors);window.lab.blocked.push(...diagnostics.blocked);window.lab.originalUi.errors.push(...diagnostics.uiErrors);window.lab.originalUi.localMetadataRequests.push(...diagnostics.queries);window.lab.manualAuthoringVerified={blankStart:true,sourceCorners:source.count,finalCorners:starter?source.count:source.count+1,starter,presetBeforeDetails:!!starter,sourceOutlineAndPitchRetained:true,lengthTarget:length,outlineEditedBeforeDetails:true,dormer:true,fold:true,name,namedSaveReopen:true,namedDownload:true,newExampleImport:true,importSaveRefresh:true,oldUnnamedCompatible:true,invalidNameRejected:true}}, {diagnostics,source,length,name,starter});
}
module.exports={runManualAuthoringChecks};
