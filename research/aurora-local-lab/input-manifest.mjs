// Source-free input contract. No filesystem, network, renderer or persistence access.
const ROLES=new Set(['rgb','dsm','mask']);
const ACTIONS={'display':'localDisplay','derive':'derive','persist-source':'storeSource','persist-derived':'storeDerived','export-derived':'exportDerived','export-source':'exportSource'};
const fail=message=>{throw new Error(message)};
const finite=n=>typeof n==='number'&&Number.isFinite(n);
const text=(v,label)=>{if(typeof v!=='string'||!v.trim()||v.length>500)fail(`Missing or invalid ${label}`);return v};
const digest=v=>{if(typeof v!=='string'||!/^[a-f0-9]{64}$/.test(v))fail('Invalid SHA-256');return v};
function instant(value,label){
  if(typeof value!=='string'||!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)$/.test(value))fail(`Explicit time zone required for ${label}`);
  const match=value.match(/^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)/),[year,month,day,hour,minute,second]=match.slice(1).map(Number);
  const date=new Date(0);date.setUTCFullYear(year,month-1,day);date.setUTCHours(hour,minute,second,0);
  if(date.getUTCFullYear()!==year||date.getUTCMonth()!==month-1||date.getUTCDate()!==day||date.getUTCHours()!==hour||date.getUTCMinutes()!==minute||date.getUTCSeconds()!==second)fail(`Invalid calendar date for ${label}`);
  // JS milliseconds truncate finer source fractions; originals stay intact and expiry is conservative.
  const result=Date.parse(value);if(!Number.isFinite(result))fail(`Invalid ${label}`);return result;
}
export function affine(value){
  if(!Array.isArray(value)||value.length!==6||!value.every(finite))fail('Six finite affine coefficients required');
  const [a,b,,d,e]=value,scale=Math.hypot(a,d)*Math.hypot(b,e),det=a*e-b*d;
  if(!finite(scale)||!finite(det)||scale<=0||Math.abs(det)/scale<1e-10)fail('Singular or nearly parallel affine axes');
  return [...value];
}
export function transformPoint(matrix,point){
  if(!Array.isArray(point)||point.length!==2||!point.every(finite))fail('Finite XY point required');
  const [a,b,c,d,e,f]=matrix,[x,y]=point,result=[a*x+b*y+c,d*x+e*y+f];if(!result.every(finite))fail('Transform range exceeded');return result;
}
export function inverseAffine(matrix){
  const [a,b,c,d,e,f]=affine(matrix),det=a*e-b*d;
  return affine([e/det,-b/det,(b*f-e*c)/det,-d/det,a/det,(d*c-a*f)/det]);
}
const near=(a,b,tolerance=1e-6)=>Math.hypot(...a.map((v,i)=>v-b[i]))<=tolerance;
function calibration(points,matrix,width,height){
  if(!Array.isArray(points)||points.length<3||points.length>100)fail('At least three calibration controls required');
  for(const p of points){
    if(!Array.isArray(p.pixel)||p.pixel.length!==2||!p.pixel.every(finite)||p.pixel[0]<-.5||p.pixel[0]>width-.5||p.pixel[1]<-.5||p.pixel[1]>height-.5)fail('Calibration pixel outside raster');
    if(!Array.isArray(p.editor)||p.editor.length!==2||!p.editor.every(finite)||!near(transformPoint(matrix,p.pixel),p.editor))fail('Pixel/editor calibration mismatch');
  }
  const a=points[0].pixel;let independent=false;
  for(let i=1;i<points.length;i++)for(let j=i+1;j<points.length;j++){
    const b=points[i].pixel,c=points[j].pixel;if(Math.abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))>1e-8)independent=true;
  }
  if(!independent)fail('Calibration controls must be non-collinear');
}
function deepFreeze(value){if(value&&typeof value==='object'){for(const child of Object.values(value))deepFreeze(child);Object.freeze(value)}return value}
export function validateInputManifest(manifest,{now=Date.now()}={}){
  if(!finite(now))fail('Finite validation clock required');
  if(manifest?.schema!=='roof-lab-input/v1')fail('Unsupported input manifest');
  text(manifest.inputId,'input identity');
  const frame=manifest.frame;
  if(frame?.units!=='m'||frame.pixelReference!=='center'||frame.crsType!=='projected')fail('Projected meters and pixel-center convention required');
  text(frame.horizontalCRS,'declared horizontal CRS');affine(frame.editorToProjected);
  if(!Array.isArray(frame.controls)||frame.controls.length<3||frame.controls.length>100)fail('Projected calibration controls required');
  for(const c of frame.controls)if(!Array.isArray(c.editor)||c.editor.length!==2||!c.editor.every(finite)||!Array.isArray(c.projected)||c.projected.length!==2||!c.projected.every(finite)||!near(transformPoint(frame.editorToProjected,c.editor),c.projected))fail('Editor/projected calibration mismatch');
  const origin=frame.controls[0].editor;let independent=false;
  for(let i=1;i<frame.controls.length;i++)for(let j=i+1;j<frame.controls.length;j++){const b=frame.controls[i].editor,c=frame.controls[j].editor;if(Math.abs((b[0]-origin[0])*(c[1]-origin[1])-(b[1]-origin[1])*(c[0]-origin[0]))>1e-8)independent=true;}
  if(!independent)fail('Projected controls must be non-collinear');
  if(!Array.isArray(manifest.assets)||!manifest.assets.length||manifest.assets.length>8)fail('Input assets required');
  const ids=new Set(),roles=new Set();let expiry=Infinity,reference;
  for(const asset of manifest.assets){
    text(asset.id,'asset identity');if(ids.has(asset.id))fail('Duplicate asset identity');ids.add(asset.id);
    if(!ROLES.has(asset.role)||roles.has(asset.role))fail('Unsupported or duplicate raster role');roles.add(asset.role);digest(asset.sha256);
    if(!Number.isSafeInteger(asset.byteLength)||asset.byteLength<=0)fail('Positive asset byte count required');
    if(!Number.isSafeInteger(asset.width)||!Number.isSafeInteger(asset.height)||asset.width<=0||asset.height<=0||asset.width>32768||asset.height>32768)fail('Unsupported raster dimensions');
    text(asset.mediaType,'media type');
    const formats=asset.role==='rgb'?['image/png','image/jpeg','image/svg+xml']:asset.role==='dsm'?['image/tiff']:['image/png','image/tiff'];
    if(!formats.includes(asset.mediaType))fail('Unsupported raster media type');
    const matrix=affine(asset.pixelToEditor);calibration(asset.controls,matrix,asset.width,asset.height);
    if(!['none','value','nan'].includes(asset.nodata?.kind)||(asset.nodata.kind==='value'&&!finite(asset.nodata.value)))fail('Explicit nodata convention required');
    if(reference&&(asset.width!==reference.width||asset.height!==reference.height||!matrix.every((v,i)=>Math.abs(v-reference.pixelToEditor[i])<=1e-9)))fail('Raster grids must be aligned before integration');reference??=asset;
    const source=asset.source;if(!['synthetic','external'].includes(source?.kind))fail('Source kind required');text(source.provider,'provider');
    if(source.kind==='synthetic'&&source.provider!=='generated-locally')fail('Synthetic source provider inconsistent');
    if(source.kind==='external'&&asset.mediaType==='image/svg+xml')fail('External SVG input unsupported');
    text(source.permissionReference,'permission reference');digest(source.originalSha256);
    if(typeof source.isDerivative!=='boolean'||(!source.isDerivative&&source.originalSha256!==asset.sha256))fail('Original/current hash relationship inconsistent');
    const fetched=instant(source.originalFetchedAt,'original acquisition');if(fetched>now)fail('Acquisition cannot be in the future');
    if(source.originalExpiresAt==null){if(source.kind!=='synthetic')fail('External source expiry required')}
    else{const end=instant(source.originalExpiresAt,'original expiry');if(end<=fetched)fail('Expiry must follow acquisition');if(end<=now)fail('Source expired');expiry=Math.min(expiry,end)}
    for(const key of Object.values(ACTIONS))if(typeof source.permissions?.[key]!=='boolean')fail('Explicit source permissions required');
  }
  if(!roles.has('rgb'))fail('RGB background required');
  if(roles.has('dsm')){
    const elevation=manifest.elevation;if(elevation?.units!=='m'||elevation?.kind!=='offset'||!finite(elevation.editorOffsetMeters))fail('DSM elevation mapping required');text(elevation.datum,'elevation datum');
    if(!Array.isArray(elevation.controls)||elevation.controls.length<2||elevation.controls.some(c=>!finite(c.sourceMeters)||!finite(c.editorMeters)||Math.abs(c.sourceMeters+elevation.editorOffsetMeters-c.editorMeters)>1e-6))fail('Elevation calibration mismatch');
    if(Math.abs(elevation.controls[0].sourceMeters-elevation.controls[1].sourceMeters)<1e-6)fail('Distinct elevation controls required');
  }else if(manifest.elevation?.kind!=='not-used')fail('Do not invent unused elevation registration');
  const normalized=structuredClone(manifest);normalized.effectiveExpiresAt=Number.isFinite(expiry)?new Date(expiry).toISOString():null;
  return deepFreeze(normalized);
}
export function assertInputUse(manifest,action,{now=Date.now()}={}){
  if(!Object.hasOwn(ACTIONS,action))fail('Unknown source operation');const key=ACTIONS[action];
  const checked=validateInputManifest(manifest,{now});
  if(checked.assets.some(a=>a.source.permissions[key]!==true))fail(`Source permission denies ${action}`);
  return checked;
}
export async function verifyInputBytes(manifest,bytesById,{clock=Date.now,action='display'}={}){
  if(typeof clock!=='function')fail('Validation clock required');
  const checked=assertInputUse(manifest,action,{now:clock()});
  if(!(bytesById instanceof Map)||bytesById.size!==checked.assets.length)fail('Exact asset byte set required');
  for(const asset of checked.assets){
    const bytes=bytesById.get(asset.id);if(!(bytes instanceof Uint8Array)||bytes.byteLength!==asset.byteLength)fail('Asset bytes missing or length mismatch');
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');if(hash!==asset.sha256)fail('Asset checksum mismatch');
  }
  return assertInputUse(checked,action,{now:clock()});
}
