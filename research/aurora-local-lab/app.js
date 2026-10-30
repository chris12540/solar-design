const sourceId = new URLSearchParams(location.search).get('google');
const sourceSession = sourceId !== null;
const logElement = document.querySelector('#log');
const status = document.querySelector('#status');
const evidence = window.lab = { events: [], errors: [], blocked: [], stage: 'import' };
const SAVE_KEY = 'aurora-local-lab:manual-design:v1';
const LIBRARY_KEY = 'aurora-local-lab:examples:v1';
const ACTIVE_KEY = 'aurora-local-lab:active-example';
const DRAFT_KEY = 'aurora-local-lab:tab-draft:v1';
let drafts, sourceCases;
const readDraft = () => {
  try {
    const record = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || 'null');
    if (!record) return null;
    const model = JSON.parse(record.json);
    return model?.format_version === '3' && model.system_json && typeof model.system_json === 'object' &&
      !Array.isArray(model.system_json) ? record : null;
  } catch { return null; }
};
const clearDraft = () => { sessionStorage.removeItem(DRAFT_KEY); drafts?.markSaved(); };
let activeId = (!sourceSession && sessionStorage.getItem(ACTIVE_KEY)) || crypto.randomUUID();
const readLibrary = () => sourceSession ? {} : JSON.parse(localStorage.getItem(LIBRARY_KEY) || '{}');
let activeProvenance = readLibrary()[activeId]?.importedFrom || null;
function refreshLibrary() {
  const select = document.querySelector('#saved-cases');
  select.replaceChildren(new Option('Saved examples', ''));
  for (const [id, record] of Object.entries(readLibrary())) select.add(new Option(record.name, id));
  if (readLibrary()[activeId]) select.value = activeId;
}
refreshLibrary();
if (readLibrary()[activeId]) document.querySelector('#case-name').value = readLibrary()[activeId].name;
function log(label, value) {
  evidence.events.push({ label, value });
  logElement.textContent += label + ' ' + JSON.stringify(value, null, 2) + '\n';
}
window.addEventListener('error', event => { evidence.errors.push(event.message); log('error', event.message); });
window.addEventListener('unhandledrejection', event => { evidence.errors.push(String(event.reason)); log('rejection', String(event.reason)); });
window.addEventListener('securitypolicyviolation', event => { evidence.blocked.push(event.blockedURI); log('blocked', event.blockedURI); });

class Events {
  listeners = new Map();
  on(name, target, method) {
    const handler = method ? method.bind(target) : target;
    if (!this.listeners.has(name)) this.listeners.set(name, []);
    this.listeners.get(name).push({ target, method, handler });
    return this;
  }
  off(name, target, method) {
    this.listeners.set(name, (this.listeners.get(name) || []).filter(x => x.target !== target || x.method !== method));
    return this;
  }
  trigger(name, ...args) {
    if (/error/i.test(name)) { const values = args.map(x => x?.err?.stack || x?.message || String(x)); evidence.errors.push(...values); log(name, values); }
    for (const { handler } of this.listeners.get(name) || []) handler(...args);
    return this;
  }
}

const { installAddressLookup } = await import('/address-lookup.js');
installAddressLookup();

try {
  const imageryModule = sourceSession ? await import('/imagery-session.js') : null;
  const imageryManifest = sourceSession ? await imageryModule.loadImageryManifest() : null;
  if(sourceSession){const {createSourceCases}=await import('/source-cases.js');sourceCases=await createSourceCases(sourceId,imageryManifest);if(sourceCases.record)document.querySelector('#case-name').value=sourceCases.record.name;}
  let originalUi;
  if(!new URLSearchParams(location.search).has('prototype')){
    try { originalUi=await import('/frontend-ui.js').then(module=>module.prepareOriginalUi()); }
    catch(error){evidence.originalUi={status:'error',errors:[error.stack||error.message]};log('Frontend controls',error.message);}
  }
  let startupJson = !sourceSession && (sessionStorage.getItem('aurora-local-lab:reopen') ||
    (!new URLSearchParams(location.search).has('demo') ? readLibrary()[activeId]?.json : undefined));
  if(sourceSession&&sourceCases.record)startupJson=sourceCases.record.nativeDesignJson;
  if (!sourceSession && !startupJson && new URLSearchParams(location.search).has('demo')) {
    const response = await fetch('/demo.json');
    if (!response.ok) throw new Error('Synthetic demo not generated. Open / for an empty editor.');
    startupJson = await response.text();
    activeId = crypto.randomUUID();
    activeProvenance = null;
    document.querySelector('#case-name').value = 'Synthetic roof demo';
  }
  const identityResponse = await fetch('/health');
  if (!identityResponse.ok) throw new Error('Local engine identity unavailable');
  const engineArtifacts = (await identityResponse.json()).artifacts;
  evidence.engineArtifacts = engineArtifacts;
  const candidate = !sourceSession && readDraft();
  if (!sessionStorage.getItem('aurora-local-lab:reopen') && !new URLSearchParams(location.search).has('demo') &&
      candidate?.schema === 'roof-lab-tab-draft/v1' && typeof candidate.json === 'string' && typeof candidate.caseId === 'string' &&
      ['cad-bundle.js', 'datamodel-api-js.wasm'].every(name => candidate.engineArtifacts?.[name] === engineArtifacts[name])) {
    startupJson = candidate.json; activeId = candidate.caseId;
    activeProvenance = candidate.importedFrom || null;
    refreshLibrary(); document.querySelector('#case-name').value = candidate.name || 'Untitled example';
    evidence.draftRestored = true;
  }
  const { default: cad } = await import('/vendor/cad-bundle.js');
  log('exports', Object.keys(cad));
  const eventEmitter = new Events();
  evidence.notifications = [];
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  eventEmitter.on('notify', notification => {
    const message = { id: notification.id, message: String(notification.message ?? ''),
      title: notification.title ? String(notification.title) : '', type: notification.messageType || 'info' };
    evidence.notifications.push(message);
    status.textContent = [message.title, message.message].filter(Boolean).join(': ');
    log('Notification', message);
  });
  const dataProvider = {
    designId: 'local-synthetic', projectId: 'local-lab', projectType: 'residential',
    design: { id: 'local-synthetic', latitude: 0, longitude: 0 },
    units: { system: { distance: 'metric' }, convert: value => value, unconvert: value => value, format: (value, digits = 2) => Number(value).toFixed(digits) + ' m' },
    distanceUnit: 'm', smallDistanceUnit: 'mm',
    featureGate: {}, selectedImageryTypes: [], lidarAccessible: false,
    peekRecord: () => null, peekAll: () => [],
  };
  const params = {
    stateFramework:originalUi?.stateFramework,
    eventEmitter, mode: 'full', renderMode: 'main', stateMode: 'default-site',
    designModelJson: startupJson,
    useMapView: false, useStreetView: false,
    viewData: [{ name: 'design-3d', domElement: document.querySelector('#viewport'), backgroundColor: '#e9edf0', camera: { verticalAngle: 90 } }],
  };
  if (!sourceSession) sessionStorage.removeItem('aurora-local-lab:reopen');
  const engine = cad.Factory.getEngineInstance('local-synthetic', params);
  if (engine instanceof Error) throw engine;
  window.engine = engine;
  log('constructed', Object.keys(engine.subsystems));
  evidence.stage = 'initialize';
  const saveHandler = { async save({ jsonToSave }) {
    if (sourceSession) {if(window.labHeightTools?.applying)throw new Error('Wait for roof fit to finish before saving.');drafts?.pause();try{const raw=typeof jsonToSave==='string'?jsonToSave:JSON.stringify(jsonToSave);await sourceCases.save(raw,document.querySelector('#case-name').value.trim()||'Untitled example',true);drafts?.markSaved();status.textContent='Source case saved until '+new Date(imageryManifest.expiresAt).toLocaleString();return true;}finally{drafts?.resume();}}
    const json = typeof jsonToSave === 'string' ? jsonToSave : JSON.stringify(jsonToSave);
    const library = readLibrary();
    library[activeId] = { ...(library[activeId] || {}), name: document.querySelector('#case-name').value.trim() || 'Untitled example', json, savedAt: new Date().toISOString(),
      ...(activeProvenance ? { importedFrom: activeProvenance } : {}) };
    localStorage.setItem(LIBRARY_KEY, JSON.stringify(library));
    localStorage.setItem(SAVE_KEY, json);
    sessionStorage.setItem(ACTIVE_KEY, activeId);
    clearDraft();
    if (new URLSearchParams(location.search).has('demo')) {
      const url = new URL(location.href); url.searchParams.delete('demo'); history.replaceState(null, '', url.pathname + url.search);
    }
    refreshLibrary();
    status.textContent = 'Saved on this browser';
    return true;
  } };
  await cad.Factory.initEngineInstance(engine, { eventEmitter, dataProvider, saveHandler, cadUserReactiveInstance:originalUi?.reactiveInstance, locale: 'en-US' });
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  evidence.stage = 'ready';
  status.textContent = 'Engine ready';
  log('ready', true);
  if (sourceSession) {
    const registration = await imageryModule.mountImagery(engine, imageryManifest);
    evidence.imagery = {active:true, registration, expiresAt:imageryManifest.expiresAt};
    document.querySelector('#case-name').value = sourceCases.record?.name||imageryManifest.address;
    document.querySelector('#case-name').readOnly = false;
    const notice = document.createElement('section'); notice.id='source-notice';
    const attribution=document.createElement('span');attribution.textContent='Google Maps';attribution.translate=false;attribution.className='google-attribution';
    const description=document.createElement('span');description.textContent=`${imageryManifest.attribution} · ${imageryManifest.address} · Source case: saves and test packages expire ${new Date(imageryManifest.expiresAt).toLocaleDateString()}. Raw export disabled.`;
    notice.append(attribution,description);document.body.append(notice);
    for(const id of ['export'])document.getElementById(id).disabled=true;
    document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();event.stopImmediatePropagation();window.labAPI?.save().catch(error=>{status.textContent=error.message})}},true);
    document.addEventListener('copy',event=>{event.preventDefault();event.stopImmediatePropagation()},true);
    document.addEventListener('cut',event=>{event.preventDefault();event.stopImmediatePropagation()},true);
    status.textContent='Google imagery loaded — expiry-aware source case';await sourceCases.refresh();
  }
  // Pinned native Focus model types; preserve its whole-scene inclusion policy.
  const focusTypes=['roof','roof.plane','tree','obstruction.circle','obstruction.polygon','obstruction.polyline','solar-panel.free','solar-panel.array','existing-solar-panel.free','drone-mesh'];
  let fitSerial=0;
  async function fitScene(request) {
    const viewport=engine.viewportManager.activeViewport,model=viewport?.cameraModel;
    const controller=model&&engine.subsystems.entityManager.getEntities(model)?.[0]?.getComponent('CameraAnimationController');
    if(controller?.isAnimating)await controller._animatePromise?.catch(()=>{});
    if(request!==fitSerial)return null;
    const camera=viewport?.camerasThree?.worldSpace;
    const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
    const include=p=>{const values=[p?.x,p?.y,p?.z];if(values.every(Number.isFinite))for(let i=0;i<3;i++){min[i]=Math.min(min[i],values[i]);max[i]=Math.max(max[i],values[i]);}};
    for(const type of focusTypes)for(const object of engine.dataStore.findAll(type)){
      const b=object.bounds;if(b){include(b.min);include(b.max);}
    }
    // Include computed roof details/walls even when a source model's box omits them.
    for(const object of [...engine.dataStore.findAllHeirs('roof'),...engine.dataStore.findAll('dormer')])for(const face of object.faces||[])for(const point of face.nodes)include(point);
    for(const wall of engine.dataStore.findAll('wall.implicit'))for(const point of wall.nodes)include(point);
    if(![...min,...max].every(Number.isFinite))return {kind:'empty'};
    if(!camera?.isPerspectiveCamera||!controller||typeof model.positionAtRadiusAndLookat!=='function'){
      engine.triggerAction('focusOnAll');return {kind:'native-fallback'};
    }
    const halfVertical=camera.fov*Math.PI/360,halfHorizontal=Math.atan(Math.tan(halfVertical)*camera.aspect),halfFov=Math.min(halfVertical,halfHorizontal);
    const ratio=model.appliedRadius/model.radius;
    if(!(halfFov>0&&halfFov<Math.PI/2&&ratio>0&&Number.isFinite(ratio)))throw new Error('Camera framing parameters unavailable');
    // Keep native ground-level orbit pivot. Enclose full 3D bounds about that pivot.
    const target=camera.position.clone().set((min[0]+max[0])/2,(min[1]+max[1])/2,0);
    const sphereRadius=Math.hypot((max[0]-min[0])/2,(max[1]-min[1])/2,Math.max(Math.abs(min[2]),Math.abs(max[2])));
    const distance=Math.max(1,sphereRadius/Math.sin(halfFov)*1.1),radius=distance/ratio;
    if(!Number.isFinite(radius)||![target.x,target.y,target.z].every(Number.isFinite))throw new Error('Scene bounds exceed camera framing range');
    await controller.animateCamera(model.positionAtRadiusAndLookat(target,radius),target,model.horizontalAngle);
    return {kind:'height-aware',min,max,distance,verticalAngle:model.verticalAngle,horizontalAngle:model.horizontalAngle};
  }
  const run = (action, payload = {}) => {
    const request=++fitSerial;
    if(action==='focusOnAll'){
      evidence.cameraFit={status:'fitting'};status.textContent='Fitting view…';
      document.querySelector('#viewport').focus();
      return fitScene(request).then(result=>{
        if(request!==fitSerial||!result)return;
        evidence.cameraFit={status:'ready',...result};status.textContent=result.kind==='empty'?'Nothing to fit':'View fitted';
      }).catch(error=>{
        if(request!==fitSerial)return;
        evidence.cameraFit={status:'error',message:error.message};status.textContent='Could not fit view';log('View fit failed',error.message);
      });
    }
    engine.triggerAction(action, payload);
    status.textContent = ({drawPitchedRoof:'Click roof corners',drawFlatRoof:'Click roof corners',drawRoofPlane:'Click face corners',undo:'Undo',redo:'Redo',cancelMode:'Ready',setCameraPosition:'View updated',focusOnAll:'View fitted'})[action] || 'Ready';
    document.querySelector('#viewport').focus();
  };
  window.labAPI = { run, save: () => engine.bridge.save(), cad };
  const { installFoldSurfacePicking } = await import('/fold-placement.js');
  installFoldSurfacePicking(engine);
  if(originalUi)originalUi.mount(engine);
  if(sourceSession){const {installHeightTools}=await import('/height-tools.js');installHeightTools(engine,imageryManifest,sourceId,sourceCases.context);}
  if (new URLSearchParams(location.search).has('demo')) run('setCameraPosition', { verticalAngle: 35, horizontalAngle: 30 });
  for (const button of document.querySelectorAll('[data-action]')) button.onclick = () => run(button.dataset.action);
  for (const button of document.querySelectorAll('[data-dormer]')) button.onclick = () => run('placeDormer', { type: button.dataset.dormer });
  document.querySelector('#top').onclick = () => run('setCameraPosition', { verticalAngle: 90, horizontalAngle: 0 });
  document.querySelector('#orbit').onclick = () => run('setCameraPosition', { verticalAngle: 35, horizontalAngle: 30 });
  document.querySelector('#save').onclick = () => window.labAPI.save().catch(error => log('Save failed', error.message));
  document.querySelector('#reopen').onclick = async () => {
    if(sourceSession){drafts?.pause();const id=document.querySelector('#saved-cases').value||sourceCases.caseId;try{await sourceCases.reopen(id)}catch(error){drafts?.resume();status.textContent=error.message}return;}
    const id = document.querySelector('#saved-cases').value;
    const record = readLibrary()[id];
    const json = record?.json || localStorage.getItem(SAVE_KEY);
    if (!json) { status.textContent = 'No local saved design'; return; }
    const button = document.querySelector('#reopen');
    button.disabled = true;
    drafts?.pause();
    try {
      if (engine.dataStore.findAllHeirs('roof').length) {
        if (record && id === activeId) {
          const value = await engine.bridge.getJsonToSave();
          const current = typeof value === 'string' ? value : JSON.stringify(value);
          const name = document.querySelector('#case-name').value.trim() || 'Untitled example';
          if (current !== record.json || name !== record.name) {
            const library = readLibrary();
            library[crypto.randomUUID()] = { name: name + ' (recovery)', json: current,
              savedAt: new Date().toISOString(), recoveredFrom: activeId,
              ...(activeProvenance ? { importedFrom: activeProvenance } : {}) };
            localStorage.setItem(LIBRARY_KEY, JSON.stringify(library));
          }
        } else await engine.bridge.save();
      }
      clearDraft();
      if (record) sessionStorage.setItem(ACTIVE_KEY, id);
      else sessionStorage.removeItem(ACTIVE_KEY);
      sessionStorage.setItem('aurora-local-lab:reopen', json);
      location.reload();
    } catch (error) { drafts?.resume(); status.textContent = 'Could not preserve current example'; log('Reopen failed', error.message); }
    finally { button.disabled = false; }
  };
  document.querySelector('#new-case').onclick = async () => {
    drafts?.pause();
    try {
      if (sourceSession) {await sourceCases.preserve();location.assign('/?google='+encodeURIComponent(sourceId));return;}
      if (engine.dataStore.findAllHeirs('roof').length) await engine.bridge.save();
      sessionStorage.removeItem(ACTIVE_KEY);
      sessionStorage.removeItem('aurora-local-lab:reopen');
      clearDraft();
      location.assign(new URLSearchParams(location.search).has('prototype')?'/?prototype=1':'/');
    } catch (error) { drafts?.resume(); status.textContent = 'Could not preserve current example'; log('Save failed', error.message); }
  };
  document.querySelector('#export').onclick = async () => {
    if (sourceSession) return;
    const value = await engine.bridge.getJsonToSave();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([typeof value === 'string' ? value : JSON.stringify(value)], { type: 'application/json' }));
    link.download = 'local-roof-example.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  };
  document.querySelector('#apply-pitch').onclick = () => {
    const value = Number(document.querySelector('#pitch').value);
    if (!Number.isFinite(value) || value < 0 || value > 89) return;
    const selection = engine.bridge.serializeSelection();
    for (const item of selection) {
      const model = engine.dataStore.find(item.data.id) || engine.dataStore.findProxy(item.data.id);
      if (model && 'pitch' in model) engine.bridge.setModelProperty(model.id, 'pitch', value);
    }
  };
  document.querySelector('#export-case').onclick = async () => {
    try {
      const { makeTestCase } = await import('/case-export.js');
      const value = await engine.bridge.getJsonToSave();
      const data = sourceSession ? await sourceCases.export(typeof value==='string'?value:JSON.stringify(value),document.querySelector('#case-name').value.trim()||'Untitled example') : await makeTestCase({ nativeDesignJson: typeof value === 'string' ? value : JSON.stringify(value),
        caseId: activeId, engineArtifacts, importedFrom: activeProvenance,
        name: document.querySelector('#case-name').value.trim() || 'Untitled example' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const slug = data.name.normalize('NFKD').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/-+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'roof-case';
      link.download = `${slug}-${activeId.replace(/[^a-zA-Z0-9-]/g, '').slice(0, 64)}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      status.textContent = 'Test case exported';
    } catch (error) { status.textContent = 'Could not export test case'; log('Export failed', error.message); }
  };
  document.querySelector('#open-case').onclick = () => document.querySelector('#case-file').click();
  document.querySelector('#case-file').onchange = async event => {
    const file = event.target.files[0];
    if (!file) return;
    const button = document.querySelector('#open-case');
    button.disabled = true;
    drafts?.pause();
    delete evidence.caseImportError;
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error('Test case exceeds 20 MB');
      const packet=JSON.parse(await file.text());
      if(packet.schema==='roof-lab-case/v2'){const {sourcePacketFromFile,sourceCaseUrl}=await import('/source-cases.js');const opened=await sourcePacketFromFile(packet);if(sourceSession)await sourceCases.preserve();else if(engine.dataStore.findAllHeirs('roof').length)await engine.bridge.save();location.assign(sourceCaseUrl(opened));return;}
      if(sourceSession)throw new Error('Open manual cases from the manual editor; this image session needs a source package.');
      const { validateTestCase } = await import('/case-export.js');
      const opened = await validateTestCase(packet, engineArtifacts);
      if (engine.dataStore.findAllHeirs('roof').length) await engine.bridge.save();
      const importedId = crypto.randomUUID(), library = readLibrary();
      library[importedId] = { name: opened.name, json: opened.nativeDesignJson,
        savedAt: new Date().toISOString(), importedFrom: opened.importedFrom };
      localStorage.setItem(LIBRARY_KEY, JSON.stringify(library));
      sessionStorage.setItem(ACTIVE_KEY, importedId);
      sessionStorage.setItem('aurora-local-lab:reopen', opened.nativeDesignJson);
      clearDraft();
      location.assign(new URLSearchParams(location.search).has('prototype') ? '/?prototype=1' : '/');
    } catch (error) {
      drafts?.resume();
      evidence.caseImportError = error.message;
      status.textContent = 'Could not open test case: ' + error.message;
      log('Import failed', error.message);
    } finally { button.disabled = false; event.target.value = ''; }
  };
  if(sourceSession)document.querySelector('#saved-cases').onchange=async event=>{if(event.target.value)try{drafts?.pause();await sourceCases.switchTo(event.target.value)}catch(error){drafts?.resume();status.textContent=error.message}};
  let pointerEditing = false;
  document.querySelector('#viewport').addEventListener('pointerdown', () => { pointerEditing = true; fitSerial++; }, true);
  document.querySelector('#viewport').addEventListener('wheel', () => { fitSerial++; }, { capture: true, passive: true });
  window.addEventListener('pointerup', () => { pointerEditing = false; }, true);
  window.addEventListener('pointercancel', () => { pointerEditing = false; }, true);
  const { installIdleDrafts } = await import('/tab-drafts.js');
  drafts = installIdleDrafts({
    readState: () => {
      const history = engine.state.data.historyData;
      const mode = engine.subsystems.modeManager.actualStateMode;
      return { revision: history.recentVersion+(sourceSession?JSON.stringify(sourceCases.heightContext()):''), dirty: history.hasUnsavedChanges||(sourceSession&&JSON.stringify(sourceCases.heightContext())!==JSON.stringify(sourceCases.record?.heightContext||{groundElevation:null,heightSha256:null})),
        name: document.querySelector('#case-name').value.trim() || 'Untitled example',
        ready: !window.labHeightTools?.applying && !pointerEditing && (mode.endsWith('default-site') || mode.endsWith(':roof') || mode.endsWith(':move.roof')) && engine.dataStore.findAllHeirs('roof').every(r =>
          r.isValid !== false && r.isConstructed !== false && !r.error && !r.needsReconstruct) };
    },
    // The save-oriented serializer exits roof editing and can add a history entry.
    // Idle drafts must snapshot committed native models without those actions.
    serialize: async () => { const value = engine.bridge.makeDesignJsonToSave(); return typeof value === 'string' ? value : JSON.stringify(value); },
    persist: async json => {
      if(sourceSession){await sourceCases.save(json,document.querySelector('#case-name').value.trim()||'Untitled example',false);status.textContent='Source draft saved until '+new Date(imageryManifest.expiresAt).toLocaleDateString();return;}
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ schema: 'roof-lab-tab-draft/v1', caseId: activeId,
        name: document.querySelector('#case-name').value.trim() || 'Untitled example', json, savedAt: new Date().toISOString(),
        importedFrom: activeProvenance, engineArtifacts }));
      sessionStorage.setItem(ACTIVE_KEY, activeId);
      if (new URLSearchParams(location.search).has('demo')) {
        const url = new URL(location.href); url.searchParams.delete('demo'); history.replaceState(null, '', url.pathname + url.search);
      }
      status.textContent = 'Draft saved in this tab';
    },
    onError: error => { status.textContent = 'Draft could not be saved; use Save locally or Export'; log('Draft save failed', error.message); },
  });
  if(sourceSession)sourceCases.ready=true;
  evidence.tabDrafts = drafts?.diagnostic || {disabledForSourceSession:true};
  if (evidence.draftRestored) status.textContent = 'Recovered draft from this tab';
  setInterval(() => {
    try {
      const roofs = engine.dataStore.findAllHeirs('roof');
      const faces = roofs.reduce((count, roof) => count + roof.faces.length, 0);
      evidence.counts = { roofs: roofs.length, faces };
      document.querySelector('#counts').textContent = `${roofs.length} roofs · ${faces} faces`;
      const selection = engine.bridge.serializeSelection();
      document.querySelector('#selection').textContent = selection.length ? JSON.stringify(selection, null, 2) : 'Select a roof or edge.';
    } catch (error) { log('Inspector', error.message); }
  }, 400);
} catch (error) {
  evidence.stage = 'blocked';
  evidence.failure = { message: error.message, stack: error.stack };
  status.textContent = error.message;
  log('startup failure', evidence.failure);
}
