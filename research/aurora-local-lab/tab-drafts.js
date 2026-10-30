// Tab-local journal for committed, idle manual edits. Named saves stay separate.
export function installIdleDrafts({ readState, serialize, persist, onError, delay = 1200 }) {
  let generation = 0, paused = false, pending = false, retryAt = 0;
  let savedName = readState().name, observed = '', written = '', changedAt = performance.now();
  const diagnostic = { writes: 0, deferred: 0, lastError: null };
  const key = state => JSON.stringify([state.revision, state.name]);
  async function tick() {
    if (pending || performance.now() < retryAt) return;
    const state = readState(), token = key(state);
    if (paused || !state.ready) { changedAt = performance.now(); diagnostic.deferred++; return; }
    if (token !== observed) { observed = token; changedAt = performance.now(); }
    if ((!state.dirty && state.name === savedName && !written) || token === written || performance.now() - changedAt < delay) return;
    const epoch = generation;
    pending = true;
    try {
      const json = await serialize();
      const current = readState();
      if (paused || epoch !== generation || !current.ready || key(current) !== token) return;
      await persist(json);
      written = token; diagnostic.writes++; diagnostic.lastError = null;
    } catch (error) {
      if (paused || epoch !== generation) return;
      diagnostic.lastError = error.message; retryAt = performance.now() + 15000;
      onError(error);
    } finally { pending = false; }
  }
  const timer = setInterval(tick, 250);
  return {
    diagnostic,
    pause() { paused = true; generation++; },
    resume() { paused = false; changedAt = performance.now(); },
    markSaved() { generation++; savedName = readState().name; written = ''; changedAt = performance.now(); retryAt = 0; diagnostic.lastError = null; },
    dispose() { clearInterval(timer); generation++; paused = true; },
  };
}
