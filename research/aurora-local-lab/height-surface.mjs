// Independent display geometry for the roof-mask region nearest the house origin.
export function buildHouseSurface(metadata, heights, mask) {
  const {width, height, pixelToEditor: t} = metadata;
  const visited = new Uint8Array(heights.length);
  const xy = i => {const c = i % width, r = Math.floor(i / width);return [t[0]*c+t[1]*r+t[2], t[3]*c+t[4]*r+t[5]]};
  let chosen = null, nearest = Infinity;
  for (let seed = 0; seed < heights.length; seed++) {
    if (visited[seed] || mask[seed] !== 1 || !Number.isFinite(heights[seed])) continue;
    const region = [seed]; visited[seed] = 1; let distance = Infinity;
    for (let head = 0; head < region.length; head++) {
      const i = region[head], c = i % width, r = Math.floor(i / width), [x,y] = xy(i);
      distance = Math.min(distance, x*x+y*y);
      const neighbors = [];
      if(c) neighbors.push(i-1); if(c+1<width) neighbors.push(i+1);
      if(r) neighbors.push(i-width); if(r+1<height) neighbors.push(i+width);
      for(const n of neighbors) if(!visited[n] && mask[n]===1 && Number.isFinite(heights[n])) {visited[n]=1;region.push(n)}
    }
    if(region.length>=12 && distance<nearest) {chosen=region;nearest=distance}
  }
  // Refuse a distant neighbor when the target roof is absent from the mask.
  if(!chosen || nearest>64) throw new Error('No roof region found near this house. Height surface unavailable.');
  const indices = new Int32Array(heights.length).fill(-1), vertices = [];
  for(const i of chosen) {indices[i]=vertices.length;vertices.push([...xy(i),heights[i]])}
  const triangles=[];
  const add=(a,b,c)=>{
    if(indices[a]<0 || indices[b]<0 || indices[c]<0) return;
    const lo=Math.min(heights[a],heights[b],heights[c]),hi=Math.max(heights[a],heights[b],heights[c]);
    if(hi-lo>2) return; // Do not span abrupt DSM discontinuities.
    triangles.push([indices[a],indices[b],indices[c]]);
  };
  for(let r=0;r<height-1;r++)for(let c=0;c<width-1;c++) {
    const a=r*width+c,b=a+1,d=a+width,e=d+1;
    const all=[a,b,d,e].every(i=>indices[i]>=0);
    if(all && Math.abs(heights[b]-heights[d])<Math.abs(heights[a]-heights[e])) {add(a,b,d);add(b,e,d)}
    else if(all) {add(a,b,e);add(a,e,d)}
    else {add(a,b,d);add(a,b,e);add(a,d,e);add(b,d,e)}
  }
  return {vertices,triangles,nearestDistance:Math.sqrt(nearest)};
}
