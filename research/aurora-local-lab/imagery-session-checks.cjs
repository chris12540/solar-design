// Source-session tests use only generated PNG, never Google's imagery or API.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{createHash}=require('node:crypto');
const {chromium}=require('/Users/chris/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const dynamic=process.argv.includes('--dynamic'),source=dynamic?'d'.repeat(32):'kimberly',suffix=dynamic?'-dynamic':'';
 const root=__dirname,files=['app.js','imagery-session.js','server.py','imagery-session-checks.cjs','index.html','style.css'];
 const hashes=()=>Object.fromEntries(files.map(p=>[p,createHash('sha256').update(fs.readFileSync(path.join(root,p))).digest('hex')])),sourceHashes=hashes();
 const bytes=fs.readFileSync(path.join(root,'runtime/input-contract/grid.png'));
 const manifest={schema:'roof-lab-google-preview/v1',provider:'Google Solar API',address:'Synthetic source-session fixture',attribution:'Synthetic fixture; no Google imagery',fetchedAt:new Date().toISOString(),expiresAt:new Date(Date.now()+180000).toISOString(),width:64,height:48,pixelToEditor:[.25,0,-7.875,0,-.25,5.875],pngSha256:createHash('sha256').update(bytes).digest('hex'),byteLength:bytes.length};
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--disable-background-networking','--disable-component-update','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'}),blocked=[],errors=[];
  await context.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!=='http://127.0.0.1:5191'){blocked.push(u.origin);return route.abort()}if(u.pathname==='/google-imagery.json')return route.fulfill({json:manifest});if(u.pathname==='/google-imagery.png')return route.fulfill({body:bytes,contentType:'image/png'});return route.continue()});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:5191/');await page.waitForFunction(()=>window.lab?.stage==='ready');
  const initial=await page.evaluate(()=>{localStorage.setItem('aurora-local-lab:manual-design:v1','manual-sentinel');sessionStorage.setItem('aurora-local-lab:active-example','preserved-manual');sessionStorage.setItem('aurora-local-lab:tab-draft:v1','manual-draft-sentinel');return{local:{...localStorage},session:{...sessionStorage}}});
  await page.goto('http://127.0.0.1:5191/?google='+source);await page.waitForFunction(()=>window.lab?.imagery?.active,{},{timeout:30000});
  for(const id of ['save','reopen','export','export-case','open-case','saved-cases'])assert.equal(await page.locator('#'+id).isDisabled(),true,id+' must be disabled');
  const mounted=await page.evaluate(()=>({registration:window.lab.imagery.registration,roofs:engine.dataStore.findAllHeirs('roof').length,history:JSON.stringify(engine.state.data.historyData),design:engine.bridge.makeDesignJsonToSave()}));
  assert.equal(mounted.roofs,0);assert.equal(mounted.registration.widthMeters,16);assert.equal(mounted.registration.heightMeters,12);
  await page.evaluate(()=>window.labAPI.run('setCameraPosition',{verticalAngle:90,horizontalAngle:0}));
  await page.waitForTimeout(700);
  await page.evaluate(()=>window.labAPI.run('drawFlatRoof'));
  const points=[[-6,4],[6,4],[6,-4],[-6,-4],[-6,4]];
  for(const world of points){
   const point=await page.evaluate(([x,y])=>{const v=engine.viewportManager.getViewportByName('design-3d'),p=v.camerasThree.worldSpace.position.clone().set(x,y,0);v.project(p);const r=v.canvas.getBoundingClientRect();return{x:r.left+p.x,y:r.bottom-p.y}},world);
   await page.mouse.move(point.x,point.y,{steps:4});await page.waitForTimeout(100);await page.mouse.click(point.x,point.y,{delay:80});await page.waitForTimeout(120);
  }
  await page.waitForFunction(()=>engine.dataStore.findAllHeirs('roof').some(r=>r.faces.length));
  const traced=await page.evaluate(()=>engine.dataStore.findAllHeirs('roof')[0].perimeterNodes.map(n=>[n.x,n.y]));
  assert.equal(traced.length,4);
  for(const expected of points.slice(0,4))assert.ok(traced.some(actual=>Math.hypot(actual[0]-expected[0],actual[1]-expected[1])<.05),'Trace must match specified grid coordinates: '+JSON.stringify({traced,expected}));
  await page.evaluate(()=>window.labAPI.run('cancelMode'));
  await page.waitForTimeout(400);
  const editedHistory=await page.evaluate(()=>JSON.stringify(engine.state.data.historyData));
  await page.evaluate(()=>window.labAPI.save());
  await page.evaluate(()=>{document.querySelector('#export').onclick();document.querySelector('#export-case').onclick();document.querySelector('#reopen').onclick();});
  await page.waitForTimeout(1800);
  assert.deepEqual(await page.evaluate(()=>({local:{...localStorage},session:{...sessionStorage}})),initial,'Source entry/save/export must not change manual library or draft');
  assert.equal(await page.evaluate(()=>JSON.stringify(engine.state.data.historyData)),editedHistory);
  await page.screenshot({path:path.join(root,`runtime/input-contract/source-session-synthetic${suffix}.png`)});
  const loadedErrors=await page.evaluate(()=>({errors:lab.errors,csp:lab.blocked}));assert.deepEqual(loadedErrors,{errors:[],csp:[]});
  await page.locator('#new-case').click();await page.waitForURL('http://127.0.0.1:5191/');await page.waitForFunction(()=>window.lab?.stage==='ready');
  assert.equal(await page.evaluate(()=>engine.subsystems.orthoTextureCollection.groundTextures.length),0);
  // Fresh source page, then advance wall clock to force expiry on resume.
  await page.goto('http://127.0.0.1:5191/?google='+source);await page.waitForFunction(()=>window.lab?.imagery?.active);
  await page.clock.install();await page.clock.setSystemTime(new Date(Date.parse(manifest.expiresAt)+1000));
  await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));await page.waitForURL('http://127.0.0.1:5191/');
  assert.deepEqual(blocked,[]);assert.deepEqual(errors,[]);assert.deepEqual(hashes(),sourceHashes);
  const result={passed:true,syntheticOnly:true,sourceHashes,registration:mounted.registration,permanentStorageUntouched:true,saveExportBlocked:true,newClearsImagery:true,traceCoordinates:true,traced,expiredSessionExits:true,blocked,errors};
  fs.writeFileSync(path.join(root,`runtime/input-contract/source-session-checks${suffix}.json`),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
