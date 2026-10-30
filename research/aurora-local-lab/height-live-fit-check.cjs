// Cache-only smoke test on one planar roof patch, not a house reconstruction or accuracy benchmark.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('/Users/chris/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const median=a=>[...a].sort((x,y)=>x-y)[Math.floor(a.length/2)];
(async()=>{
 const cache=path.join(__dirname,'runtime/google-kimberly'),metadata=JSON.parse(fs.readFileSync(path.join(cache,'height.json')));assert.ok(Date.parse(metadata.expiresAt)>Date.now());
 const bytes=fs.readFileSync(path.join(cache,'height.bin')),mask=fs.readFileSync(path.join(cache,'height-mask.bin')),points=[];
 const [a,b,tx,d,e,ty]=metadata.pixelToEditor;
 for(let i=0;i<mask.length;i++){const z=bytes.readFloatLE(i*4)-metadata.groundElevation;if(mask[i]!==1||!Number.isFinite(z))continue;const c=i%metadata.width,r=Math.floor(i/metadata.width);points.push({x:a*c+b*r+tx,y:d*c+e*r+ty,z})}
 let best=null;
 for(const center of points.filter((p,i)=>i%7===0&&Math.hypot(p.x,p.y)<12)){
  const near=points.filter(p=>Math.abs(p.x-center.x)<3&&Math.abs(p.y-center.y)<3);if(near.length<80)continue;
  const mean=near.reduce((s,p)=>[s[0]+p.x/near.length,s[1]+p.y/near.length,s[2]+p.z/near.length],[0,0,0]);let xx=0,xy=0,yy=0,xz=0,yz=0;
  for(const p of near){const x=p.x-mean[0],y=p.y-mean[1],z=p.z-mean[2];xx+=x*x;xy+=x*y;yy+=y*y;xz+=x*z;yz+=y*z}
  const det=xx*yy-xy*xy;if(det<1)continue;const gx=(xz*yy-yz*xy)/det,gy=(yz*xx-xz*xy)/det,slope=Math.hypot(gx,gy);if(slope<.2||slope>.8)continue;
  const u=[gx/slope,gy/slope],v=[-u[1],u[0]],interior=points.filter(p=>Math.abs((p.x-center.x)*u[0]+(p.y-center.y)*u[1])<1.65&&Math.abs((p.x-center.x)*v[0]+(p.y-center.y)*v[1])<2.65);if(interior.length<60)continue;
  const error=median(interior.map(p=>Math.abs(p.z-mean[2]-gx*(p.x-mean[0])-gy*(p.y-mean[1]))));if(error>.15||best&&error>=best.error)continue;
  best={center,u,v,error,interior,corners:[[-2,-3],[-2,3],[2,3],[2,-3]].map(([du,dv])=>[center.x+du*u[0]+dv*v[0],center.y+du*u[1]+dv*v[1]])};
 }
 assert.ok(best,'Need one sufficiently planar and masked patch for live smoke check');
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--disable-background-networking','--disable-component-update','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'}),errors=[],blocked=[];
  await context.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!=='http://127.0.0.1:5191'){blocked.push(u.origin);return route.abort()}if(u.pathname==='/height-acquire')return route.fulfill({json:{ok:true,reused:true}});if(route.request().method()==='POST'){blocked.push(u.pathname);return route.abort()}return route.continue()});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:5191/?google=kimberly');await page.waitForFunction(()=>window.labHeightTools);await page.locator('#load-heights').click();await page.waitForFunction(()=>labHeightTools.isAvailable);
  await page.evaluate(()=>labAPI.run('setCameraPosition',{verticalAngle:90,horizontalAngle:0}));await page.waitForTimeout(700);await page.evaluate(()=>labAPI.run('drawPitchedRoof'));
  for(const world of [...best.corners,best.corners[0]]){const p=await page.evaluate(([x,y])=>{const v=engine.viewportManager.getViewportByName('design-3d'),p=v.camerasThree.worldSpace.position.clone().set(x,y,0);v.project(p);const r=v.canvas.getBoundingClientRect();return{x:r.left+p.x,y:r.bottom-p.y}},world);await page.mouse.move(p.x,p.y,{steps:4});await page.waitForTimeout(100);await page.mouse.click(p.x,p.y,{delay:80});await page.waitForTimeout(120)}
  await page.waitForFunction(()=>engine.dataStore.findAllHeirs('roof').some(r=>r.faces.length));await page.evaluate(()=>labAPI.run('cancelMode'));await page.waitForTimeout(300);
  await page.evaluate(corners=>{const r=engine.dataStore.findAllHeirs('roof')[0],low=[(corners[0][0]+corners[1][0])/2,(corners[0][1]+corners[1][1])/2];let chosen=null,best=Infinity;for(const edge of r.perimeterEdges){const [a,b]=edge.nodes,dist=Math.hypot((a.x+b.x)/2-low[0],(a.y+b.y)/2-low[1]);if(dist<best){best=dist;chosen=edge}}for(const edge of r.perimeterEdges){edge.height=2;edge.pitch=edge===chosen?10:90}engine.dataStore.commit();engine.triggerAction('selectEntitiesByIds',{entityIds:[r.id]})},best.corners);await page.waitForTimeout(500);
  const snapshot=()=>page.evaluate(()=>{const r=engine.dataStore.findAllHeirs('roof')[0],q=n=>Math.round(n*1e7)/1e7;return{nodes:r.perimeterNodes.map(n=>[q(n.x),q(n.y)]),edges:r.perimeterEdges.map(e=>[e.id,q(e.height),q(e.pitch)]),faces:r.faces.map(f=>f.nodes.map(n=>[q(n.x),q(n.y),q(n.z)]))}});
  const before=await snapshot();await page.locator('#preview-height-fit').click();assert.equal(await page.locator('#apply-height-fit').isDisabled(),false,await page.locator('#height-status').textContent());assert.deepEqual(await snapshot(),before);
  const preview=await page.evaluate(()=>labHeightTools.lastPreview);assert.equal(preview.length,1);assert.ok(preview[0].error<.35);
  await page.locator('#apply-height-fit').click();await page.getByText('Fit applied. Use Undo to restore original roof.').waitFor();const after=await snapshot();assert.deepEqual(after.nodes,before.nodes);assert.notDeepEqual(after.edges,before.edges);
  await page.evaluate(()=>labAPI.run('undo'));await page.waitForTimeout(400);assert.deepEqual(await snapshot(),before);await page.evaluate(()=>labAPI.run('redo'));await page.waitForTimeout(400);assert.deepEqual(await snapshot(),after);
  const status=await page.evaluate(()=>({errors:lab.errors,csp:lab.blocked,local:Object.keys(localStorage),session:Object.keys(sessionStorage)}));assert.deepEqual(status,{errors:[],csp:[],local:[],session:[]});assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  console.log(JSON.stringify({passed:true,cacheOnly:true,livePlanarPatchFit:true,previewNonmutating:true,nativeRoofValid:true,outlineFixed:true,undoRedo:true,noPersistentModel:true,notWholeHouseOrAccuracyBenchmark:true}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
