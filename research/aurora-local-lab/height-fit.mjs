// Independent robust scalar plane fitting. XY outline and edge directions stay fixed.
const median=values=>{const a=[...values].sort((x,y)=>x-y),n=a.length;return n%2?a[n>>1]:(a[n/2-1]+a[n/2])/2};
export function inside(x,y,ring){let yes=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])yes=!yes}return yes}
function distance(x,y,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)));return Math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)}
export function robustLine(samples){
 if(samples.length<40)throw new Error('Too few valid roof samples for a reliable fit.');
 let weights=samples.map(()=>1),h=0,m=0;
 for(let iteration=0;iteration<12;iteration++){
  let sw=0,sx=0,sy=0,sxx=0,sxy=0;for(let i=0;i<samples.length;i++){const[x,y]=samples[i],w=weights[i];sw+=w;sx+=w*x;sy+=w*y;sxx+=w*x*x;sxy+=w*x*y}
  const det=sw*sxx-sx*sx;if(det<1e-7)throw new Error('Height samples do not span enough roof depth.');m=(sw*sxy-sx*sy)/det;h=(sy-m*sx)/sw;
  const residual=samples.map(([x,y])=>y-h-m*x),center=median(residual),scale=Math.max(.04,1.4826*median(residual.map(v=>Math.abs(v-center))));
  weights=residual.map(v=>Math.min(1,1.5*scale/Math.max(1e-9,Math.abs(v-center))));
 }
 const errors=samples.map(([x,y])=>Math.abs(y-h-m*x)),error=median(errors),inliers=errors.filter(v=>v<=Math.max(.2,3*error)).length/samples.length;
 if(!Number.isFinite(h+m)||error>.35||inliers<.7)throw new Error('Height data does not support a consistent roof plane.');
 return{height:h,slope:m,error,inliers,samples:samples.length};
}
export function proposeFit(roof,points){
 if(roof.type!=='roof'||roof.nodes.length<3||roof.nodes.length>200||roof.edges.length!==roof.nodes.length)throw new Error('Fit needs a complete roof outline.');
 const changes=[];for(const edge of roof.edges){
  if(!roof.flat&&edge.pitch>=89)continue;
  const faces=roof.flat?[roof.faces[0]]:roof.faces.filter(f=>f.sourceId===edge.id);const face=faces[0];if(!face)throw new Error('A roof edge has no usable face.');
  const[a,b]=edge.nodes,dx=b[0]-a[0],dy=b[1]-a[1],length=Math.hypot(dx,dy);if(length<.1)throw new Error('Roof edge too short.');
  let nx=-dy/length,ny=dx/length;const cx=face.nodes.reduce((s,p)=>s+p[0]/face.nodes.length,0),cy=face.nodes.reduce((s,p)=>s+p[1]/face.nodes.length,0);if((cx-a[0])*nx+(cy-a[1])*ny<0){nx=-nx;ny=-ny}
  const samples=[];for(const p of points){if(!p.roof||!faces.some(f=>inside(p.x,p.y,f.nodes)&&!f.nodes.some((n,i)=>distance(p.x,p.y,n,f.nodes[(i+1)%f.nodes.length])<.35)))continue;samples.push([(p.x-a[0])*nx+(p.y-a[1])*ny,p.z])}
  let fit;
  if(roof.flat){if(samples.length<40)throw new Error('Too few flat-roof samples.');const height=median(samples.map(s=>s[1])),error=median(samples.map(s=>Math.abs(s[1]-height)));if(error>.25)throw new Error('Roof surface is not sufficiently flat.');fit={height,slope:0,error,samples:samples.length,inliers:1}}
  else fit=robustLine(samples);
  const pitch=roof.flat?edge.pitch:Math.atan(fit.slope)*180/Math.PI;
  if(fit.height<.25||fit.height>30||(!roof.flat&&(pitch<0||pitch>80)))throw new Error('Proposed height or slope is outside supported limits. Check ground elevation and roof outline.');
  changes.push({id:edge.id,height:fit.height,pitch,...{error:fit.error,samples:fit.samples},oldHeight:edge.height,oldPitch:edge.pitch});
 }
 if(!changes.length)throw new Error('No sloped or flat roof faces selected.');
 if(roof.flat){const height=median(changes.map(c=>c.height));for(const c of changes)c.height=height}
 return changes;
}

// Standalone faces retain their heading; fit pitch/height along existing upslope.
export function proposePlaneFit(roof,points){
 if(roof.type!=='roof.plane'||roof.nodes.length<3)throw new Error('Select a valid independent face.');
 const valid=points.filter(p=>p.roof&&inside(p.x,p.y,roof.nodes)&&!roof.nodes.some((n,i)=>distance(p.x,p.y,n,roof.nodes[(i+1)%roof.nodes.length])<.35));
 if(valid.length<40)throw new Error('Too few valid samples inside this face.');
 const norm=Math.hypot(roof.normal[0],roof.normal[1]),anchor=roof.vertices.reduce((a,b)=>b[2]<a[2]?b:a),u=norm>1e-8?[-roof.normal[0]/norm,-roof.normal[1]/norm]:[0,0];
 let fit;
 if(norm<1e-8){const height=median(valid.map(p=>p.z)),error=median(valid.map(p=>Math.abs(p.z-height)));if(error>.25)throw new Error('Flat face has sloped/noisy data. Set an initial slope before fitting.');fit={height,slope:0,error,samples:valid.length}}
 else fit=robustLine(valid.map(p=>[(p.x-anchor[0])*u[0]+(p.y-anchor[1])*u[1],p.z]));
 const pitch=Math.atan(fit.slope)*180/Math.PI;
 if(fit.height<.25||fit.height>50||pitch<0||pitch>80)throw new Error('Proposed face height or pitch outside supported limits.');
 return[{kind:'plane',id:roof.id,height:fit.height,pitch,error:fit.error,samples:fit.samples,oldHeight:roof.height,oldPitch:roof.pitch}];
}
