// Local interaction adapter. Retained CAD artifacts remain unchanged.
export function installFoldSurfacePicking(engine) {
  const mode = engine.subsystems.modeManager.getModeObject('place.kink');
  const originalPosition = mode._getPositionFromMouse;
  const originalCanSave = mode.kinkCanBeSaved;
  const originalPlace = mode.place;
  const diagnostics = window.lab.foldSurfacePicking = { surfaceReads: 0, rejectedClicks: 0, committedSurfaceReads: 0 };
  let committedFaces = [];

  mode.place = function (...args) {
    // Keep independent vertex copies: a vertical preview can temporarily remove
    // its host face from live collision geometry while leaving its own wall.
    committedFaces = (this.model.editedRoof?.faces || []).filter(f => !f.holes?.length)
      .map(f => f.nodes.map(n => ({ x: n.x, y: n.y, z: n.z })));
    return originalPlace.apply(this, args);
  };

  function committedSurfaceHit() {
    const { origin, direction } = mode.collisionWorld.getMouseRay();
    let closest = null, closestT = Infinity;
    for (const nodes of committedFaces) {
      let nx = 0, ny = 0, nz = 0;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i], b = nodes[(i + 1) % nodes.length];
        nx += (a.y - b.y) * (a.z + b.z);
        ny += (a.z - b.z) * (a.x + b.x);
        nz += (a.x - b.x) * (a.y + b.y);
      }
      if (!nodes.length || Math.abs(nz) < 1e-10) continue;
      const denominator = nx * direction.x + ny * direction.y + nz * direction.z;
      if (Math.abs(denominator) < 1e-10) continue;
      const a = nodes[0];
      const t = (nx * (a.x - origin.x) + ny * (a.y - origin.y) + nz * (a.z - origin.z)) / denominator;
      if (!Number.isFinite(t) || t < 0 || t >= closestT) continue;
      const p = { x: origin.x + t * direction.x, y: origin.y + t * direction.y, z: origin.z + t * direction.z };
      let inside = false;
      for (let i = 0, j = nodes.length - 1; i < nodes.length; j = i++) {
        const a = nodes[i], b = nodes[j];
        if ((a.y > p.y) !== (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x) inside = !inside;
      }
      if (inside) { closest = p; closestT = t; }
    }
    return closest;
  }

  function isOblique() {
    const ray = mode.collisionWorld.getMouseRay();
    return ray && Math.hypot(ray.direction.x, ray.direction.y) > 1e-6;
  }

  function hostSurfaceHit() {
    const roof = mode.model.editedRoof;
    if (!roof) return null;
    // Respect frontmost scene hit. Never reach through another roof or a wall.
    const picks = mode.collisionWorld.getAllMousePicked() || [];
    const hit = picks.find(hit => {
      const model = hit.collider?.entity?.model;
      // Line and vertex handles are not opaque surfaces. The preview can put
      // its own edge under the pointer while reconstruction updates each frame.
      const previewWall = model?.type === 'wall.implicit' &&
        model.source === mode.model.editedObject;
      return model && model !== mode.model.editedObject &&
        !previewWall && !model.type?.startsWith('edge.') && !model.type?.startsWith('node.');
    });
    if (!hit && picks.some(h => h.collider?.entity?.model?.type === 'wall.implicit' &&
      h.collider.entity.model.source === mode.model.editedObject)) {
      const point = committedSurfaceHit();
      if (point) diagnostics.committedSurfaceReads += 1;
      return point;
    }
    if (!hit || !roof.faces.includes(hit.collider.entity.model)) return null;
    const { x, y, z } = hit.point || {};
    return [x, y, z].every(Number.isFinite) ? { x, y, z } : null;
  }

  mode._getPositionFromMouse = function (...args) {
    if (!isOblique()) return originalPosition.apply(this, args);
    const point = hostSurfaceHit();
    if (!point) return null;
    diagnostics.surfaceReads += 1;
    return this.getSnappedPoint(point);
  };
  mode.kinkCanBeSaved = function (...args) {
    // Moving outside the roof must not commit the last valid preview position.
    if (isOblique() && !hostSurfaceHit()) {
      diagnostics.rejectedClicks += 1;
      return false;
    }
    return originalCanSave.apply(this, args);
  };
}
