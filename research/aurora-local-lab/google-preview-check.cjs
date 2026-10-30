// Live check reads acquired local cache only; never calls Google or writes a model.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('/Users/chris/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--disable-background-networking','--disable-component-update','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'}),blocked=[],errors=[];
  await context.route('**/*',route=>{if(new URL(route.request().url()).origin==='http://127.0.0.1:5191')return route.continue();blocked.push(new URL(route.request().url()).origin);return route.abort()});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:5191/?google=kimberly');await page.waitForFunction(()=>window.lab?.imagery?.active,null,{timeout:30000});await page.waitForTimeout(1000);
  const result=await page.evaluate(()=>({loaded:engine.subsystems.orthoTextureCollection.groundTextures[0].isLoaded,active:engine.subsystems.orthoTextureCollection.activeGroundTextures.length,errors:lab.errors,csp:lab.blocked,localStorageKeys:Object.keys(localStorage),sessionStorageKeys:Object.keys(sessionStorage),notice:document.querySelector('#source-notice').textContent}));
  assert.equal(result.loaded,true);assert.equal(result.active,1);assert.deepEqual(result.errors,[]);assert.deepEqual(result.csp,[]);assert.deepEqual(result.localStorageKeys,[]);assert.deepEqual(result.sessionStorageKeys,[]);assert.deepEqual(blocked,[]);assert.deepEqual(errors,[]);
  const cache=path.join(__dirname,'runtime/google-kimberly'),manifest=JSON.parse(fs.readFileSync(path.join(cache,'manifest.json')));
  assert.ok(Date.parse(manifest.expiresAt)>Date.now());
  await page.screenshot({path:path.join(cache,'preview.png')});fs.chmodSync(path.join(cache,'preview.png'),0o600);
  console.log(JSON.stringify({passed:true,imageryLoaded:true,attributionVisible:result.notice.includes('Google Maps'),browserStorageEmpty:true,externalRequests:blocked.length,errors:errors.length}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
