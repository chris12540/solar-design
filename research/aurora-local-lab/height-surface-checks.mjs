import assert from 'node:assert/strict';
import {buildHouseSurface} from './height-surface.mjs';
const width=30,height=20,metadata={width,height,pixelToEditor:[.5,0,-3,0,-.5,3]},heights=new Float32Array(width*height).fill(100),mask=new Uint8Array(width*height);
for(let r=2;r<12;r++)for(let c=2;c<12;c++)mask[r*width+c]=1;
for(let r=2;r<18;r++)for(let c=18;c<29;c++)mask[r*width+c]=1; // larger neighbor
mask[6*width+6]=0; // courtyard/missing sample
heights[3*width+3]=NaN;
heights[9*width+9]=110; // discontinuity must not become a triangle
const surface=buildHouseSurface(metadata,heights,mask);
assert.equal(surface.vertices.length,98);
assert.ok(surface.triangles.length>100);
assert.ok(surface.vertices.every(([x])=>x<=2.5));
for(const triangle of surface.triangles){
 const vertices=triangle.map(i=>surface.vertices[i]);
 assert.ok(Math.max(...vertices.map(p=>p[2]))-Math.min(...vertices.map(p=>p[2]))<=2);
 assert.ok(vertices.every(p=>Number.isFinite(p[0]+p[1]+p[2])));
 // Grid adjacency only; no long triangles over other roofs or missing areas.
 for(const a of vertices)for(const b of vertices)assert.ok(Math.hypot(a[0]-b[0],a[1]-b[1])<=Math.SQRT1_2+1e-9);
}
const distant={...metadata,pixelToEditor:[.5,0,100,0,-.5,100]};
assert.throws(()=>buildHouseSurface(distant,heights,mask),/No roof region/);
assert.throws(()=>buildHouseSurface(metadata,heights,new Uint8Array(mask.length)),/No roof region/);
console.log(JSON.stringify({passed:true,nearestHouseOnly:true,largerNeighborExcluded:true,missingSamplesNotBridged:true,heightDiscontinuityNotBridged:true,distantRoofRejected:true,vertices:surface.vertices.length,triangles:surface.triangles.length}));
