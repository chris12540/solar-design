// Full real local lookup -> existing cache -> editor. No new imagery acquisition.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{createHash}=require('node:crypto');
const {chromium}=require('/Users/chris/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const root=__dirname,files=['address-lookup.js','address-imagery.py','google-imagery.py','server.py','app.js','imagery-session.js','index.html','style.css','address-lookup-checks.cjs'];
 const hashes=()=>Object.fromEntries(files.map(p=>[p,createHash('sha256').update(fs.readFileSync(path.join(root,p))).digest('hex')])),sourceHashes=hashes();
 const manifestPath=path.join(root,'runtime/google-kimberly/manifest.json'),before=fs.readFileSync(manifestPath,'utf8'),manifest=JSON.parse(before);
 assert.ok(Date.parse(manifest.expiresAt)>Date.now());
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--disable-background-networking','--disable-component-update','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'}),blocked=[],errors=[];
  await context.route('**/*',route=>{if(new URL(route.request().url()).origin==='http://127.0.0.1:5191')return route.continue();blocked.push(new URL(route.request().url()).origin);return route.abort()});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:5191/');await page.waitForFunction(()=>window.lab?.stage==='ready');
  assert.equal(await page.locator('#export').textContent(),'Export engine JSON');
  assert.match(await page.locator('#export-case').getAttribute('title'),/editable model/);
  assert.match(await page.locator('#open-case').getAttribute('title'),/Validate and reopen/);
  await page.locator('#google-preview').click();await page.locator('#address-query').fill(manifest.address);
  await page.getByRole('button',{name:'Search',exact:true}).click();
  const load=page.getByRole('button',{name:'Load imagery',exact:true});await load.waitFor({timeout:30000});
  assert.equal(await load.count(),1,'Duplicate dataset parcel rows must collapse');
  await load.click();const link=page.getByRole('link',{name:'Open image editor',exact:true});await link.waitFor({timeout:30000});
  assert.equal(await link.getAttribute('href'),'/?google=kimberly');
  const popupPromise=page.waitForEvent('popup');await link.click();const popup=await popupPromise;popup.on('pageerror',e=>errors.push(e.message));
  await popup.waitForFunction(()=>window.lab?.imagery?.active,null,{timeout:30000});
  assert.equal(await popup.locator('#export-case').isDisabled(),true);assert.equal(await popup.locator('#save').isDisabled(),true);
  assert.equal(fs.readFileSync(manifestPath,'utf8'),before,'Cached source acquisition time and bytes must remain untouched');
  await popup.close();
  // Unmatched local addresses explain coverage without a Google fallback.
  await page.route('**/address-search',route=>route.fulfill({json:{results:[]}}));
  await page.locator('#address-query').fill('Synthetic address outside local records');await page.getByRole('button',{name:'Search',exact:true}).click();
  await page.getByText(/No matching local property record/).waitFor();
  const denied=await page.evaluate(async()=>{
   const headers={'Content-Type':'application/json'};
   const invalid=await fetch('/address-imagery',{method:'POST',headers,body:JSON.stringify({token:'../escape'})});
   const expired=await fetch('/address-imagery',{method:'POST',headers,body:JSON.stringify({token:'a'.repeat(32)})});
   const source=await fetch('/google-imagery.json?source=../escape');
   return[invalid.status,expired.status,source.status];
  });assert.deepEqual(denied,[400,410,400]);
  assert.deepEqual(blocked,[]);assert.deepEqual(errors,[]);assert.deepEqual(hashes(),sourceHashes);
  const result={passed:true,realLocalLookup:true,duplicateParcelsCollapsed:true,existingImageReused:true,separateEditorTab:true,sourceExportStillBlocked:true,localCoverageExplained:true,invalidTokensRejected:true,sourceHashes,blocked,errors};
  fs.writeFileSync(path.join(root,'runtime/input-contract/address-lookup-checks.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
