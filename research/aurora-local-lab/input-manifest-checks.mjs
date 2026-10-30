import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {deflateSync} from 'node:zlib';
import {affine,transformPoint,inverseAffine,validateInputManifest,assertInputUse,verifyInputBytes} from './input-manifest.mjs';
const sourceHashes=Object.fromEntries(['input-manifest.mjs','input-manifest-checks.mjs'].map(name=>[name,createHash('sha256').update(readFileSync(new URL(name,import.meta.url))).digest('hex')]));
const NOW=Date.parse('2026-10-30T00:00:00Z'),fetched='2026-10-01T00:00:00Z',expires='2026-11-01T00:00:00Z';
// Procedural RGB checkerboard; PNG encoding uses only Node standard libraries.
function crc32(bytes){let crc=0xffffffff;for(const byte of bytes){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0)}return(crc^0xffffffff)>>>0}
function chunk(type,data){const name=Buffer.from(type),length=Buffer.alloc(4),crc=Buffer.alloc(4);length.writeUInt32BE(data.length);crc.writeUInt32BE(crc32(Buffer.concat([name,data])));return Buffer.concat([length,name,data,crc])}
function gridPng(){
 const header=Buffer.alloc(13);header.writeUInt32BE(64,0);header.writeUInt32BE(48,4);header[8]=8;header[9]=2;
 const raw=Buffer.alloc(48*(1+64*3));
 for(let y=0;y<48;y++)for(let x=0;x<64;x++){
  let color=x%16===0||y%16===0?[50,50,50]:[238,238,238];
  if(x<3&&y<3)color=[255,0,0];if(x>60&&y<3)color=[0,255,0];if(x<3&&y>44)color=[0,0,255];
  const i=y*(1+64*3)+1+x*3;for(let c=0;c<3;c++)raw[i+c]=color[c];
 }
 return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(raw)),chunk('IEND',Buffer.alloc(0))]);
}
const bytes=gridPng(),hash=createHash('sha256').update(bytes).digest('hex');
const permissions={localDisplay:true,derive:true,storeSource:true,storeDerived:true,exportDerived:true,exportSource:true};
const controls=[{pixel:[0,0],editor:[-7.875,5.875]},{pixel:[63,0],editor:[7.875,5.875]},{pixel:[0,47],editor:[-7.875,-5.875]}];
function fixture(){return{schema:'roof-lab-input/v1',inputId:'synthetic-grid-16x12m',frame:{units:'m',pixelReference:'center',crsType:'projected',horizontalCRS:'LOCAL:SYNTHETIC',editorToProjected:[1,0,0,0,1,0],controls:controls.map(c=>({editor:[...c.editor],projected:[...c.editor]}))},elevation:{kind:'not-used'},assets:[{id:'rgb',role:'rgb',mediaType:'image/png',sha256:hash,byteLength:bytes.length,width:64,height:48,pixelToEditor:[.25,0,-7.875,0,-.25,5.875],controls:structuredClone(controls),nodata:{kind:'none'},source:{kind:'synthetic',provider:'generated-locally',permissionReference:'Own input-manifest-checks.mjs fixture generator',originalSha256:hash,isDerivative:false,originalFetchedAt:fetched,originalExpiresAt:null,permissions:{...permissions}}}]}}
const clone=structuredClone;let assertions=0;
function reject(mutator,pattern){const m=fixture();mutator(m);assert.throws(()=>validateInputManifest(m,{now:NOW}),pattern);assertions++;}
const valid=validateInputManifest(fixture(),{now:NOW});assert.equal(valid.effectiveExpiresAt,null);assert.ok(Object.isFrozen(valid.assets[0].source.permissions));assertions++;
assert.throws(()=>assertInputUse(fixture(),'constructor',{now:NOW}),/Unknown source operation/);assertions++;
const matrix=affine(fixture().assets[0].pixelToEditor),inverse=inverseAffine(matrix);
for(const [pixel,expected]of [[[-.5,-.5],[-8,6]],[[63.5,47.5],[8,-6]],[[31.5,23.5],[0,0]]]){assert.deepEqual(transformPoint(matrix,pixel),expected);const back=transformPoint(inverse,expected);assert.ok(Math.hypot(...back.map((n,i)=>n-pixel[i]))<1e-9);assertions++}
const rotated=fixture();rotated.assets[0].pixelToEditor=[0,.25,-5.875,.25,0,-7.875];rotated.assets[0].controls=controls.map(c=>({pixel:c.pixel,editor:[-c.editor[1],c.editor[0]]}));validateInputManifest(rotated,{now:NOW});assert.deepEqual(transformPoint(rotated.assets[0].pixelToEditor,[31.5,23.5]),[0,0]);assertions++;
reject(m=>m.assets[0].pixelToEditor[2]-=.125,/calibration mismatch/);
reject(m=>m.frame.editorToProjected[2]=100,/projected calibration mismatch/);
reject(m=>m.frame.pixelReference='corner',/pixel-center/);
reject(m=>m.frame.units='degrees',/Projected meters/);
reject(m=>m.assets[0].pixelToEditor=[1,2,0,2,4,0],/Singular/);
reject(m=>m.assets[0].controls=[{pixel:[0,0],editor:[-7.875,5.875]},{pixel:[1,0],editor:[-7.625,5.875]},{pixel:[2,0],editor:[-7.375,5.875]}],/non-collinear/);
reject(m=>m.assets[0].source.originalFetchedAt='2026-02-30T00:00:00Z',/Invalid calendar/);
reject(m=>m.assets[0].source.originalFetchedAt='2026-10-01T00:00:00',/time zone/);
reject(m=>m.assets[0].source.originalFetchedAt='2027-01-01T00:00:00Z',/future/);
reject(m=>delete m.assets[0].source.permissions.storeDerived,/Explicit source permissions/);
reject(m=>m.assets[0].source.originalSha256='0'.repeat(64),/hash relationship/);
function external(){const m=fixture(),a=m.assets[0];a.mediaType='image/png';a.source={...a.source,kind:'external',provider:'fictitious-metadata-test',permissionReference:'Fictitious unit-test declaration; no external data',originalExpiresAt:expires};return m}
assert.throws(()=>validateInputManifest({...external(),assets:[{...external().assets[0],source:{...external().assets[0].source,originalExpiresAt:null}}]},{now:NOW}),/expiry required/);assertions++;
assert.throws(()=>validateInputManifest(external(),{now:Date.parse(expires)}),/expired/);assertions++;
const offset=external();offset.assets[0].source.originalExpiresAt='2026-11-01T02:00:00+02:00';assert.equal(validateInputManifest(offset,{now:NOW}).effectiveExpiresAt,expires.replace('Z','.000Z'));assertions++;
const micro=external();micro.assets[0].source.originalExpiresAt='2026-11-01T00:00:00.123456Z';const microChecked=validateInputManifest(micro,{now:NOW});assert.equal(microChecked.effectiveExpiresAt,'2026-11-01T00:00:00.123Z');assert.equal(microChecked.assets[0].source.originalExpiresAt,micro.assets[0].source.originalExpiresAt);assert.throws(()=>assertInputUse(micro,'display',{now:Date.parse('2026-11-01T00:00:00.123Z')}),/expired/);assertions++;
const multi=external(),mask=clone(multi.assets[0]);mask.id='mask';mask.role='mask';mask.source.originalExpiresAt='2026-10-31T00:00:00Z';multi.assets.push(mask);multi.effectiveExpiresAt='2099-01-01T00:00:00Z';assert.equal(validateInputManifest(multi,{now:NOW}).effectiveExpiresAt,'2026-10-31T00:00:00.000Z');assertions++;
const misaligned=clone(multi);misaligned.assets[1].pixelToEditor[2]+=.25;misaligned.assets[1].controls.forEach(c=>c.editor[0]+=.25);assert.throws(()=>validateInputManifest(misaligned,{now:NOW}),/grids must be aligned/);assertions++;
const noSourceExport=external();noSourceExport.assets[0].source.permissions.exportSource=false;assert.throws(()=>assertInputUse(noSourceExport,'export-source',{now:NOW}),/denies export-source/);assertions++;
const denied=external();denied.assets[0].source.permissions.storeDerived=false;assert.throws(()=>assertInputUse(denied,'persist-derived',{now:NOW}),/denies persist-derived/);assertions++;
const dsm=fixture(),height=clone(dsm.assets[0]);height.id='dsm';height.role='dsm';height.mediaType='image/tiff';height.nodata={kind:'nan'};dsm.assets.push(height);assert.throws(()=>validateInputManifest(dsm,{now:NOW}),/DSM elevation/);assertions++;
dsm.elevation={kind:'offset',units:'m',datum:'Synthetic vertical reference',editorOffsetMeters:-100,controls:[{sourceMeters:100,editorMeters:0},{sourceMeters:104,editorMeters:4}]};validateInputManifest(dsm,{now:NOW});dsm.elevation.controls[1].editorMeters=5;assert.throws(()=>validateInputManifest(dsm,{now:NOW}),/Elevation calibration/);assertions++;
await verifyInputBytes(fixture(),new Map([['rgb',bytes]]),{clock:()=>NOW});assertions++;
const changed=Uint8Array.from(bytes);changed[0]^=1;await assert.rejects(verifyInputBytes(fixture(),new Map([['rgb',changed]]),{clock:()=>NOW}),/checksum/);assertions++;
await assert.rejects(verifyInputBytes(fixture(),new Map(),{clock:()=>NOW}),/Exact asset/);assertions++;
const duringHash=fixture();duringHash.assets[0].source.originalExpiresAt=expires;let clockCalls=0;await assert.rejects(verifyInputBytes(duringHash,new Map([['rgb',bytes]]),{clock:()=>clockCalls++?Date.parse(expires):NOW}),/expired/);assertions++;
for(const [name,hash] of Object.entries(sourceHashes))assert.equal(createHash('sha256').update(readFileSync(new URL(name,import.meta.url))).digest('hex'),hash,'Sources changed during checks');
// Write only self-generated fixtures. External-policy tests above are metadata mocks.
const dir=fileURLToPath(new URL('./runtime/input-contract/',import.meta.url));mkdirSync(dir,{recursive:true,mode:0o700});const generated=fixture();generated.assets[0].source.originalFetchedAt=new Date().toISOString();writeFileSync(dir+'grid.png',bytes,{mode:0o600});writeFileSync(dir+'manifest.json',JSON.stringify(generated,null,2),{mode:0o600});writeFileSync(dir+'checks.json',JSON.stringify({assertions,sourceHashes,checkedAt:new Date().toISOString(),externalBytesRead:0,networkRequests:0,imageDecoding:false,editorIntegration:false,scope:'source-free declarations, calibration, expiry and byte identity'},null,2),{mode:0o600});console.log(JSON.stringify({assertions,syntheticExtentMeters:[16,12],fixture:'runtime/input-contract/',externalBytesRead:0,editorIntegration:false}));
