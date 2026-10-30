// Live display verification reads acquired cache only. Acquisition POST is intercepted.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('/Users/chris/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const cache=path.join(__dirname,'runtime/google-kimberly'),manifest=JSON.parse(fs.readFileSync(path.join(cache,'manifest.json'))),height=JSON.parse(fs.readFileSync(path.join(cache,'height.json')));
 assert.equal(height.expiresAt,manifest.expiresAt);assert.equal(height.imageSha256,manifest.pngSha256);assert.ok(Date.parse(height.expiresAt)>Date.now());
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--disable-background-networking','--disable-component-update','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'}),blocked=[],errors=[];
  await context.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!=='http://127.0.0.1:5191'){blocked.push(u.origin);return route.abort()}if(u.pathname==='/height-acquire')return route.fulfill({json:{ok:true,reused:true}});if(route.request().method()==='POST'){blocked.push(u.pathname);return route.abort()}return route.continue()});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:5191/?google=kimberly');await page.waitForFunction(()=>window.labHeightTools,null,{timeout:30000});await page.locator('#load-heights').click();await page.waitForFunction(()=>window.labHeightTools.isAvailable,null,{timeout:30000});
  await page.locator('#orbit').click();await page.waitForTimeout(1200);
  const result=await page.evaluate(()=>{const c=document.querySelector('#height-cloud'),p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let pixels=0;for(let i=3;i<p.length;i+=4)if(p[i])pixels++;return{samples:labHeightTools.sampleCount,pixels,ground:Number(document.querySelector('#ground-elevation').value),roofs:engine.dataStore.findAllHeirs('roof').length,local:Object.keys(localStorage),session:Object.keys(sessionStorage),errors:lab.errors,csp:lab.blocked}});
  assert.ok(result.samples>1000);assert.ok(result.pixels>1000);assert.ok(Number.isFinite(result.ground));assert.equal(result.roofs,0);assert.deepEqual(result.local,[]);assert.deepEqual(result.session,[]);assert.deepEqual(result.errors,[]);assert.deepEqual(result.csp,[]);assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  await page.screenshot({path:path.join(cache,'preview.png')});fs.chmodSync(path.join(cache,'preview.png'),0o600);
  console.log(JSON.stringify({passed:true,localCacheOnly:true,registeredHeightData:true,display3D:true,modelsUntouched:true,noBrowserStorage:true,noExternalRequests:true,originalExpiryPreserved:true}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
