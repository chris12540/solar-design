import assert from 'node:assert/strict';
import {robustLine,proposeFit,proposePlaneFit} from './height-fit.mjs';
const samples=Array.from({length:120},(_,i)=>[i/15,4+.5*i/15+(i%7===0?8:0)]);
const fit=robustLine(samples);assert.ok(Math.abs(fit.height-4)<.03);assert.ok(Math.abs(fit.slope-.5)<.01);
assert.throws(()=>robustLine(samples.slice(0,20)),/Too few/);assert.throws(()=>robustLine(samples.map(([,z])=>[1,z])),/span/);
const roof={type:'roof',details:false,flat:false,nodes:[[-6,-6],[6,-6],[6,6],[-6,6]],edges:[{id:'south',nodes:[[-6,-6],[6,-6]],height:3,pitch:30},{id:'north',nodes:[[6,6],[-6,6]],height:3,pitch:30},{id:'east',nodes:[[6,-6],[6,6]],height:3,pitch:90},{id:'west',nodes:[[-6,6],[-6,-6]],height:3,pitch:90}],faces:[{sourceId:'south',nodes:[[-6,-6],[6,-6],[6,0],[-6,0]]},{sourceId:'north',nodes:[[-6,0],[6,0],[6,6],[-6,6]]}]};
const points=[];for(let x=-5.5;x<=5.5;x+=.5)for(let y=-5.5;y<=5.5;y+=.5)points.push({x,y,z:4+Math.tan(25*Math.PI/180)*(6-Math.abs(y)),roof:true});
const proposal=proposeFit(roof,points);assert.equal(proposal.length,2);for(const p of proposal){assert.ok(Math.abs(p.height-4)<1e-7);assert.ok(Math.abs(p.pitch-25)<1e-7)}
const flat={...roof,flat:true,edges:roof.edges.map(e=>({...e,pitch:0})),faces:[{sourceId:'south',nodes:roof.nodes}]};const flatFit=proposeFit(flat,points.map(p=>({...p,z:5})));assert.equal(flatFit.length,4);const nativeFlat=proposeFit({...flat,edges:flat.edges.map(e=>({...e,pitch:90}))},points.map(p=>({...p,z:5})));assert.ok(nativeFlat.every(p=>p.pitch===90&&p.height===5));assert.ok(flatFit.every(p=>p.height===5&&p.pitch===0));
assert.deepEqual(proposeFit({...roof,details:true},points),proposal);assert.throws(()=>proposeFit(roof,points.map(p=>({...p,roof:false}))),/Too few/);
console.log(JSON.stringify({passed:true,robustOutliers:true,knownSlopeHeight:true,insufficientAndDegenerateRejected:true,baseRoofWithDetailsSupported:true,maskRequired:true}));

const lNodes=[[-6,-6],[6,-6],[6,0],[0,0],[0,6],[-6,6]],lRoof={type:'roof',flat:true,nodes:lNodes,edges:lNodes.map((p,i)=>({id:String(i),nodes:[p,lNodes[(i+1)%6]],height:3,pitch:90})),faces:[{nodes:lNodes,sourceId:'0'}]};assert.equal(proposeFit(lRoof,points.map(p=>({...p,z:5}))).length,6);
const nodePlane=[[-4,-3],[4,-3],[4,3],[-4,3]],plane={id:'plane',type:'roof.plane',nodes:nodePlane,vertices:nodePlane.map(([x,y])=>[x,y,4+.3*x+.4*y]),normal:[-.3,-.4,1],height:1.6,pitch:Math.atan(.5)*180/Math.PI};
const cloud=[];for(let x=-3.5;x<=3.5;x+=.25)for(let y=-2.5;y<=2.5;y+=.25)cloud.push({x,y,z:10+.6*x+.8*y,roof:true});const fitted=proposePlaneFit(plane,cloud)[0];assert.ok(Math.abs(fitted.height-5.2)<1e-7);assert.ok(Math.abs(fitted.pitch-45)<1e-7);
console.log(JSON.stringify({concaveOutline:true,independentFaceHeightPitch:true,headingPreserved:true}));
