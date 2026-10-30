// Source cases stay server-side under original expiry. Permanent manual library is separate.
const post=async(path,data)=>{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const value=await r.json();if(!r.ok)throw new Error(value.error||'Source case request failed');return value};
const fresh=packet=>{if(packet.schema!=='roof-lab-case/v2'||Date.parse(packet.expiresAt)<=Date.now()||!Number.isFinite(Date.parse(packet.expiresAt)))throw new Error('Invalid or expired source case');return packet};
export async function sourcePacketFromFile(packet){return fresh(await post('/source-case-import',{packet}))}
export function sourceCaseUrl(packet){return '/?google='+encodeURIComponent(packet.source.id)+'&case='+encodeURIComponent(packet.caseId)}
export async function createSourceCases(sourceId,manifest){
 const query=new URLSearchParams(location.search),id=query.get('case');let record=null;
 if(id){const response=await fetch('/source-case?id='+encodeURIComponent(id)+'&checkpoint='+(query.has('checkpoint')?'1':'0'),{cache:'no-store'});if(!response.ok)throw new Error('Saved source case unavailable or expired');record=fresh(await response.json());if(record.source.id!==sourceId||record.source.imageSha256!==manifest.pngSha256)throw new Error('Source case/image mismatch')}
 let writeQueue=Promise.resolve();
 let caseId=record?.caseId||crypto.randomUUID(),context=record?.heightContext||{groundElevation:null,heightSha256:null};
 const manager={record,get caseId(){return caseId},context,ready:false,
  heightContext(){return window.labHeightTools?.getContext?.()||context},
  async refresh(){const response=await fetch('/source-cases?source='+encodeURIComponent(sourceId),{cache:'no-store'});if(!response.ok)throw new Error('Saved source cases unavailable');const list=await response.json(),select=document.querySelector('#saved-cases');select.replaceChildren(new Option('Saved source cases',''));for(const entry of list)select.add(new Option(entry.name+(entry.hasDraft?' (draft)':''),entry.caseId));if(list.some(e=>e.caseId===caseId))select.value=caseId;return list},
  async save(json,name,checkpoint=false){const heightContext=structuredClone(manager.heightContext());const operation=async()=>{if(Date.parse(manifest.expiresAt)<=Date.now())throw new Error('Source expired');const packet=fresh(await post('/source-case-save',{sourceId,expectedImageSha256:manifest.pngSha256,caseId,name,nativeDesignJson:json,heightContext,checkpoint,inputExpiresAt:record?.expiresAt}));record=packet;manager.record=packet;manager.context=packet.heightContext;query.delete('checkpoint');query.set('case',caseId);history.replaceState(null,'',location.pathname+'?'+query.toString());await manager.refresh();return packet};const task=writeQueue.then(operation,operation);writeQueue=task.catch(()=>{});return task},
  async preserve(){if(!window.engine||!manager.ready)return;const value=await engine.bridge.getJsonToSave();await manager.save(typeof value==='string'?value:JSON.stringify(value),document.querySelector('#case-name').value.trim()||'Untitled example',false)},
  async reopen(id){const saved=await fetch('/source-case?id='+encodeURIComponent(id)+'&checkpoint=1',{cache:'no-store'});if(!saved.ok)throw new Error('No saved checkpoint yet. Use Save locally first.');await manager.preserve();if(id===caseId)await post('/source-case-recover',{caseId});location.assign('/?google='+encodeURIComponent(sourceId)+'&case='+encodeURIComponent(id)+'&checkpoint=1')},
  async switchTo(id){await manager.preserve();location.assign('/?google='+encodeURIComponent(sourceId)+'&case='+encodeURIComponent(id))},
  async export(json,name){const packet=await manager.save(json,name,false);if(!packet.geometry.buildings.some(b=>b.faces.length))throw new Error('Draw a roof before exporting');return packet},
 };
 if(query.has('checkpoint')){query.delete('checkpoint');history.replaceState(null,'',location.pathname+'?'+query.toString())}
 return manager;
}
