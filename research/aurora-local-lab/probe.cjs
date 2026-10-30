// Dedicated, credential-free browser. Every non-lab request is aborted.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const sourceFiles = ['app.js','frontend-ui.js','fold-placement.js','style.css','probe.cjs','interaction-cases.cjs','case-export.js','index.html','import-case-checks.cjs','reopen-checks.cjs','tab-drafts.js','draft-checks.cjs','roof-property-checks.cjs','roof-type-checks.cjs','roof-move-checks.cjs','roof-explode-checks.cjs','plane-edit-checks.cjs','plane-boundary-checks.cjs','corner-angle-checks.cjs','corner-remove-checks.cjs','corner-add-checks.cjs','edge-length-checks.cjs','manual-authoring-checks.cjs','roof-starter-checks.cjs','view-fit-checks.cjs','rectangle-size-checks.cjs'];
const hashFile = name => createHash('sha256').update(fs.readFileSync(path.join(__dirname,name))).digest('hex');
const sourceHashes = Object.fromEntries(sourceFiles.map(name=>[name,hashFile(name)]));
const useOriginalUi = !process.argv.includes('--prototype');
const flat = process.argv.includes('--flat');
const singleFace = process.argv.includes('--single-face');
const concave = process.argv.includes('--concave');
const manualStarter=process.argv.find(arg=>arg.startsWith('--manual-starter='))?.split('=')[1];
assert.ok(!manualStarter||(['gable','shed'].includes(manualStarter)&&process.argv.includes('--manual-case')&&!process.argv.includes('--demo')),'--manual-starter requires --manual-case, blank start, and gable or shed');
const perimeter = process.argv.includes('--perimeter');
const initialDormer = process.argv.find(arg=>arg.startsWith('--dormer='))?.split('=')[1]||'gable';
const foldAngle = Number(process.argv.find(arg=>arg.startsWith('--angle='))?.split('=')[1]||30);
const outsideFold = process.argv.includes('--outside-fold');
const interactionCase = process.argv.find(arg=>arg.startsWith('--case='))?.slice(7);
const interactionLabel = interactionCase && interactionCase + (concave ? '-concave' : '') + (process.argv.includes('--import-case') ? '-import' : process.argv.includes('--export-case') ? '-export' : '');
const { CASES, runInteractionCase, snapshot: geometrySnapshot, assertSame: assertSameGeometry } = require('./interaction-cases.cjs');
assert.ok(!interactionCase||(CASES.includes(interactionCase)&&(process.argv.includes('--demo')!==concave)&&useOriginalUi),'--case requires known case, either --demo or --concave, and original UI');
assert.ok(['gable','hip','shed'].includes(initialDormer),'Supported dormer placement shapes: gable, hip, shed');
assert.ok(!perimeter||process.argv.includes('--verify'),'--perimeter requires --verify');
assert.ok(Number.isFinite(foldAngle),'Camera angle must be finite');
assert.ok(!outsideFold||process.argv.includes('--ui-fold-3d'),'--outside-fold requires --ui-fold-3d');
const { chromium } = require('/Users/chris/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--disable-background-networking', '--disable-component-update', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'],
  });
  let page,finished=false,verifiedDemo;
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block' });
    const blocked = [], requests = [], consoleErrors = [];
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.origin === 'http://127.0.0.1:5191') {
        requests.push(url.pathname);
        return route.continue();
      }
      blocked.push(url.origin + url.pathname);
      return route.abort('blockedbyclient');
    });
    page = await context.newPage();
    page.setDefaultTimeout(8000);
    page.on('pageerror', error => consoleErrors.push(error.message));
    page.on('response', response => { if (response.status() >= 400) consoleErrors.push(`${response.status()} ${response.url()}`); });
    const query=new URLSearchParams();
    if(process.argv.includes('--demo'))query.set('demo','1');
    if(!useOriginalUi)query.set('prototype','1');
    await page.goto('http://127.0.0.1:5191/?'+query);
    await page.waitForFunction(() => ['ready', 'blocked'].includes(window.lab?.stage), { timeout: 25000 }).catch(() => {});
    if(useOriginalUi){
      await page.waitForFunction(()=>['ready','error'].includes(window.lab?.originalUi?.status),{timeout:15000}).catch(()=>{});
      await page.waitForTimeout(300);
      if(process.argv.includes('--menu')){
        await page.getByTestId('roof-menu').hover();
        console.log(await page.locator('[data-testid]').evaluateAll(nodes=>nodes.map(n=>({id:n.getAttribute('data-testid'),text:n.textContent?.slice(0,100)}))));
      }
      if(process.argv.includes('--demo')&&await page.evaluate(()=>window.lab.originalUi?.status==='ready')){
        const center=await page.evaluate(()=>{
          const viewport=window.engine.viewportManager.getViewportByName('design-3d');
          const face=window.engine.dataStore.findAllHeirs('roof')[0].faces[0];
          const point=viewport.camerasThree.worldSpace.position.clone().set(0,0,0);
          face.nodes.forEach(node=>{point.x+=node.x/face.nodes.length;point.y+=node.y/face.nodes.length;point.z+=node.z/face.nodes.length});
          viewport.project(point);const rect=viewport.canvas.getBoundingClientRect();
          return{x:rect.left+point.x,y:rect.bottom-point.y};
        });
        await page.mouse.move(center.x,center.y,{steps:5});
        await page.mouse.dblclick(center.x,center.y,{delay:100});
        await page.waitForTimeout(350);
        // Selection can consume the first click while the camera settles. Use the
        // visible native inspector action when double-click only selects the roof.
        if (!await page.evaluate(() => window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'))) {
          const edit = page.getByRole('button', { name: 'Edit roof', exact: true });
          if (await edit.count()) await edit.click({timeout:1500}).catch(async error => {
            if (!await page.evaluate(() => window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'))) throw error;
          });
        }
        await page.waitForFunction(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'),null,{timeout:8000});
        await page.locator('#original-ui-root button').first().waitFor();
        await page.waitForTimeout(300);
      }
      if(process.argv.includes('--ui-fields')){
        await page.evaluate(()=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[window.engine.dataStore.findAllHeirs('roof')[0].perimeterEdges[0].id]}));
        await page.waitForFunction(()=>window.engine.state.data.selectionData.perimeterEdges.count>0,{timeout:5000});
        await page.waitForTimeout(600);
        await page.getByTestId('perimeterEdges-pitch').fill('28');
        await page.getByTestId('perimeterEdges-pitch').blur();
        await page.waitForFunction(()=>window.engine.dataStore.findAllHeirs('roof')[0].perimeterEdges[0].pitch===28,{timeout:6000});
        await page.getByTestId('perimeterEdges-height').fill('3.5');
        await page.getByTestId('perimeterEdges-height').blur();
        await page.waitForFunction(()=>window.engine.dataStore.findAllHeirs('roof')[0].perimeterEdges[0].height===3.5,{timeout:6000});
        await page.waitForFunction(()=>Number(document.querySelector('[data-testid="perimeterEdges-slope"]').value)===6.4,{timeout:6000});
        await page.evaluate(()=>window.lab.originalUi.propertyEditsVerified=true);
      }
      if(process.argv.includes('--ui-dormers')){
        const anchor=await page.evaluate(()=>{
          const roof=window.engine.dataStore.findAllHeirs('roof')[0];
          const area=face=>Math.abs(face.nodes.reduce((sum,n,i)=>{const p=face.nodes[(i+1)%face.nodes.length];return sum+n.x*p.y-p.x*n.y},0));
          const face=[...roof.faces].sort((a,b)=>area(b)-area(a))[0];
          return face.nodes.reduce((p,n)=>({x:p.x+n.x/face.nodes.length,y:p.y+n.y/face.nodes.length,z:p.z+n.z/face.nodes.length}),{x:0,y:0,z:0});
        });
        await page.getByTestId('original-roof-options').locator('button').nth({gable:3,hip:4,shed:5}[initialDormer]).click();
        await page.waitForFunction(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith('place.dormer'),{timeout:5000});
        await page.waitForTimeout(800);
        const screen=await page.evaluate(anchor=>{
          const viewport=window.engine.viewportManager.getViewportByName('design-3d');
          const p=viewport.camerasThree.worldSpace.position.clone().set(anchor.x,anchor.y,anchor.z);viewport.project(p);
          const rect=viewport.canvas.getBoundingClientRect();return {x:rect.left+p.x,y:rect.bottom-p.y};
        },anchor);
        await page.mouse.move(screen.x,screen.y,{steps:8});await page.waitForTimeout(250);
        await page.mouse.click(screen.x,screen.y,{delay:100});await page.waitForTimeout(150);
        await page.waitForFunction(({shape,faces})=>window.engine.dataStore.findAll('dormer').some(d=>d.shape===shape&&d.faces.length===faces),{shape:initialDormer,faces:{gable:2,hip:3,shed:1}[initialDormer]},{timeout:5000});
        await page.waitForFunction(()=>!window.engine.subsystems.modeManager.actualStateMode.endsWith('place.dormer'),null,{timeout:6000});
        await page.evaluate(()=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[window.engine.dataStore.findAll('dormer')[0].id]}));
        await page.waitForFunction(()=>window.engine.state.data.selectionData.dormers.count>0,null,{timeout:6000});
        const shapes=[];
        for(const [shape,faces]of (process.argv.includes('--placement-only')?[]:[['hip',3],['shed',1],['gable',2]])){
          await page.locator(`#original-inspector-root [aria-label="${shape}"][aria-checked]`).click();
          await page.waitForFunction(({shape,faces})=>window.engine.dataStore.findAll('dormer')[0].shape===shape&&window.engine.dataStore.findAll('dormer')[0].faces.length===faces,{shape,faces},{timeout:5000});
          await page.locator(`#original-inspector-root [aria-label="${shape}"][aria-checked="true"]`).waitFor();
          shapes.push({shape,faces});
        }
        await page.evaluate(({shapes,initialDormer})=>{window.lab.originalUi.dormersVerified=shapes;window.lab.originalUi.initialDormerVerified=initialDormer;},{shapes,initialDormer});
      }
      if(process.argv.includes('--ui-fold')||process.argv.includes('--ui-fold-fields')||process.argv.includes('--ui-fold-3d')){
        // Place against an unobstructed plan view; a 3D face centroid can be occluded.
        if(!process.argv.includes('--ui-fold-3d'))await page.getByRole('button',{name:'2D',exact:true}).click();
        else await page.evaluate(angle=>window.labAPI.run('setCameraPosition',{verticalAngle:35,horizontalAngle:angle}),foldAngle);
        await page.waitForTimeout(800);
        const anchor=await page.evaluate(oblique=>{
          const faces=window.engine.dataStore.findAllHeirs('roof')[0].faces;
          const area=face=>Math.abs(face.nodes.reduce((sum,n,i)=>{const p=face.nodes[(i+1)%face.nodes.length];return sum+n.x*p.y-p.x*n.y;},0));
          const face=oblique?[...faces].sort((a,b)=>area(b)-area(a))[0]:faces[0];
          return face.nodes.reduce((p,n)=>({x:p.x+n.x/face.nodes.length,y:p.y+n.y/face.nodes.length,z:p.z+n.z/face.nodes.length}),{x:0,y:0,z:0});
        },process.argv.includes('--ui-fold-3d'));
        await page.getByTestId('original-roof-options').locator('button').first().click();
        await page.waitForFunction(()=>window.engine.subsystems.modeManager.actualStateMode.endsWith('place.kink'),null,{timeout:6000});
        await page.waitForTimeout(800);
        const screen=await page.evaluate(anchor=>{
          const viewport=window.engine.viewportManager.getViewportByName('design-3d');
          const p=viewport.camerasThree.worldSpace.position.clone().set(anchor.x,anchor.y,anchor.z);viewport.project(p);
          const rect=viewport.canvas.getBoundingClientRect();return {x:rect.left+p.x,y:rect.bottom-p.y};
        },anchor);
        await page.mouse.move(screen.x,screen.y,{steps:8});await page.waitForTimeout(200);
        if(process.argv.includes('--ui-fold-3d')){
          const diagnostic=await page.evaluate(anchor=>{
            const mode=window.engine.subsystems.modeManager.getModeObject('place.kink');
            const k=mode.model.editedObject,r=mode.model.editedRoof;
            const xyz=p=>p&&{x:p.x,y:p.y,z:p.z};
            const report={anchor,mouse:xyz(mode._getPositionFromMouse()),ray:mode.collisionWorld.getMouseRay(),fold:k&&{x:k.x,y:k.y,height:k.height,inBounds:k.inBounds},roof:{isValid:r.isValid,isConstructed:r.isConstructed,error:r.error},picks:mode.collisionWorld.getAllMousePicked()?.map(hit=>({point:xyz(hit.point),tag:hit.collider?.entity?.tag,type:hit.collider?.entity?.model?.type,id:hit.collider?.entity?.model?.id}))};
            window.lab.foldPlacementDiagnostic=report;return report;
          },anchor);
          assert.equal(diagnostic.fold.inBounds,true,'Preview must lie inside host roof');
          assert.ok(diagnostic.mouse.z>0,'Oblique fold pointer must resolve on elevated roof');
          assert.ok(Math.hypot(diagnostic.fold.x-diagnostic.mouse.x,diagnostic.fold.y-diagnostic.mouse.y)<1e-5,'Preview must track roof-surface pointer');
          if(process.argv.includes('--trace-fold'))console.log('Fold placement diagnostics',JSON.stringify(diagnostic,null,2));
        }
        if(outsideFold){
          await page.mouse.move(850,850,{steps:8});await page.waitForTimeout(200);
          await page.waitForFunction(()=>window.engine.subsystems.modeManager.getModeObject('place.kink')._getPositionFromMouse()===null);
        }
        await page.mouse.click(outsideFold?850:screen.x,outsideFold?850:screen.y,{delay:100});await page.waitForTimeout(150);
        await page.waitForFunction(()=>!window.engine.subsystems.modeManager.actualStateMode.endsWith('place.kink'),null,{timeout:6000});
        const fold=await page.evaluate(()=>{
          const roof=window.engine.dataStore.findAllHeirs('roof')[0];
          const kink=roof.kinks[0];
          return{count:roof.kinks.length,pitch:kink?.pitch,height:kink?.height,faces:roof.faces.length};
        });
        if(outsideFold){
          assert.equal(fold.count,0,'Outside click must discard preview, not commit stale position');
          assert.equal(fold.faces,4,'Rejected fold must restore four original faces');
          assert.ok(await page.evaluate(()=>window.lab.foldSurfacePicking.rejectedClicks)>0);
          await page.evaluate(()=>window.lab.originalUi.outsideFoldRejected=true);
        }else{
          assert.equal(fold.count,1);assert.equal(fold.pitch,0);assert.ok(fold.faces>=5,'Flat fold must produce an additional roof face');
          await page.evaluate(fold=>{window.lab.originalUi.foldVerified=fold;},fold);
        }
        if(process.argv.includes('--ui-fold-fields')){
          await page.evaluate(()=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[window.engine.dataStore.findAllHeirs('roof')[0].kinks[0].id]}));
          const pitchInput=page.locator('#original-inspector-root input[type="number"]').first();
          await pitchInput.fill('10');
          await pitchInput.blur();
          await page.waitForFunction(()=>window.engine.dataStore.findAllHeirs('roof')[0].kinks[0].pitch===10);
          await page.waitForFunction(()=>Number(document.querySelectorAll('#original-inspector-root input[type="number"]')[1].value)===2.1);
          await page.evaluate(()=>window.lab.originalUi.foldEditsVerified={pitch:10,slope:2.1});
        }
      }
    }
    if(process.argv.includes('--ui-dormers')||process.argv.includes('--ui-fold-fields')||(process.argv.includes('--ui-fold-3d')&&!outsideFold)){
      const snapshot=()=>window.engine.dataStore.findAllHeirs('roof').map(r=>({
        id:r.id,faces:r.faces.map(f=>f.nodes.map(n=>[n.x,n.y,n.z])),
        folds:r.kinks.map(k=>({id:k.id,pitch:k.pitch,height:k.height})),
        dormers:window.engine.dataStore.findAll('dormer').map(d=>({id:d.id,shape:d.shape,pitch:d.pitch,faces:d.faces.map(f=>f.nodes.map(n=>[n.x,n.y,n.z]))})),
      }));
      await page.evaluate(()=>window.labAPI.save());
      const before=await page.evaluate(snapshot);
      const previous=await page.evaluate(()=>({ui:window.lab.originalUi,errors:window.lab.errors,diagnostic:window.lab.foldPlacementDiagnostic,surfacePicking:window.lab.foldSurfacePicking}));
      await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);
      await page.waitForFunction(()=>window.lab?.stage==='ready');
      await page.waitForTimeout(600);
      const after=await page.evaluate(snapshot);
      const normalized=v=>JSON.stringify(v,(_,n)=>typeof n==='number'?Math.round(n*1e9)/1e9:n);
      assert.equal(normalized(after),normalized(before),'Dormer/fold source and faces must survive save/reopen');
      await page.evaluate(previous=>{
        const ui=window.lab.originalUi;
        ui.errors.push(...previous.ui.errors);
        ui.localMetadataRequests.push(...previous.ui.localMetadataRequests);
        for(const key of ['dormersVerified','initialDormerVerified','foldVerified','foldEditsVerified'])if(previous.ui[key])ui[key]=previous.ui[key];
        ui.detailRoundTripEqual=true;
        if(previous.diagnostic)window.lab.foldPlacementDiagnostic=previous.diagnostic;
        window.lab.foldPickingBeforeReload=previous.surfacePicking;
        window.lab.errors.push(...previous.errors);
      },previous);
    }
    if (process.argv.includes('--draw') || process.argv.includes('--manual-case') || process.argv.includes('--verify') || flat || singleFace || concave) {
      if(useOriginalUi){
        await page.getByTestId('roof-menu').hover();
        await page.getByTestId(singleFace?'create-roof-face':flat?'create-smart-roof-flat':'create-smart-roof-pitched').click();
      }else await page.getByRole('button', { name: singleFace?'Roof face':flat?'Flat roof':'Pitched roof', exact: true }).click();
      await page.waitForFunction(() => window.engine.subsystems.modeManager.actualStateMode.includes('draw.'));
      // Native tool animates into top view before accepting a stable footprint.
      await page.waitForTimeout(750);
      const corners=concave?[[300,350],[650,350],[650,500],[475,500],[475,650],[300,650]]:[[300,350], [650,350], [650,650], [300,650]];
      for (const [x, y] of corners) {
        await page.mouse.move(x, y, { steps: 3 });
        await page.waitForTimeout(100);
        await page.mouse.click(x, y, { delay: 70 });
        // Native input consumes mouse-up on its next frame; do not race a new move.
        await page.waitForTimeout(100);
      }
      const origin = singleFace?{x:300,y:350}:await page.evaluate(() => {
        const viewport = window.engine.viewportManager.getViewportByName('design-3d');
        const node = window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes[0];
        const point = viewport.camerasThree.worldSpace.position.clone().set(node.x, node.y, 0);
        viewport.project(point);
        const rect = viewport.canvas.getBoundingClientRect();
        return { x: rect.left + point.x, y: rect.bottom - point.y };
      });
      assert.ok(Math.hypot(origin.x-300,origin.y-350)<1,'First roof corner must match the clicked pixel');
      await page.mouse.move(origin.x, origin.y, { steps: 4 });
      await page.waitForTimeout(150);
      await page.mouse.click(origin.x, origin.y, { delay: 70 });
      await page.waitForFunction(() => window.engine.dataStore.findAllHeirs('roof').some(roof => roof.faces.length > 0), { timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(800);
      if(flat||singleFace||concave){
        await page.evaluate(async()=>{
          await window.labAPI.save();
          const saved=JSON.parse(localStorage.getItem('aurora-local-lab:manual-design:v1'));
          window.lab.drawingEvidence={mode:window.engine.subsystems.modeManager.actualStateMode,roofs:saved.site_json.roofs,buildings:saved.site_json.buildings};
        });
        const snapshot=()=>window.engine.dataStore.findAllHeirs('roof').map(r=>({id:r.id,type:r.type,faces:r.faces.map(f=>f.nodes.map(n=>[n.x,n.y,n.z]))}));
        const before=await page.evaluate(snapshot);
        const evidence=await page.evaluate(()=>({drawing:window.lab.drawingEvidence,errors:window.lab.errors,ui:window.lab.originalUi}));
        await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);
        await page.waitForFunction(()=>window.lab?.stage==='ready');
        await page.waitForTimeout(600);
        const after=await page.evaluate(snapshot);
        const normalized=v=>JSON.stringify(v,(_,n)=>typeof n==='number'?Math.round(n*1e9)/1e9:n);
        assert.equal(normalized(after),normalized(before),'Drawn geometry must survive save/reopen');
        await page.evaluate(evidence=>{
          window.lab.drawingEvidence={...evidence.drawing,roundTripEqual:true};
          window.lab.errors.push(...evidence.errors);
          if(evidence.ui){window.lab.originalUi.errors.push(...evidence.ui.errors);window.lab.originalUi.localMetadataRequests.push(...evidence.ui.localMetadataRequests);}
        },evidence);
      }
    }
    if(process.argv.includes('--manual-case'))await require('./manual-authoring-checks.cjs').runManualAuthoringChecks(page,{starter:manualStarter});
    if(interactionCase)await runInteractionCase(page,interactionCase);
    if (process.argv.includes('--verify')) {
      await page.getByLabel('Example name').fill('Synthetic verification roof');
      const drag = await page.evaluate(perimeter => {
        const roof = window.engine.dataStore.findAllHeirs('roof')[0];
        const viewport = window.engine.viewportManager.getViewportByName('design-3d');
        const project = n => {
          const p = viewport.camerasThree.worldSpace.position.clone().set(n.x,n.y,n.z);
          viewport.project(p);
          const rect = viewport.canvas.getBoundingClientRect();
          return { x: rect.left+p.x, y: rect.bottom-p.y };
        };
        const edge = roof.edges.filter(e => e.faces.length === (perimeter?1:2)).sort((a,b) => b.length-a.length)[0];
        const a = project(edge.nodes[0]), b = project(edge.nodes[1]);
        const length = Math.hypot(b.x-a.x,b.y-a.y);
        return { start: {x:(a.x+b.x)/2,y:(a.y+b.y)/2}, shift: {x:-(b.y-a.y)/length*25,y:(b.x-a.x)/length*25},
          footprint: roof.perimeterNodes.map(n => [n.x,n.y]), before: roof.perimeterEdges.map(e => ({id:e.id,pitch:e.pitch,height:e.height})) };
      },perimeter);
      await page.mouse.move(drag.start.x,drag.start.y,{steps:5});
      await page.waitForTimeout(150);
      await page.mouse.down();
      await page.waitForTimeout(80);
      await page.mouse.move(drag.start.x+drag.shift.x,drag.start.y+drag.shift.y,{steps:15});
      await page.waitForTimeout(120);
      await page.mouse.up();
      await page.waitForTimeout(500);
      const afterDrag = await page.evaluate(() => {
        const roof=window.engine.dataStore.findAllHeirs('roof')[0];
        return {footprint:roof.perimeterNodes.map(n=>[n.x,n.y]), edges:roof.perimeterEdges.map(e=>({id:e.id,pitch:e.pitch,height:e.height})),faces:roof.faces.length};
      });
      await page.getByRole('button', {name:'Undo',exact:true}).click();
      await page.waitForTimeout(500);
      const afterUndo = await page.evaluate(() => window.engine.dataStore.findAllHeirs('roof')[0].perimeterEdges.map(e=>({id:e.id,pitch:e.pitch,height:e.height})));
      const maxUndoHeightError = Math.max(...drag.before.map(e => Math.abs(e.height-afterUndo.find(a=>a.id===e.id).height)));
      const footprintPreserved=JSON.stringify(drag.footprint)===JSON.stringify(afterDrag.footprint);
      const dragEvidence = { changed:JSON.stringify(drag.before)!==JSON.stringify(afterDrag.edges)||!footprintPreserved, footprintPreserved, undoRestored:maxUndoHeightError<1e-10 && drag.before.every(e=>afterUndo.some(a=>a.id===e.id&&a.pitch===e.pitch)), maxUndoHeightError, faces:afterDrag.faces, before:drag.before, after:afterDrag.edges, afterUndo };
      await page.getByRole('button',{name:'Redo',exact:true}).click();
      await page.waitForTimeout(500);
      const afterRedo=await page.evaluate(()=>{
        const roof=window.engine.dataStore.findAllHeirs('roof')[0];
        return{footprint:roof.perimeterNodes.map(n=>[n.x,n.y]),edges:roof.perimeterEdges.map(e=>({id:e.id,pitch:e.pitch,height:e.height})),faces:roof.faces.length};
      });
      const normalized=v=>JSON.stringify(v,(_,n)=>typeof n==='number'?Math.round(n*1e9)/1e9:n);
      dragEvidence.redoRestored=normalized(afterRedo)===normalized(afterDrag);
      assert.equal(dragEvidence.redoRestored,true,'Redo must restore dragged geometry');
      await page.getByRole('button',{name:'Undo',exact:true}).click();
      await page.waitForTimeout(500);
      const restoredFootprint=await page.evaluate(()=>window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes.map(n=>[n.x,n.y]));
      assert.equal(normalized(restoredFootprint),normalized(drag.footprint),'Undo must restore footprint');
      await page.evaluate(() => window.engine.triggerAction('selectEntitiesByIds', {entityIds:[window.engine.dataStore.findAllHeirs('roof')[0].perimeterEdges[0].id]}));
      await page.waitForFunction(() => window.engine.bridge.serializeSelection().length > 0);
      if(useOriginalUi){
        await page.getByTestId('perimeterEdges-pitch').fill('30');
        await page.getByTestId('perimeterEdges-pitch').blur();
      }else{
        await page.locator('#pitch').fill('30');
        await page.getByRole('button',{name:'Apply pitch',exact:true}).click();
      }
      await page.waitForFunction(() => window.engine.dataStore.findAllHeirs('roof')[0].perimeterEdges[0].pitch === 30);
      await page.evaluate(async () => {
        await window.labAPI.save();
        const saved = localStorage.getItem('aurora-local-lab:manual-design:v1');
        if (!saved) throw new Error('Native save produced no local data');
        let parsed;
        try { parsed = JSON.parse(saved); } catch {}
        window.lab.saveEvidence = { bytes: saved.length, type: typeof parsed, keys: parsed && typeof parsed === 'object' ? Object.keys(parsed) : [] };
      });
      fs.mkdirSync(path.join(__dirname, 'runtime'), { recursive: true, mode: 0o700 });
      verifiedDemo=await page.evaluate(()=>localStorage.getItem('aurora-local-lab:manual-design:v1'));
      const before = await page.evaluate(() => window.engine.dataStore.findAllHeirs('roof').map(roof => ({ id: roof.id, perimeter: roof.perimeterNodes.map(n => [n.x,n.y]), edges:roof.perimeterEdges.map(e=>({id:e.id,pitch:e.pitch,height:e.height})), faces: roof.faces.length })));
      const saveEvidence = await page.evaluate(() => window.lab.saveEvidence);
      const preReloadErrors = await page.evaluate(() => window.lab.errors);
      const preReloadUi = await page.evaluate(() => window.lab.originalUi);
      const library = await page.evaluate(() => JSON.parse(localStorage.getItem('aurora-local-lab:examples:v1')));
      assert.equal(Object.values(library)[0].name, 'Synthetic verification roof');
      await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button', { name: 'Reopen saved', exact: true }).click()]);
      await page.waitForFunction(() => window.lab?.stage === 'ready');
      await page.waitForTimeout(600);
      const after = await page.evaluate(() => window.engine.dataStore.findAllHeirs('roof').map(roof => ({ id: roof.id, perimeter: roof.perimeterNodes.map(n => [n.x,n.y]), edges:roof.perimeterEdges.map(e=>({id:e.id,pitch:e.pitch,height:e.height})), faces: roof.faces.length })));
      await page.evaluate(({before,after,saveEvidence,dragEvidence,preReloadErrors,preReloadUi}) => {
        const normalized=value=>JSON.stringify(value,(_,v)=>typeof v==='number'?Math.round(v*1e9)/1e9:v);
        window.lab.errors.push(...preReloadErrors);
        window.lab.roundTrip = { before, after, equal: normalized(before) === normalized(after), comparisonPrecisionMeters:1e-9, saveEvidence };
        window.lab.dragEvidence=dragEvidence;
        if(preReloadUi){window.lab.originalUi.errors.push(...preReloadUi.errors);window.lab.originalUi.localMetadataRequests.push(...preReloadUi.localMetadataRequests);}
      }, {before,after,saveEvidence,dragEvidence,preReloadErrors,preReloadUi});
      await page.getByRole('button', { name: '3D', exact: true }).click();
      await page.waitForTimeout(500);
    }
    if(process.argv.includes('--export-case')||process.argv.includes('--import-case')){
      const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Export test case',exact:true}).click()]);
      const target=path.join(__dirname,'runtime','exported-test-case.json');
      await download.saveAs(target);
      const packet=JSON.parse(fs.readFileSync(target,'utf8'));
      assert.equal(packet.schema,'roof-lab-case/v1');
      assert.equal(packet.provenance.engineArtifacts['cad-bundle.js'],'065f6e39575ec8b5bc15ddac809aa7178285e0a90852ebe46a04c16249dcfedb');
      assert.equal(packet.benchmarkCompatible,false);
      assert.equal(packet.coordinates.georeferenced,false);
      assert.equal(packet.nativeDesignSha256,createHash('sha256').update(packet.nativeDesignJson).digest('hex'));
      assert.match(packet.provenance.exporter.algorithmSha256,/^[a-f0-9]{64}$/);
      const native=JSON.parse(packet.nativeDesignJson);
      assert.equal(packet.geometry.buildings.length,native.site_json.buildings.length);
      for(const [i,building]of packet.geometry.buildings.entries()){
        const source=native.site_json.buildings[i];
        assert.equal(building.faces.length,source.faces.length);
        for(const [j,face]of building.faces.entries())assert.deepEqual(face.vertices,source.faces[j].nodes.map(k=>{const n=source.nodes[k];return[n.x,n.y,n.z]}));
      }
      const validations=await page.evaluate(async()=>{
        const {geometryFromNative}=await import('/case-export.js');
        const nodes=[[0,0,3],[10,0,3],[10,10,3],[0,10,3],[3,3,3],[7,3,3],[7,7,3],[3,7,3]].map(([x,y,z])=>({x,y,z}));
        const make=()=>({site_json:{buildings:[{id:'fixture',nodes:structuredClone(nodes),faces:[{nodes:[0,1,2,3],holes:[[4,5,6,7]]}],walls:[]}]}});
        const hole=geometryFromNative(make()).buildings[0].faces[0].holes[0];
        const bad=make();bad.site_json.buildings[0].faces[0].nodes[0]=999;
        let rejectsBadIndex=false;try{geometryFromNative(bad)}catch{rejectsBadIndex=true}
        const nonfinite=make();nonfinite.site_json.buildings[0].nodes[0].z=NaN;
        let rejectsNonfinite=false;try{geometryFromNative(nonfinite)}catch{rejectsNonfinite=true}
        const unknown=make();delete unknown.site_json.buildings[0].faces[0].holes;
        return{hole,rejectsBadIndex,rejectsNonfinite,unknownHolesMarked:!geometryFromNative(unknown).holeTopologyComplete};
      });
      assert.deepEqual(validations.hole,[[3,3,3],[7,3,3],[7,7,3],[3,7,3]]);
      assert.equal(validations.rejectsBadIndex,true);assert.equal(validations.rejectsNonfinite,true);assert.equal(validations.unknownHolesMarked,true);
      const before=await page.evaluate(geometrySnapshot);
      let previous=await page.evaluate(()=>({ui:window.lab.originalUi,errors:window.lab.errors,blocked:window.lab.blocked,
        interactionCase:window.lab.interactionCase,drawingEvidence:window.lab.drawingEvidence,dragEvidence:window.lab.dragEvidence,roundTrip:window.lab.roundTrip}));
      if(process.argv.includes('--import-case')){
        previous=await require('./import-case-checks.cjs').runImportChecks(page,packet);
      }else{
      await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.evaluate(json=>{
        sessionStorage.setItem('aurora-local-lab:reopen',json);location.reload();
      },packet.nativeDesignJson)]);
      }
      await page.waitForFunction(()=>window.lab?.stage==='ready');
      await page.waitForTimeout(700);
      assertSameGeometry(await page.evaluate(geometrySnapshot),before);
      await page.evaluate(({previous,buildings})=>{
        window.lab.errors.push(...previous.errors);window.lab.blocked.push(...previous.blocked);
        if(previous.ui){
          window.lab.originalUi.errors.push(...previous.ui.errors);
          window.lab.originalUi.localMetadataRequests.push(...previous.ui.localMetadataRequests);
          for(const [key,value]of Object.entries(previous.ui))if(!['status','errors','localMetadataRequests'].includes(key))window.lab.originalUi[key]=value;
        }
        for(const key of ['interactionCase','drawingEvidence','dragEvidence','roundTrip'])if(previous[key])window.lab[key]=previous[key];
        window.lab.caseExportVerified={buildings,checksum:true,holeFixture:true,invalidInputsRejected:true,nativeRestored:true};
      },{previous,buildings:packet.geometry.buildings.length});
    }
    if(process.argv.includes('--rectangle-size'))await require('./rectangle-size-checks.cjs').runRectangleSizeChecks(page,{rotated:process.argv.includes('--rotated-size')});
    if(process.argv.includes('--view-fit'))await require('./view-fit-checks.cjs').runViewFitChecks(page);
    if(process.argv.includes('--roof-starter'))await require('./roof-starter-checks.cjs').runRoofStarterChecks(page);
    if(process.argv.includes('--edge-length'))await require('./edge-length-checks.cjs').runEdgeLengthChecks(page);
    if(process.argv.includes('--add-corner'))await require('./corner-add-checks.cjs').runCornerAddChecks(page);
    if(process.argv.includes('--remove-corner'))await require('./corner-remove-checks.cjs').runCornerRemoveChecks(page);
    if(process.argv.includes('--outline-controls')) {
      console.log('Outline APIs',JSON.stringify(await page.evaluate(()=>{
        const r=window.engine.dataStore.findAllHeirs('roof')[0];
        const methods=o=>{const names=[];for(let p=Object.getPrototypeOf(o),i=0;p&&i<5;p=Object.getPrototypeOf(p),i++)names.push(...Object.getOwnPropertyNames(p));return [...new Set(names)].filter(n=>/split|insert|create|delete|remove|add|node/i.test(n))};
        return {roof:methods(r),edge:methods(r.perimeterEdges[0]),node:methods(r.perimeterNodes[0]),canDelete:r.perimeterNodes[0].canDelete,nodeDelete:r.perimeterNodes[0].onDelete.toString(),modeMethods:methods(window.engine.subsystems.modeManager.getModeObject('roof')),modeUpdate:window.engine.subsystems.modeManager.getModeObject('roof').onUpdate?.toString(),drawGesture:window.engine.subsystems.modeManager.getModeObject('roof')._tryEnteringRoofDrawMode?.toString(),deleteGesture:window.engine.subsystems.modeManager.getModeObject('roof')._deletePressed?.toString(),deleteAction:window.engine.subsystems.modeManager.getModeObject('roof').handleDeleteAction?.toString(),
          entities:window.engine.subsystems.entityManager.getEntities(r.perimeterEdges[0]).map(e=>({tag:e.tag,components:e.components.map(c=>({type:c.constructor.getType?.(),methods:Object.getOwnPropertyNames(Object.getPrototypeOf(c)).filter(k=>/click|mouse|node|split/i.test(k)),click:c.onMouseDblClick?.toString()}))}))};
      })));
    }
    if(process.argv.includes('--corner-angle'))await require('./corner-angle-checks.cjs').runCornerAngleChecks(page,{inner:process.argv.includes('--inner-corner')});
    if(process.argv.includes('--corner-controls')) {
      await page.evaluate(()=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes[0].id]}));
      await page.waitForTimeout(600);
      console.log('Corner controls',await page.evaluate(()=>({selected:window.engine.bridge.serializeSelection(),types:window.engine.state.data.inspectorData?.selectedTypes,active:window.engine.state.data.activeTabData,selectionKeys:Object.keys(window.engine.state.data.selectionData),panel:document.querySelector('#original-inspector-root').textContent,angle:window.engine.dataStore.findAllHeirs('roof')[0].perimeterNodes[0].angle})));
    }
    if(process.argv.includes('--edge-controls')) {
      await page.evaluate(()=>window.engine.triggerAction('selectEntitiesByIds',{entityIds:[window.engine.dataStore.findAllHeirs('roof')[0].perimeterEdges[0].id]}));
      await page.getByTestId('perimeterEdges-height').waitFor();
      console.log('Edge controls',await page.locator('#original-inspector-root').evaluate(root=>({text:root.textContent,controls:[...root.querySelectorAll('input,button,select')].map(n=>({tag:n.tagName,testid:n.getAttribute('data-testid'),label:n.getAttribute('aria-label'),text:n.textContent,value:n.value}))})));
    }
    if(process.argv.includes('--roof-explode'))await require('./roof-explode-checks.cjs').runRoofExplodeChecks(page);
    if(process.argv.includes('--plane-boundary'))await require('./plane-boundary-checks.cjs').runPlaneBoundaryChecks(page,{corner:process.argv.includes('--corner')});
    if(process.argv.includes('--plane-edit'))await require('./plane-edit-checks.cjs').runPlaneEditChecks(page);
    if(process.argv.includes('--roof-move'))await require('./roof-move-checks.cjs').runRoofMoveChecks(page,{oblique:process.argv.includes('--move-3d')});
    if(process.argv.includes('--roof-type'))await require('./roof-type-checks.cjs').runRoofTypeChecks(page);
    if(process.argv.includes('--roof-properties'))await require('./roof-property-checks.cjs').runRoofPropertyChecks(page);
    if(process.argv.includes('--audit-controls')) {
      await page.evaluate(() => window.engine.triggerAction('selectEntitiesByIds', {entityIds:[window.engine.dataStore.findAllHeirs('roof')[0].id]}));
      await page.waitForTimeout(700);
      console.log('Roof controls', await page.locator('#original-inspector-root').evaluate(root => ({text:root.textContent,
        controls:[...root.querySelectorAll('button,input,select,[role="radio"],[role="combobox"]')].map(n=>({tag:n.tagName,role:n.getAttribute('role'),testid:n.getAttribute('data-testid'),label:n.getAttribute('aria-label'),text:n.textContent,value:n.value}))})));
    }
    if(process.argv.includes('--recovery'))await require('./reopen-checks.cjs').runReopenChecks(page);
    if(process.argv.includes('--drafts'))await require('./draft-checks.cjs').runDraftChecks(page);
    if(process.argv.includes('--show-help')){await page.locator('#modeling-help summary').click();await page.locator('#modeling-help[open]').waitFor();}
    const result = await page.evaluate(() => ({
      ...window.lab,
      loadStages: window.engine?.loader?._loadingStages.map(({name,state}) => ({name,state})),
      modes: window.engine?.subsystems.modeManager.modes ? [...window.engine.subsystems.modeManager.modes.keys()] : [],
      actions: window.engine?.state?.actions ? Object.fromEntries(Object.entries(window.engine.state.actions).map(([group, actions]) => [group, Object.keys(actions)])) : {},
      stateKeys: window.engine?.state?.data ? Object.keys(window.engine.state.data) : [],
      callbacks: Object.keys(window.engine?.subsystems.engineCallbacks.callbacks || {}),
      actualMode: window.engine?.subsystems.modeManager.actualStateMode,
      roofRecords: window.engine?.dataStore.findAllHeirs('roof').map(roof => ({ id: roof.id, type: roof.type, nodes: roof.nodes?.length, perimeter: roof.perimeterNodes?.map(node => ({ id: node.id, x: node.x, y: node.y })), faces: roof.faces?.length })),
      selected: window.engine?.bridge.serializeSelection(),
      edgeRecords: window.engine?.dataStore.findAllHeirs('roof')[0]?.edges?.map(edge => ({ id: edge.id, type: edge.type, faces: edge.faces?.length, nodes: edge.nodes?.map(n => [n.x,n.y,n.z]) })),
      originalUiButtons:document.querySelectorAll('#original-ui-root button').length,
      propertyPanel:{text:document.querySelector('[data-testid="inspector-drawer"]')?.textContent?.slice(0,1500),fields:[...document.querySelectorAll('#original-inspector-root input')].map(input=>({type:input.type,value:input.value,testid:input.getAttribute('data-testid'),label:input.getAttribute('aria-label')}))},
    }));
    if(process.argv.includes('--inspect-storage'))console.log('Storage integration',await page.evaluate(()=>({
      history:window.engine.state.data.historyData,storage:window.engine.state.data.storageData,
      storeKeys:Object.keys(window.engine.dataStore),signalKeys:Object.keys(window.engine.subsystems.signals),
    })));
    const report = { result, requests, blocked, consoleErrors };
    if(interactionCase)console.log('Interaction case',JSON.stringify(result.interactionCase));
    fs.mkdirSync(path.join(__dirname, 'runtime'), { recursive: true, mode: 0o700 });
    fs.writeFileSync(path.join(__dirname, 'runtime', 'probe.json'), JSON.stringify(report, null, 2), { mode: 0o600 });
    await page.screenshot({ path: path.join(__dirname, 'runtime', 'preview.png') });
    console.log(JSON.stringify({ stage:result.stage,originalUi:result.originalUi,originalUiButtons:result.originalUiButtons,propertyPanel:result.propertyPanel,mode:result.actualMode,roofs:result.roofRecords?.length,faces:result.roofRecords?.map(r=>r.faces),drawing:result.drawingEvidence?{roofCount:result.drawingEvidence.roofs.length,types:result.drawingEvidence.roofs.map(r=>({type:r.type,faces:r.faces?.length,corners:r.perimeter_nodes?.length}))}:undefined,drag:result.dragEvidence?{changed:result.dragEvidence.changed,footprintPreserved:result.dragEvidence.footprintPreserved,undoRestored:result.dragEvidence.undoRestored,maxUndoHeightError:result.dragEvidence.maxUndoHeightError}:undefined,roundTripEqual:result.roundTrip?.equal,failure:result.failure,errors:result.errors,pageErrors:consoleErrors,localRequestCount:requests.length,blocked},null,2));
    assert.equal(result.stage, 'ready');
    assert.equal(result.errors.length, 0);
    assert.deepEqual(result.blocked,[],'CSP must not block unexpected resource requests');
    assert.equal(consoleErrors.length, 0);
    assert.equal(blocked.length, 0);
    assert.ok(!result.events.some(event=>event.label==='Inspector'), 'Inspector must read valid native model types');
    if(useOriginalUi){
      assert.equal(result.originalUi?.status,'ready');
      assert.deepEqual(result.originalUi.errors,[]);
      assert.deepEqual(result.originalUi.localMetadataRequests,[],'All property metadata must resolve locally');
    }
    if (process.argv.includes('--verify')) {
      assert.equal(result.roundTrip.equal,true,'Save/reopen must preserve source geometry');
      assert.equal(result.dragEvidence.changed,true,'Native internal-edge drag must change source elevations');
      assert.equal(result.dragEvidence.footprintPreserved,!perimeter,perimeter?'Perimeter drag must change footprint':'Internal-edge drag must preserve footprint');
      assert.equal(result.dragEvidence.undoRestored,true,'One undo must restore source elevations');
      assert.ok(result.roofRecords[0].faces >= 4,'Native solver must emit roof faces');
    }
    if(flat||singleFace||concave){
      const roofs=singleFace?result.drawingEvidence.buildings:result.drawingEvidence.roofs;
      assert.equal(roofs.length,1,'Drawing must serialize exactly one roof');
      const roof=roofs[0];
      assert.ok(roof.faces.length>0,'Drawing must emit faces');
      assert.ok(roof.nodes.every(n=>[n.x,n.y,n.z].every(Number.isFinite)),'All roof nodes must be finite');
      if(flat){
        assert.equal(roof.faces.length,1,'Flat roof must emit one face');
        assert.equal(roof.faces[0].pitch,0);
        const heights=roof.faces[0].nodes.map(i=>roof.nodes[i].z);
        assert.ok(Math.max(...heights)-Math.min(...heights)<1e-9,'Flat face must be horizontal');
      }
      if(singleFace){
        assert.equal(roof.faces.length,1,'Standalone drawing must emit one face');
        assert.ok(Math.abs(roof.faces[0].pitch-20)<1e-9,'Standalone face must retain initial pitch');
        assert.equal(roof.faces[0].nodes.length,4);
      }
      if(concave){
        assert.equal(roof.perimeter_nodes.length,6,'L footprint must retain six corners');
        const area=nodes=>Math.abs(nodes.reduce((sum,n,i)=>{const p=nodes[(i+1)%nodes.length];return sum+n.x*p.y-p.x*n.y;},0))/2;
        const footprintArea=area(roof.perimeter_nodes);
        const projectedFaceArea=roof.faces.reduce((sum,f)=>sum+area(f.nodes.map(i=>roof.nodes[i])),0);
        assert.ok(Math.abs(footprintArea-projectedFaceArea)<1e-6,'Projected face area must match L footprint');
        result.drawingEvidence.areaCheck={footprintArea,projectedFaceArea};
      }
    }
    const testName=process.argv.includes('--manual-case')?'manual-authoring'+(manualStarter?'-'+manualStarter:''):interactionLabel||((process.argv.includes('--export-case')||process.argv.includes('--import-case'))?`${process.argv.includes('--import-case')?'case-import':'case-export'}${concave?'-concave':singleFace?'-single-face':flat?'-flat':''}`:perimeter?'perimeter':flat?'flat':singleFace?'single-face':concave?'concave':process.argv.includes('--ui-fold-3d')?(outsideFold?'fold-outside':`fold-3d-${foldAngle}`):process.argv.includes('--ui-fold-fields')?'fold-fields':process.argv.includes('--ui-fold')?'fold':process.argv.includes('--ui-dormers')?`dormers-${initialDormer}${process.argv.includes('--placement-only')?'-initial':''}`:process.argv.includes('--ui-fields')?'fields':process.argv.includes('--verify')?'roundtrip':'startup');
    const reportName=testName+(process.argv.includes('--recovery')?'-recovery':'')+(process.argv.includes('--drafts')?'-drafts':'')+(process.argv.includes('--roof-properties')?'-roof-properties':'')+(process.argv.includes('--roof-type')?'-roof-type':'')+(process.argv.includes('--roof-move')?'-roof-move'+(process.argv.includes('--move-3d')?'-3d':''):'')+(process.argv.includes('--roof-explode')?'-roof-explode':'')+(process.argv.includes('--plane-edit')?'-plane-edit':'')+(process.argv.includes('--plane-boundary')?'-plane-boundary'+(process.argv.includes('--corner')?'-corner':''):'')+(process.argv.includes('--corner-angle')?'-corner-angle':'')+(process.argv.includes('--remove-corner')?'-remove-corner':'')+(process.argv.includes('--add-corner')?'-add-corner':'')+(process.argv.includes('--edge-length')?'-edge-length':'')+(process.argv.includes('--roof-starter')?'-roof-starter':'')+(process.argv.includes('--rectangle-size')?'-rectangle-size'+(process.argv.includes('--rotated-size')?'-rotated':''):'')+(process.argv.includes('--view-fit')?'-view-fit'+(result.roofRecords?.length===0?'-empty':''):'');
    const variant=useOriginalUi?'original-ui':'prototype';
    if(interactionCase)assert.equal(result.interactionCase?.completed,true);
    for(const name of sourceFiles)assert.equal(hashFile(name),sourceHashes[name],`${name} changed during verification; rerun against stable sources`);
    const verified={verifiedAt:new Date().toISOString(),testName:reportName,variant,sourceHashes,...report};
    fs.writeFileSync(path.join(__dirname,'runtime',`verified-${variant}-${reportName}.json`),JSON.stringify(verified,null,2),{mode:0o600});
    if(verifiedDemo)fs.writeFileSync(path.join(__dirname,'runtime','demo-design.json'),verifiedDemo,{mode:0o600});
    finished=true;
  } finally {
    if(page&&!finished){
      const failure=await page.evaluate(()=>({stage:window.lab?.stage,cameraFit:window.lab?.cameraFit,viewFitProgress:window.lab?.viewFitProgress,interactionDebug:window.lab?.interactionDebug,ui:window.lab?.originalUi,errors:window.lab?.errors,mode:window.engine?.subsystems.modeManager.actualStateMode,panel:document.querySelector('#original-inspector-root')?.textContent?.slice(0,2000),dormers:window.engine?.dataStore.findAll('dormer').map(d=>({id:d.id,shape:d.shape,faces:d.faces.length})),selection:window.engine?.bridge.serializeSelection()})).catch(()=>({stage:'page-unavailable'}));
      fs.mkdirSync(path.join(__dirname,'runtime'),{recursive:true,mode:0o700});
      fs.writeFileSync(path.join(__dirname,'runtime','failure.json'),JSON.stringify(failure,null,2),{mode:0o600});
      await page.screenshot({path:path.join(__dirname,'runtime','failure.png')}).catch(()=>{});
      console.log('Failure state:',JSON.stringify(failure,null,2));
    }
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
