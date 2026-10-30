// Transient Google source session. Never writes browser storage or exports a case.
const sourceId=new URLSearchParams(location.search).get('google')||'kimberly';
const sourceQuery='?source='+encodeURIComponent(sourceId);
export async function loadImageryManifest() {
  const response = await fetch('/google-imagery.json'+sourceQuery, { cache: 'no-store' });
  if (!response.ok) throw new Error('Address imagery unavailable. Google API access must be working and imagery acquired first.');
  const manifest = await response.json();
  if (manifest.schema !== 'roof-lab-google-preview/v1' || manifest.provider !== 'Google Solar API' ||
      !Number.isFinite(Date.parse(manifest.expiresAt)) || Date.parse(manifest.expiresAt) <= Date.now() ||
      !Number.isInteger(manifest.width) || !Number.isInteger(manifest.height) ||
      manifest.width <= 0 || manifest.height <= 0 || manifest.width * manifest.height > 4000000 ||
      !Array.isArray(manifest.pixelToEditor) || manifest.pixelToEditor.length !== 6 ||
      !manifest.pixelToEditor.every(Number.isFinite) || !/^[a-f0-9]{64}$/.test(manifest.pngSha256)) {
    throw new Error('Invalid or expired imagery manifest');
  }
  const fetched=Date.parse(manifest.fetchedAt),expires=Date.parse(manifest.expiresAt);
  if(!Number.isFinite(fetched)||fetched>Date.now()+60000||expires>fetched+30*86400000||expires<=fetched)throw new Error('Invalid source lifetime');
  const [a,b,,d,e] = manifest.pixelToEditor;
  // Acquisition reprojects north-up into local meters. Reject unsupported grids.
  if (a <= 0 || e >= 0 || b !== 0 || d !== 0) throw new Error('Unsupported imagery registration');
  return manifest;
}

export async function mountImagery(engine, manifest) {
  const deadline = Date.parse(manifest.expiresAt);
  const assertFresh = () => { if (Date.now() >= deadline) throw new Error('Imagery expired'); };
  assertFresh();
  const response = await fetch('/google-imagery.png'+sourceQuery, { cache: 'no-store' });
  if (!response.ok) throw new Error('Imagery bytes unavailable or expired');
  const bytes = await response.arrayBuffer();
  const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(n => n.toString(16).padStart(2,'0')).join('');
  if (sha !== manifest.pngSha256 || bytes.byteLength !== manifest.byteLength) throw new Error('Imagery checksum mismatch');
  assertFresh();
  const url = URL.createObjectURL(new Blob([bytes], {type:'image/png'}));
  const collection = engine.subsystems.orthoTextureCollection;
  if (collection.groundTextures.length) { URL.revokeObjectURL(url); throw new Error('Existing imagery would be replaced'); }
  const resource = collection.orthoImageResourceFromWorldfile({source:'custom',url,name:'Google Solar imagery',width:manifest.width,height:manifest.height,opacity:1},null);
  const texture = collection.createGroundTexture({id:'google-source-preview',active:true,disabled:false},resource);
  try {
    const origin = collection.deps.bridge.getOriginLatLng();
    const reference = texture.constructor.getDefaultWorldfile(1,1,origin);
    const longitudePerMeter=reference.a/50, latitudePerMeter=-reference.e/50;
    const [a,b,tx,d,e,ty]=manifest.pixelToEditor;
    resource.worldfile={a:a*longitudePerMeter,b:b*longitudePerMeter,c:origin.lng+(tx-(a+b)/2)*longitudePerMeter,
      d:d*latitudePerMeter,e:e*latitudePerMeter,f:origin.lat+(ty-(d+e)/2)*latitudePerMeter};
    texture.initialize();
    const local = texture.localParameters();
    const expected=[tx+(a*(manifest.width-1)+b*(manifest.height-1))/2,ty+(d*(manifest.width-1)+e*(manifest.height-1))/2];
    if (Math.hypot(texture.params.model.x-expected[0],texture.params.model.y-expected[1])>1e-6 ||
        Math.abs(local.dimensions.width-manifest.width*a)>1e-6 || Math.abs(local.dimensions.height+manifest.height*e)>1e-6) throw new Error('Native imagery registration mismatch');
    await collection.loadTexture(texture);
    assertFresh();
    if (!texture.isLoaded) throw new Error('Native imagery decoder failed');
    collection.setGroundTextures([texture]);collection.orthoTextureActivityChanged();
  } catch(error) { URL.revokeObjectURL(url); throw error; }
  // Timers are bounded below browser timeout limits; recheck after tab suspension.
  let timer;
  const check=()=>{
    clearTimeout(timer);
    if(Date.now()>=deadline){document.body.replaceChildren(document.createTextNode('Google imagery session expired. Reopen manual editor to continue.'));location.replace('/');return;}
    timer=setTimeout(check,Math.min(60000,deadline-Date.now()));
  };
  check();document.addEventListener('visibilitychange',check);
  window.addEventListener('pagehide',()=>{clearTimeout(timer);URL.revokeObjectURL(url)},{once:true});
  return {widthMeters:manifest.width*manifest.pixelToEditor[0],heightMeters:-manifest.height*manifest.pixelToEditor[4],center:[texture.params.model.x,texture.params.model.y]};
}
