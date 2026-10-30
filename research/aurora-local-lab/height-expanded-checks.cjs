// Independent/concave/detailed native fitting checks. Every input is synthetic.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{createHash,randomUUID}=require('node:crypto');
const {chromium}=require('/Users/chris/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const digest=b=>createHash('sha256').update(b).digest('hex');
(async()=>{
 const mode=process.argv.includes('--details')?'details':process.argv.includes('--plane')?'plane':'concave',root=__dirname,source='d'.repeat(32),caseId=randomUUID();
 const image=fs.readFileSync(path.join(root,'runtime/input-contract/grid.png')),expiresAt=new Date(Date.now()+300000).toISOString();
 const manifest={schema:'roof-lab-google-preview/v1',provider:'Google Solar API',address:'Synthetic expanded-fit fixture',attribution:'Synthetic fixture',fetchedAt:new Date().toISOString(),expiresAt,width:64,height:48,pixelToEditor:[.5,0,-15.75,0,-.5,11.75],pngSha256:digest(image),byteLength:image.length};
 const raw=mode==='details'?JSON.parse(fs.readFileSync(path.join(root,'runtime/manual-gable-details.roofcase.json'))).nativeDesignJson:null;
 let height=null,heights=null,mask=null,stored={schema:'roof-lab-case/v2',caseId,name:'Synthetic expanded fit',expiresAt,nativeDesignJson:raw,source:{id:source,imageSha256:manifest.pngSha256},heightContext:{groundElevation:null,heightSha256:null}};
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--disable-background-networking','--disable-component-update','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'}),errors=[],blocked=[];
  await context.route('**/*',route=>{const u=new URL(route.request().url()),p=u.pathname;if(u.origin!=='http://127.0.0.1:5193'){blocked.push(u.origin);return route.abort()}
   if(p==='/google-imagery.json')return route.fulfill({json:manifest});if(p==='/google-imagery.png')return route.fulfill({body:image,contentType:'image/png'});
   if(p==='/source-case')return route.fulfill({json:stored});if(p==='/source-cases')return route.fulfill({json:[]});
   if(p==='/source-case-save'){const body=route.request().postDataJSON();stored={...stored,...body,caseId:body.caseId,source:{id:source,imageSha256:manifest.pngSha256}};return route.fulfill({json:stored})}
   if(p==='/height-acquire')return route.fulfill({json:{ok:true,reused:true}});if(p==='/height.json')return route.fulfill({json:height});if(p==='/height.bin')return route.fulfill({body:heights});if(p==='/height-mask.bin')return route.fulfill({body:mask});return route.continue()});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:5193/?google='+source+(raw?'&case='+caseId:''));await page.waitForFunction(()=>window.labHeightTools);
  if(mode!=='details'){
   await page.evaluate(()=>labAPI.run('setCameraPosition',{verticalAngle:90,horizontalAngle:0}));await page.waitForTimeout(700);await page.evaluate(mode=>labAPI.run(mode==='plane'?'drawRoofPlane':'drawPitchedRoof'),mode);
   const corners=mode==='plane'?[[-10,6],[10,6],[10,-6],[-10,-6]]:[[-12,10],[12,10],[12,0],[0,0],[0,-10],[-12,-10]];
   for(const world of [...corners,corners[0]]){const p=await page.evaluate(([x,y])=>{const v=engine.viewportManager.getViewportByName('design-3d'),p=v.camerasThree.worldSpace.position.clone().set(x,y,0);v.project(p);const r=v.canvas.getBoundingClientRect();return{x:r.left+p.x,y:r.bottom-p.y}},world);await page.mouse.move(p.x,p.y,{steps:4});await page.waitForTimeout(100);await page.mouse.click(p.x,p.y,{delay:80});await page.waitForTimeout(120)}
   await page.waitForFunction(()=>engine.dataStore.findAllHeirs('roof').some(r=>r.faces.length));await page.evaluate(()=>labAPI.run('cancelMode'));await page.waitForTimeout(300);
  }
  await page.evaluate(()=>engine.triggerAction('selectEntitiesByIds',{entityIds:[engine.dataStore.findAllHeirs('roof')[0].id]}));await page.waitForTimeout(400);
  const surfaces=await page.evaluate(()=>engine.dataStore.findAllHeirs('roof')[0].faces.map(f=>f.nodes.map(n=>[n.x,n.y,n.z])));
  const inside=(x,y,ring)=>{let yes=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])yes=!yes}return yes};
  function zAt(x,y,face){const a=face[0];let normal;for(let i=1;i<face.length-1;i++){const b=face[i],c=face[i+1],u=b.map((v,j)=>v-a[j]),v=c.map((w,j)=>w-a[j]);normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];if(Math.abs(normal[2])>1e-7)return a[2]-(normal[0]*(x-a[0])+normal[1]*(y-a[1]))/normal[2]}return NaN}
  const width=128,rows=96,affine=[.25,0,-15.875,0,-.25,11.875];heights=Buffer.alloc(width*rows*4);mask=Buffer.alloc(width*rows);
  for(let r=0;r<rows;r++)for(let c=0;c<width;c++){const x=affine[2]+c*.25,y=affine[5]-r*.25,i=r*width+c,face=surfaces.find(f=>inside(x,y,f));mask[i]=face?1:0;const z=face?(mode==='plane'?4+Math.tan(35*Math.PI/180)*(6-y):zAt(x,y,face)+(mode==='details'?.25:.5)):0;heights.writeFloatLE(100+z,i*4)}
  height={schema:'roof-lab-height/v1',expiresAt,imageSha256:manifest.pngSha256,width,height:rows,pixelToEditor:affine,datum:'EGM96',units:'m',byteOrder:'little-endian-float32',groundElevation:100,sha256:digest(heights),maskSha256:digest(mask)};
  await page.locator('#load-heights').click();await page.waitForFunction(()=>labHeightTools.isAvailable);
  const snapshot=()=>page.evaluate(()=>{const r=engine.dataStore.findAllHeirs('roof')[0],q=n=>Math.round(n*1e6)/1e6,v=engine.bridge.makeDesignJsonToSave(),native=typeof v==='string'?JSON.parse(v):v;return{type:r.type,xy:r.perimeterNodes.map(n=>[q(n.x),q(n.y)]),height:q(r.height),pitch:q(r.pitch),edges:r.perimeterEdges.map(e=>[e.id,q(e.height??0),q(e.pitch??0)]),details:{dormers:(r.dormers||[]).map(d=>[d.id,d.x,d.y,d.width,d.pitch,d.pitchFront]),folds:(r.kinks||[]).map(d=>[d.id,d.x,d.y,d.pitch])},geometry:native.site_json.buildings.map(b=>[b.faces.map(f=>f.nodes.map(i=>[q(b.nodes[i].x),q(b.nodes[i].y),q(b.nodes[i].z)])),b.walls.map(w=>w.nodes.map(i=>[q(b.nodes[i].x),q(b.nodes[i].y),q(b.nodes[i].z)]))])}});
  const before=await snapshot();await page.locator('#preview-height-fit').click();assert.equal(await page.locator('#apply-height-fit').isDisabled(),false,await page.locator('#height-status').textContent());assert.deepEqual(await snapshot(),before);await page.locator('#apply-height-fit').click();await page.getByText('Fit applied. Use Undo to restore original roof.').waitFor({timeout:10000});const after=await snapshot();assert.deepEqual(after.xy,before.xy);assert.deepEqual(after.details,before.details);
  if(mode==='plane'){assert.ok(Math.abs(after.pitch-35)<.01);assert.ok(Math.abs(after.height-4)<.01)}else for(let i=0;i<before.edges.length;i++)if(before.edges[i][2]<89)assert.ok(Math.abs(after.edges[i][1]-before.edges[i][1]-(mode==='details'?.25:.5))<.02);
  await page.evaluate(()=>labAPI.run('undo'));await page.waitForTimeout(500);assert.deepEqual(await snapshot(),before);await page.evaluate(()=>labAPI.run('redo'));await page.waitForTimeout(500);assert.deepEqual(await snapshot(),after);
  const state=await page.evaluate(()=>({valid:engine.dataStore.findAllHeirs('roof')[0].isValid,errors:lab.errors,csp:lab.blocked,local:Object.keys(localStorage),session:Object.keys(sessionStorage)}));assert.deepEqual(state,{valid:true,errors:[],csp:[],local:[],session:[]});assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  console.log(JSON.stringify({passed:true,mode,syntheticOnly:true,previewNonmutating:true,outlineFixed:true,nativeDetailsPreserved:true,knownFitRecovered:true,undoRedo:true,noAcquisitions:true}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
