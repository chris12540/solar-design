// Synthetic display regression: known PNG tones must survive ground rendering.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {createHash} = require('node:crypto'), {execFileSync} = require('node:child_process');
const {chromium} = require('/Users/chris/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const python = '/Users/chris/code/solar-designer/.venv/bin/python';
(async () => {
  const bytes = execFileSync(python, ['-c', 'import numpy as np,sys\nfrom rasterio.io import MemoryFile\na=np.tile(np.repeat(np.array([64,128,192,240],dtype="uint8"),16),(3,48,1))\nwith MemoryFile() as f:\n with f.open(driver="PNG",width=64,height=48,count=3,dtype="uint8") as d:d.write(a)\n sys.stdout.buffer.write(f.read())']);
  const manifest = {schema:'roof-lab-google-preview/v1',provider:'Google Solar API',address:'Synthetic brightness fixture',attribution:'Synthetic fixture',fetchedAt:new Date().toISOString(),expiresAt:new Date(Date.now()+300000).toISOString(),width:64,height:48,pixelToEditor:[1,0,-31.5,0,-1,23.5],pngSha256:createHash('sha256').update(bytes).digest('hex'),byteLength:bytes.length};
  const browser = await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--disable-background-networking','--disable-component-update']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000},serviceWorkers:'block'}), errors = [], blocked = [], legacyWarnings = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => {if(m.type()==='error') {if(/^Feature name does not correctly reference FeatureGate (lidar|editSiteModel|editSystemModel|fillZone|walkway|balanceOfSystem|autoDesigner)$/.test(m.text())) legacyWarnings.push(m.text());else errors.push(m.text())}});
    await page.route('**/*', route => {
      const u = new URL(route.request().url());
      if(u.origin !== 'http://127.0.0.1:5191') {blocked.push(u.origin);return route.abort()}
      if(u.pathname==='/google-imagery.json') return route.fulfill({json:manifest});
      if(u.pathname==='/google-imagery.png') return route.fulfill({body:bytes,contentType:'image/png'});
      if(u.pathname==='/source-cases') return route.fulfill({json:[]});
      if(route.request().method()==='POST') {blocked.push(u.pathname);return route.abort()}
      return route.continue();
    });
    await page.goto('http://127.0.0.1:5191/?google='+'d'.repeat(32));
    await page.waitForFunction(()=>window.labHeightTools);
    await page.evaluate(()=>{for(const id of ['height-tools','original-ui-root','source-notice']) {const element=document.getElementById(id);if(element)element.style.visibility='hidden'}});
    const evidence=[];
    for(const verticalAngle of [90,35]) {
      await page.evaluate(verticalAngle=>labAPI.run('setCameraPosition',{verticalAngle,horizontalAngle:0}),verticalAngle);
      await page.waitForTimeout(900);
      const points = await page.evaluate(()=>[-24,-8,8,24].map(x=>{
        const v=engine.viewportManager.getViewportByName('design-3d'),p=v.camerasThree.worldSpace.position.clone().set(x,-5,0);v.project(p);
        const r=v.canvas.getBoundingClientRect();return [r.left+p.x,r.bottom-p.y];
      }));
      const png=await page.screenshot();
      const actual=JSON.parse(execFileSync(python,['-c','from rasterio.io import MemoryFile\nimport json,sys\nwith MemoryFile(sys.stdin.buffer.read()) as f:\n with f.open() as d:a=d.read()\n print(json.dumps([a[:3,round(y),round(x)].tolist() for x,y in json.loads(sys.argv[1])]))',JSON.stringify(points)],{input:png}).toString());
      for(let i=0;i<4;i++)for(const channel of actual[i])assert.ok(Math.abs(channel-[64,128,192,240][i])<=3,JSON.stringify({verticalAngle,actual,points}));
      evidence.push({verticalAngle,actual});
      if(verticalAngle===90) fs.writeFileSync(path.join(__dirname,'runtime/input-contract/imagery-brightness.png'),png);
    }
    assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
    console.log(JSON.stringify({passed:true,syntheticOnly:true,tonesPreserved2DAnd3D:true,evidence,legacyFeatureWarnings:legacyWarnings.length,noAcquisitions:true}));
  } finally {await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
