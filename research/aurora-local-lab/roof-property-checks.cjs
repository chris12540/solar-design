const assert = require('node:assert/strict');
const {snapshot, assertSame} = require('./interaction-cases.cjs');

async function runRoofPropertyChecks(page) {
  const state = () => page.evaluate(() => {
    const roof = window.engine.dataStore.findAllHeirs('roof')[0];
    return {id:roof.id,height:roof.height,stories:roof.stories};
  });
  const original = await state();
  assert.ok(Number.isFinite(original.height));
  await page.evaluate(id => window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}), original.id);
  await page.getByTestId('roofs-height').waitFor();
  const baseline = await page.evaluate(snapshot);
  const delta = 1.25;
  const initialVersion=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
  await page.getByTestId('roofs-height').fill(String(original.height + delta));
  await page.getByTestId('roofs-height').blur();
  await page.waitForFunction(height => window.engine.dataStore.findAllHeirs('roof')[0].height === height, original.height+delta);
  await page.waitForTimeout(500);
  await page.waitForFunction(version=>window.engine.state.data.historyData.recentVersion!==version,initialVersion,{timeout:5000});
  const raised = await page.evaluate(snapshot);
  for (let i=0;i<baseline.roofs.length;i++) {
    const before=baseline.roofs[i], after=raised.roofs[i];
    assertSame(after.perimeter,before.perimeter);
    assert.equal(after.valid,true); assert.ok(!after.error);
    assert.equal(after.faces.length,before.faces.length);
    for(let j=0;j<before.faces.length;j++) for(let k=0;k<before.faces[j].length;k++) {
      const a=after.faces[j][k], b=before.faces[j][k];
      assertSame(a,[b[0],b[1],b[2]+delta], 'raised roof face');
    }
    for(let j=0;j<before.edges.length;j++) {
      assert.equal(after.edges[j].pitch,before.edges[j].pitch);
      assertSame(after.edges[j].height,before.edges[j].height+delta);
    }
  }
  assert.equal(raised.dormers.length,baseline.dormers.length);
  for(let i=0;i<baseline.dormers.length;i++) {
    const before=baseline.dormers[i],after=raised.dormers[i];
    assert.equal(after.shape,before.shape); assert.equal(after.pitch,before.pitch);
    for(let j=0;j<before.faces.length;j++) for(let k=0;k<before.faces[j].length;k++) {
      const b=before.faces[j][k]; assertSame(after.faces[j][k],[b[0],b[1],b[2]+delta],'raised dormer');
    }
  }
  await page.getByRole('button',{name:'Undo',exact:true}).click();
  await page.waitForTimeout(500); assertSame(await page.evaluate(snapshot),baseline);
  assertSame((await state()).height,original.height);
  await page.getByRole('button',{name:'Redo',exact:true}).click();
  await page.waitForTimeout(500); assertSame(await page.evaluate(snapshot),raised);
  await page.evaluate(id => window.engine.triggerAction('selectEntitiesByIds',{entityIds:[id]}), original.id);
  const beforeStories=await state();
  const storiesVersion=await page.evaluate(()=>window.engine.state.data.historyData.recentVersion);
  const stories=2;
  await page.getByTestId('roofs-stories').fill(String(stories));
  await page.getByTestId('roofs-stories').blur();
  await page.waitForFunction(stories=>window.engine.dataStore.findAllHeirs('roof')[0].stories===stories,stories);
  await page.waitForTimeout(500);
  await page.waitForFunction(version=>window.engine.state.data.historyData.recentVersion!==version,storiesVersion,{timeout:5000});
  const storyState=await state(), storyGeometry=await page.evaluate(snapshot);
  assert.ok(storyState.height>beforeStories.height,'Increasing stories must raise roof');
  const storyDelta=storyState.height-beforeStories.height;
  for(let i=0;i<raised.roofs.length;i++) {
    assertSame(storyGeometry.roofs[i].perimeter,raised.roofs[i].perimeter);
    for(let j=0;j<raised.roofs[i].faces.length;j++) for(let k=0;k<raised.roofs[i].faces[j].length;k++) {
      const b=raised.roofs[i].faces[j][k];assertSame(storyGeometry.roofs[i].faces[j][k],[b[0],b[1],b[2]+storyDelta],'stories height propagation');
    }
  }
  await page.getByRole('button',{name:'Undo',exact:true}).click();
  await page.waitForTimeout(500); assertSame((await state()).stories,beforeStories.stories); assertSame(await page.evaluate(snapshot),raised);
  await page.getByRole('button',{name:'Redo',exact:true}).click();
  await page.waitForTimeout(500); assert.equal((await state()).stories,stories); assertSame(await page.evaluate(snapshot),storyGeometry);
  await page.getByRole('button',{name:'Save locally',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Saved'));
  const previous=await page.evaluate(()=>({...window.lab}));
  await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.getByRole('button',{name:'Reopen saved',exact:true}).click()]);
  await page.waitForFunction(()=>window.lab?.stage==='ready',null,{timeout:30000});
  await page.waitForTimeout(500);
  assertSame(await page.evaluate(snapshot),storyGeometry);
  assertSame((await state()).height,storyState.height); assert.equal((await state()).stories,stories);
  await page.evaluate(previous=>{
    window.lab.errors.push(...previous.errors); window.lab.blocked.push(...previous.blocked);
    window.lab.originalUi.errors.push(...previous.originalUi.errors);
    window.lab.originalUi.localMetadataRequests.push(...previous.originalUi.localMetadataRequests);
    for(const key of ['interactionCase','drawingEvidence','dragEvidence','roundTrip','caseImportVerified','caseExportVerified']) if(previous[key])window.lab[key]=previous[key];
    window.lab.roofPropertiesVerified={heightTranslation:true,slopesPreserved:true,attachedDormersTranslated:true,storiesHeightCoupled:true,undoRedo:true,reopen:true,toleranceMeters:1e-7};
  },previous);
}
module.exports={runRoofPropertyChecks};
