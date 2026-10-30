const assert = require('node:assert/strict');

const CASES = ['fold-sloped-3d', 'fold-vertical-3d', 'two-folds', 'two-dormers', 'fold-height-drag', 'committed-wall-blocks', 'dormer-and-fold', 'cancel-fold', 'cancel-dormer', 'delete-fold', 'delete-dormer', 'move-dormer', 'move-dormer-3d', 'foreign-roof-blocks'];

function snapshot() {
  const point = n => [n.x, n.y, n.z];
  return {
    roofs: window.engine.dataStore.findAllHeirs('roof').map(r => ({
      id: r.id, type: r.type, valid: r.isValid, constructed: r.isConstructed, error: r.error,
      perimeter: (r.perimeterNodes || r.faces[0]?.nodes || []).map(n => [n.x, n.y]),
      edges: (r.perimeterEdges || []).map(e => ({ id: e.id, pitch: e.pitch, height: e.height })),
      folds: (r.kinks || []).map(k => ({ id: k.id, pitch: k.pitch, x: k.x, y: k.y, height: k.height })),
      faces: r.faces.map(f => f.nodes.map(point)),
      walls: window.engine.dataStore.findAll('wall.implicit').filter(w => w.roof === r)
        .map(w => ({ sourceId: w.source?.id || null, nodes: w.nodes.map(point) })),
    })),
    dormers: window.engine.dataStore.findAll('dormer').map(d => ({
      id: d.id, shape: d.shape, pitch: d.pitch, faces: d.faces.map(f => f.nodes.map(point)),
    })),
  };
}

function assertGeometry(value) {
  for (const roof of value.roofs) {
    assert.equal(roof.valid, true, 'Host roof must remain valid');
    assert.equal(roof.constructed, true, 'Host roof must remain constructed');
    assert.ok(!roof.error, 'Host roof must have no geometry error');
    assert.ok(roof.faces.length > 0, 'Host roof must retain faces');
  }
  for (const object of [...value.roofs, ...value.dormers]) {
    for (const face of [...object.faces, ...(object.walls || []).map(w => w.nodes)]) {
      assert.ok(face.length >= 3, 'Face must have at least three corners');
      assert.ok(face.flat().every(Number.isFinite), 'Face coordinates must be finite');
    }
  }
}

function assertSame(actual, expected, location = 'geometry') {
  if (typeof expected === 'number') {
    assert.ok(Number.isFinite(actual) && Math.abs(actual - expected) <= 1e-7,
      `${location}: expected ${expected}, received ${actual}`);
  } else if (expected && typeof expected === 'object') {
    assert.deepEqual(Object.keys(actual), Object.keys(expected), `${location}: structure changed`);
    for (const key of Object.keys(expected)) assertSame(actual[key], expected[key], `${location}.${key}`);
  } else assert.equal(actual, expected, location);
}

async function project(page, point) {
  return page.evaluate(point => {
    const viewport = window.engine.viewportManager.getViewportByName('design-3d');
    const p = viewport.camerasThree.worldSpace.position.clone().set(point.x, point.y, point.z);
    viewport.project(p);
    const rect = viewport.canvas.getBoundingClientRect();
    return { x: rect.left + p.x, y: rect.bottom - p.y };
  }, point);
}

async function place(page, buttonIndex, point, kind) {
  await page.getByTestId('original-roof-options').locator('button').nth(buttonIndex).click();
  await page.waitForFunction(kind => window.engine.subsystems.modeManager.actualStateMode.endsWith(`place.${kind}`), kind);
  await page.waitForTimeout(800);
  const screen = await project(page, point);
  await page.mouse.move(screen.x, screen.y, { steps: 8 });
  await page.waitForTimeout(300);
  await page.evaluate(({ kind, point, screen }) => {
    const mode = window.engine.subsystems.modeManager.getModeObject(`place.${kind}`);
    const edited = mode.model.editedObject;
    window.lab.interactionDebug = {
      kind, point, screen, pointer: mode._getPositionFromMouse?.(), surfacePicking: { ...window.lab.foldSurfacePicking },
      edited: edited && { type: edited.type, id: edited.id, x: edited.x, y: edited.y, pitch: edited.pitch, inBounds: edited.inBounds },
      roof: { valid: mode.model.editedRoof.isValid, constructed: mode.model.editedRoof.isConstructed, error: mode.model.editedRoof.error },
      picks: mode.collisionWorld.getAllMousePicked()?.map(hit => ({
        type: hit.collider?.entity?.model?.type, id: hit.collider?.entity?.model?.id,
        hostFace: mode.model.editedRoof.faces.includes(hit.collider?.entity?.model),
        point: hit.point && { x: hit.point.x, y: hit.point.y, z: hit.point.z },
        wall: hit.collider?.entity?.model?.type === 'wall.implicit' ? (() => {
          const m = hit.collider.entity.model;
          return { keys: Object.keys(m), getters: Object.getOwnPropertyNames(Object.getPrototypeOf(m)),
            sourceKey: m.sourceKey, source: m.source && {id:m.source.id,type:m.source.type},
            roof: m.roof?.id, kink: m.kink?.id,
          };
        })() : undefined,
      })),
    };
  }, { kind, point, screen });
  await page.mouse.click(screen.x, screen.y, { delay: 100 });
  await page.waitForFunction(kind => !window.engine.subsystems.modeManager.actualStateMode.endsWith(`place.${kind}`), kind);
  await page.waitForTimeout(250);
}

async function runInteractionCase(page, name) {
  assert.ok(CASES.includes(name), `Unknown interaction case: ${name}`);
  if (name === 'foreign-roof-blocks') return runForeignRoofCase(page);
  await page.getByRole('button', { name: '2D', exact: true }).click();
  await page.waitForTimeout(800);
  if (!await page.evaluate(() => window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'))) {
    const center = await page.evaluate(() => {
      const face = window.engine.dataStore.findAllHeirs('roof')[0].faces[0];
      return face.nodes.reduce((p, n) => ({ x: p.x + n.x / face.nodes.length, y: p.y + n.y / face.nodes.length, z: p.z + n.z / face.nodes.length }), { x: 0, y: 0, z: 0 });
    });
    const screen = await project(page, center);
    await page.mouse.dblclick(screen.x, screen.y, { delay: 100 });
    await page.waitForFunction(() => window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'));
    await page.waitForTimeout(300);
  }
  const anchors = await page.evaluate(() => {
    const roof = window.engine.dataStore.findAllHeirs('roof')[0];
    const area = f => Math.abs(f.nodes.reduce((sum, n, i) => {
      const next = f.nodes[(i + 1) % f.nodes.length];
      return sum + n.x * next.y - next.x * n.y;
    }, 0));
    const faces = [...roof.faces].sort((a, b) => area(b) - area(a));
    const center = f => f.nodes.reduce((p, n) => ({
      x: p.x + n.x / f.nodes.length, y: p.y + n.y / f.nodes.length, z: p.z + n.z / f.nodes.length,
    }), { x: 0, y: 0, z: 0 });
    const face = faces[0], c = center(face);
    const longest = face.nodes.map((n, i) => [n, face.nodes[(i + 1) % face.nodes.length]])
      .sort(([a, b], [c, d]) => Math.hypot(d.x - c.x, d.y - c.y) - Math.hypot(b.x - a.x, b.y - a.y))[0];
    const offset = sign => ({
      x: c.x + sign * 0.15 * (longest[1].x - longest[0].x),
      y: c.y + sign * 0.15 * (longest[1].y - longest[0].y),
      z: c.z + sign * 0.15 * (longest[1].z - longest[0].z),
    });
    return { center: c, separated: [offset(-1), offset(1)], opposite: center(faces[faces.length - 1]) };
  });
  const initial = await page.evaluate(snapshot);
  const checkpoints = [];
  let beforeHeightDrag;
  let beforeCombinedFold;
  let beforeDeletion;
  let beforeMovement;
  if (['two-dormers', 'dormer-and-fold', 'cancel-dormer', 'delete-dormer', 'move-dormer', 'move-dormer-3d'].includes(name)) {
    for (const [index, shape] of (name === 'two-dormers' ? ['gable', 'hip'] : ['gable']).entries()) {
      await place(page, { gable: 3, hip: 4 }[shape], anchors.separated[index], 'dormer');
      const current = await page.evaluate(snapshot);
      assert.equal(current.dormers.length, index + 1, 'Each placement must add one dormer');
      assert.equal(current.dormers[index].shape, shape);
      assert.equal(current.dormers[index].faces.length, { gable: 2, hip: 3 }[shape]);
      assertGeometry(current);
      checkpoints.push({ dormers: current.dormers.map(d => d.shape) });
    }
    if (name === 'dormer-and-fold') {
      beforeCombinedFold = await page.evaluate(snapshot);
      await place(page, 1, anchors.opposite, 'kink');
      const current = await page.evaluate(snapshot);
      assert.equal(current.dormers.length, 1, 'Fold must retain the existing dormer');
      assert.equal(current.dormers[0].shape, 'gable');
      assert.equal(current.roofs[0].folds.length, 1);
      assert.equal(current.roofs[0].folds[0].pitch, 45);
      assertGeometry(current);
      checkpoints.push({ dormers: ['gable'], folds: [45], faces: current.roofs[0].faces.length });
    }
  } else {
    if (name.endsWith('-3d') || name === 'committed-wall-blocks') {
      await page.getByRole('button', { name: '3D', exact: true }).click();
      await page.waitForTimeout(800);
    }
    const sequence = name === 'two-folds' ? ['sloped', 'sloped'] : [
      name === 'fold-height-drag' ? 'flat' : ['fold-vertical-3d', 'committed-wall-blocks'].includes(name) ? 'vertical' : 'sloped',
    ];
    for (const [index, type] of sequence.entries()) {
      await place(page, { flat: 0, sloped: 1, vertical: 2 }[type], index ? anchors.opposite : anchors.center, 'kink');
      const current = await page.evaluate(snapshot);
      assert.equal(current.roofs[0].folds.length, index + 1, 'Each placement must add one fold');
      assert.equal(current.roofs[0].folds[index].pitch, { flat: 0, sloped: 45, vertical: 90 }[type]);
      assertGeometry(current);
      checkpoints.push({ folds: current.roofs[0].folds.map(k => k.pitch), faces: current.roofs[0].faces.length });
    }
  }
  if (name === 'move-dormer' || name === 'move-dormer-3d') {
    if (name.endsWith('-3d')) {
      await page.getByRole('button', { name: '3D', exact: true }).click();
      await page.waitForTimeout(800);
    }
    beforeMovement = await page.evaluate(snapshot);
    const point = await page.evaluate(() => {
      const d = window.engine.dataStore.findAll('dormer')[0];
      window.engine.triggerAction('selectEntitiesByIds', { entityIds: [d.id] });
      const face = d.faces[0];
      return face.nodes.reduce((p, n) => ({ x: p.x + n.x / face.nodes.length, y: p.y + n.y / face.nodes.length, z: p.z + n.z / face.nodes.length }), { x: 0, y: 0, z: 0 });
    });
    await page.waitForTimeout(300);
    const screen = await project(page, point);
    await page.mouse.move(screen.x, screen.y, { steps: 8 });
    await page.waitForTimeout(150);
    await page.mouse.down();
    await page.waitForTimeout(100);
    await page.mouse.move(screen.x + 25, screen.y, { steps: 15 });
    await page.waitForTimeout(150);
    await page.mouse.up();
    await page.waitForTimeout(500);
    const after = await page.evaluate(snapshot);
    const center = d => {
      const points = d.faces.flat();
      return points.reduce((c, p) => [c[0] + p[0] / points.length, c[1] + p[1] / points.length], [0, 0]);
    };
    assert.equal(after.dormers.length, 1);
    assert.equal(after.dormers[0].id, beforeMovement.dormers[0].id);
    assert.equal(after.dormers[0].shape, 'gable');
    const a = center(beforeMovement.dormers[0]), b = center(after.dormers[0]);
    const distance = Math.hypot(a[0] - b[0], a[1] - b[1]);
    assert.ok(distance > 0.01, 'Pointer drag must move dormer in XY');
    const oldPoints = beforeMovement.dormers[0].faces.flat(), newPoints = after.dormers[0].faces.flat();
    assert.equal(newPoints.length, oldPoints.length, 'Moving must retain dormer topology');
    const delta = newPoints[0].map((value, axis) => value - oldPoints[0][axis]);
    for (let i = 0; i < oldPoints.length; i++) {
      for (let axis = 0; axis < 3; axis++) assert.ok(Math.abs(newPoints[i][axis] - oldPoints[i][axis] - delta[axis]) < 1e-7,
        'Moving on one host plane must translate geometry, not resize it');
    }
    assert.equal(after.dormers[0].pitch, beforeMovement.dormers[0].pitch);
    assertGeometry(after);
    checkpoints.push({ movedDormerMeters: distance, view: name.endsWith('-3d') ? '3d' : '2d' });
  }
  if (name === 'delete-fold' || name === 'delete-dormer') {
    beforeDeletion = await page.evaluate(snapshot);
    const id = name === 'delete-fold' ? beforeDeletion.roofs[0].folds[0].id : beforeDeletion.dormers[0].id;
    await page.evaluate(id => window.engine.triggerAction('selectEntitiesByIds', { entityIds: [id] }), id);
    await page.waitForFunction(id => window.engine.bridge.serializeSelection().some(s => s.data.id === id), id);
    await page.keyboard.press('Delete');
    await page.waitForFunction(kind => kind === 'delete-fold' ? window.engine.dataStore.findAllHeirs('roof')[0].kinks.length === 0 : window.engine.dataStore.findAll('dormer').length === 0, name);
    await page.waitForTimeout(300);
    assertSame(await page.evaluate(snapshot), initial);
    checkpoints.push({ deleted: name === 'delete-fold' ? 'fold' : 'dormer', restoredOriginalRoof: true });
  }
  if (name === 'cancel-fold' || name === 'cancel-dormer') {
    const beforeCancel = await page.evaluate(snapshot);
    const kind = name === 'cancel-fold' ? 'kink' : 'dormer';
    await page.getByTestId('original-roof-options').locator('button').nth(kind === 'kink' ? 0 : 4).click();
    await page.waitForFunction(kind => window.engine.subsystems.modeManager.actualStateMode.endsWith(`place.${kind}`), kind);
    await page.waitForTimeout(800);
    const screen = await project(page, kind === 'kink' ? anchors.opposite : anchors.separated[1]);
    await page.mouse.move(screen.x, screen.y, { steps: 8 });
    await page.waitForTimeout(300);
    const draft = await page.evaluate(snapshot);
    if (kind === 'kink') assert.equal(draft.roofs[0].folds.length, 2, 'Cancellation test must create a fold preview');
    else assert.equal(draft.dormers.length, 2, 'Cancellation test must create a dormer preview');
    await page.keyboard.press('Escape');
    await page.waitForFunction(kind => !window.engine.subsystems.modeManager.actualStateMode.endsWith(`place.${kind}`), kind);
    await page.waitForTimeout(300);
    assertSame(await page.evaluate(snapshot), beforeCancel);
    checkpoints.push({ cancelledPreview: kind, retainedExistingDetail: true });
  }
  if (name === 'fold-height-drag') {
    beforeHeightDrag = await page.evaluate(snapshot);
    const endpoints = await page.evaluate(() => {
      const roof = window.engine.dataStore.findAllHeirs('roof')[0], fold = roof.kinks[0];
      const edge = roof.edges.filter(e => e.faces.length === 2 && e.faces.some(f => f.source === fold))
        .sort((a, b) => b.length - a.length)[0];
      if (!edge) throw new Error('No fold boundary edge found');
      return edge.nodes.map(n => ({ x: n.x, y: n.y, z: n.z }));
    });
    const [a, b] = await Promise.all(endpoints.map(p => project(page, p)));
    const length = Math.hypot(b.x - a.x, b.y - a.y), x = (a.x + b.x) / 2, y = (a.y + b.y) / 2;
    await page.mouse.move(x, y, { steps: 8 });
    await page.waitForTimeout(150);
    await page.mouse.down();
    await page.waitForTimeout(100);
    await page.mouse.move(x - (b.y - a.y) / length * 25, y + (b.x - a.x) / length * 25, { steps: 15 });
    await page.waitForTimeout(150);
    await page.mouse.up();
    await page.waitForTimeout(500);
    const after = await page.evaluate(snapshot);
    assert.ok(Math.abs(after.roofs[0].folds[0].height - beforeHeightDrag.roofs[0].folds[0].height) > 1e-6,
      'Dragging fold boundary must change fold height');
    assertGeometry(after);
    checkpoints.push({ heightBefore: beforeHeightDrag.roofs[0].folds[0].height, heightAfter: after.roofs[0].folds[0].height });
  }
  if (name === 'committed-wall-blocks') {
    const wallPoint = await page.evaluate(() => {
      const roof = window.engine.dataStore.findAllHeirs('roof')[0], fold = roof.kinks[0];
      const wall = window.engine.dataStore.findAll('wall.implicit').find(w => w.roof === roof && w.source?.type === 'edge.perimeter');
      if (!wall) throw new Error('No committed exterior roof wall found');
      const center = wall.nodes.reduce((p, n) => ({ x: p.x + n.x / wall.nodes.length, y: p.y + n.y / wall.nodes.length, z: p.z + n.z / wall.nodes.length }), { x: 0, y: 0, z: 0 });
      const top = [...wall.nodes].sort((a, b) => b.z - a.z)[0];
      const [a, b, c] = wall.nodes;
      const u = { x: b.x - a.x, y: b.y - a.y, z: b.z - a.z }, v = { x: c.x - a.x, y: c.y - a.y, z: c.z - a.z };
      return { x: 0.3 * center.x + 0.7 * top.x, y: 0.3 * center.y + 0.7 * top.y, z: 0.3 * center.z + 0.7 * top.z,
        angle: Math.atan2(u.y * v.z - u.z * v.y, u.z * v.x - u.x * v.z) * 180 / Math.PI };
    });
    const before = await page.evaluate(snapshot);
    await page.getByTestId('original-roof-options').locator('button').first().click();
    await page.waitForFunction(() => window.engine.subsystems.modeManager.actualStateMode.endsWith('place.kink'));
    await page.waitForTimeout(800);
    let blocked, screen;
    for (const angle of [wallPoint.angle, wallPoint.angle + 180]) {
      await page.evaluate(angle => window.labAPI.run('setCameraPosition', { verticalAngle: 20, horizontalAngle: angle }), angle);
      await page.waitForTimeout(800);
      screen = await project(page, wallPoint);
      await page.mouse.move(screen.x, screen.y, { steps: 8 });
      await page.waitForTimeout(300);
      blocked = await page.evaluate(() => {
        const mode = window.engine.subsystems.modeManager.getModeObject('place.kink');
        const hit = mode.collisionWorld.getAllMousePicked().find(h => {
          const m = h.collider?.entity?.model;
          return m && (m.type.startsWith('face.') || m.type.startsWith('wall.')) &&
            !(m.type === 'wall.implicit' && m.source === mode.model.editedObject);
        });
        return { pointer: mode._getPositionFromMouse(), hitsCommittedWall: hit?.collider.entity.model.type === 'wall.implicit' };
      });
      if (blocked.hitsCommittedWall) break;
    }
    assert.equal(blocked.hitsCommittedWall, true, 'Fixture must expose a frontmost committed wall');
    assert.equal(blocked.pointer, null, 'Committed wall must block fold pointer');
    await page.mouse.click(screen.x, screen.y, { delay: 100 });
    await page.waitForFunction(() => !window.engine.subsystems.modeManager.actualStateMode.endsWith('place.kink'));
    await page.waitForTimeout(300);
    assertSame(await page.evaluate(snapshot), before);
    checkpoints.push({ committedWallBlocked: true });
  }
  const completed = await page.evaluate(snapshot);
  checkpoints.push({ hostCorners: initial.roofs[0].perimeter.length,
    committedSurfaceReads: await page.evaluate(() => window.lab.foldSurfacePicking.committedSurfaceReads) });
  assert.deepEqual(completed.roofs[0].perimeter, initial.roofs[0].perimeter, 'Adding details must preserve footprint');
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await page.waitForTimeout(500);
  const undone = await page.evaluate(snapshot);
  if (beforeMovement) assertSame(undone, beforeMovement);
  else if (beforeDeletion) assertSame(undone, beforeDeletion);
  else if (name === 'fold-height-drag') assertSame(undone, beforeHeightDrag);
  else if (name === 'dormer-and-fold') assertSame(undone, beforeCombinedFold);
  else if (name === 'cancel-dormer') assert.equal(undone.dormers.length, 0, 'Cancelled preview must not add an undo step');
  else if (name === 'two-dormers') assert.equal(undone.dormers.length, 1, 'Undo must remove only the second dormer');
  else assert.equal(undone.roofs[0].folds.length, name === 'two-folds' ? 1 : 0, 'Undo must remove only the last fold');
  await page.getByRole('button', { name: 'Redo', exact: true }).click();
  await page.waitForTimeout(500);
  assertSame(await page.evaluate(snapshot), completed);
  await page.evaluate(() => window.labAPI.save());
  const previous = await page.evaluate(() => ({ errors: window.lab.errors, ui: window.lab.originalUi, blocked: window.lab.blocked, drawingEvidence: window.lab.drawingEvidence }));
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.getByRole('button', { name: 'Reopen saved', exact: true }).click(),
  ]);
  await page.waitForFunction(() => window.lab?.stage === 'ready');
  await page.waitForTimeout(600);
  const reopened = await page.evaluate(snapshot);
  assertSame(reopened, completed);
  assertGeometry(reopened);
  await page.evaluate(({ previous, name, checkpoints }) => {
    window.lab.errors.push(...previous.errors);
    window.lab.blocked.push(...previous.blocked);
    window.lab.originalUi.errors.push(...previous.ui.errors);
    window.lab.originalUi.localMetadataRequests.push(...previous.ui.localMetadataRequests);
    if (previous.drawingEvidence) window.lab.drawingEvidence = previous.drawingEvidence;
    window.lab.interactionCase = { name, checkpoints, completed: true, undoRedo: true, roundTrip: true, toleranceMeters: 1e-7 };
  }, { previous, name, checkpoints });
}

async function runForeignRoofCase(page) {
  await page.getByRole('button', { name: '2D', exact: true }).click();
  await page.waitForTimeout(800);
  const host = await page.evaluate(() => {
    const roof = window.engine.dataStore.findAllHeirs('roof')[0];
    const face = roof.faces[0];
    const target = face.nodes.reduce((p, n) => ({ x: p.x + n.x / face.nodes.length, y: p.y + n.y / face.nodes.length, z: p.z + n.z / face.nodes.length }), { x: 0, y: 0, z: 0 });
    return { id: roof.id, target };
  });
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'));
  await page.getByTestId('roof-menu').hover();
  await page.getByTestId('create-smart-roof-flat').click();
  await page.waitForFunction(() => window.engine.subsystems.modeManager.actualStateMode.endsWith('draw.roof'));
  await page.waitForTimeout(800);
  for (const [x, y] of [[400, 160], [700, 160], [700, 280], [400, 280], [400, 160]]) {
    await page.mouse.move(x, y, { steps: 4 });
    await page.waitForTimeout(100);
    await page.mouse.click(x, y, { delay: 100 });
    await page.waitForTimeout(130);
  }
  await page.waitForFunction(() => window.engine.dataStore.findAllHeirs('roof').length === 2 && window.engine.dataStore.findAllHeirs('roof')[1].faces.length > 0);
  const fixture = await page.evaluate(hostId => {
    const roofs = window.engine.dataStore.findAllHeirs('roof');
    const h = roofs.find(r => r.id === hostId), b = roofs.find(r => r.id !== hostId);
    const ys = r => r.perimeterNodes.map(n => n.y);
    return { id: b.id, centerY: ys(b).reduce((a, v) => a + v, 0) / ys(b).length,
      disjoint: Math.max(...ys(b)) < Math.min(...ys(h)) || Math.max(...ys(h)) < Math.min(...ys(b)) };
  }, host.id);
  assert.equal(fixture.disjoint, true, 'Occluder must have a disjoint footprint, not overlap host');
  if (await page.evaluate(() => window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'))) {
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !window.engine.subsystems.modeManager.actualStateMode.endsWith(':roof'));
  }
  await page.evaluate(id => window.engine.triggerAction('selectEntitiesByIds', { entityIds: [id] }), host.id);
  await page.waitForFunction(id => window.engine.bridge.serializeSelection().some(s => s.data.id === id), host.id);
  await page.evaluate(() => window.engine.triggerAction('enterRoofIsolationMode'));
  await page.waitForFunction(id => window.engine.subsystems.modeManager.getModeObject('place.kink').model.editedRoof?.id === id, host.id);
  await page.evaluate(() => window.labAPI.run('setCameraPosition', { verticalAngle: 35, horizontalAngle: 180 }));
  await page.waitForTimeout(900);
  let screen = await project(page, host.target);
  await page.mouse.move(screen.x, screen.y, { steps: 8 });
  await page.waitForTimeout(250);
  const height = await page.evaluate(({ fixture }) => {
    const mode = window.engine.subsystems.modeManager.getModeObject('place.kink');
    const { origin, direction } = mode.collisionWorld.getMouseRay();
    const t = (fixture.centerY - origin.y) / direction.y;
    const height = origin.z + t * direction.z;
    const blocker = window.engine.dataStore.find(fixture.id);
    for (const edge of blocker.perimeterEdges) window.engine.bridge.setModelProperty(edge.id, 'height', height);
    return height;
  }, { fixture });
  assert.ok(Number.isFinite(height) && height > host.target.z + 0.5, 'Fixture must rise above host target ray');
  await page.waitForTimeout(700);
  const before = await page.evaluate(snapshot);
  assertGeometry(before);
  await page.getByTestId('original-roof-options').locator('button').first().click();
  await page.waitForFunction(() => window.engine.subsystems.modeManager.actualStateMode.endsWith('place.kink'));
  await page.waitForTimeout(800);
  screen = await project(page, host.target);
  await page.mouse.move(screen.x, screen.y, { steps: 8 });
  await page.waitForTimeout(300);
  const check = await page.evaluate(blockerId => {
    const mode = window.engine.subsystems.modeManager.getModeObject('place.kink');
    const blocker = window.engine.dataStore.find(blockerId);
    const picks = mode.collisionWorld.getAllMousePicked();
    const first = picks.find(hit => {
      const m = hit.collider?.entity?.model;
      return m && m !== mode.model.editedObject && !m.type.startsWith('edge.') && !m.type.startsWith('node.') &&
        !(m.type === 'wall.implicit' && m.source === mode.model.editedObject);
    });
    const model = first?.collider.entity.model;
    const p = first?.point;
    const nodes = blocker.faces.flatMap(f => f.nodes);
    // Inactive roofs are picked through their derived building mesh. Verify
    // physical ownership against this disjoint rectangular fixture's bounds.
    const bounds = { minX: Math.min(...nodes.map(n => n.x)), maxX: Math.max(...nodes.map(n => n.x)),
      minY: Math.min(...nodes.map(n => n.y)), maxY: Math.max(...nodes.map(n => n.y)), maxZ: Math.max(...nodes.map(n => n.z)) };
    const inForeignPrism = p && p.x >= bounds.minX - 1e-6 && p.x <= bounds.maxX + 1e-6 &&
      p.y >= bounds.minY - 1e-6 && p.y <= bounds.maxY + 1e-6 && p.z >= -1e-6 && p.z <= bounds.maxZ + 1e-6;
    const result = { blockerFrontmost: !!model && !!inForeignPrism && /^(face|wall)\./.test(model.type), bounds,
      frontPoint: p && { x: p.x, y: p.y, z: p.z },
      pointer: mode._getPositionFromMouse(), firstType: model?.type,
      hitTypes: picks.map(h => h.collider?.entity?.model?.type) };
    window.lab.interactionDebug = result;
    return result;
  }, fixture.id);
  assert.equal(check.blockerFrontmost, true, 'Foreign roof must actually be the frontmost hit');
  assert.equal(check.pointer, null, 'Foreign roof must block placement on host behind it');
  await page.mouse.click(screen.x, screen.y, { delay: 100 });
  await page.waitForFunction(() => !window.engine.subsystems.modeManager.actualStateMode.endsWith('place.kink'));
  await page.waitForTimeout(300);
  assertSame(await page.evaluate(snapshot), before);
  await page.evaluate(() => window.labAPI.save());
  const previous = await page.evaluate(() => ({ errors: window.lab.errors, ui: window.lab.originalUi, blocked: window.lab.blocked }));
  await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }), page.getByRole('button', { name: 'Reopen saved', exact: true }).click()]);
  await page.waitForFunction(() => window.lab?.stage === 'ready');
  await page.waitForTimeout(600);
  assertSame(await page.evaluate(snapshot), before);
  await page.evaluate(({ previous, height, check }) => {
    window.lab.errors.push(...previous.errors); window.lab.blocked.push(...previous.blocked);
    window.lab.originalUi.errors.push(...previous.ui.errors);
    window.lab.originalUi.localMetadataRequests.push(...previous.ui.localMetadataRequests);
    window.lab.interactionCase = { name: 'foreign-roof-blocks', completed: true, roundTrip: true, undoRedo: false,
      checkpoints: [{ disjointFootprints: true, blockerHeight: height, foreignRoofBlocked: true,
        frontType: check.firstType, frontPoint: check.frontPoint, blockerBounds: check.bounds }], toleranceMeters: 1e-7 };
  }, { previous, height, check });
}

module.exports = { CASES, runInteractionCase, snapshot, assertSame, place };
