"""Evaluate fixed detector outputs; draft visual labels are not survey truth."""
from pathlib import Path
import json
import pickle
import math
import numpy as np
import cv2
from affine import Affine
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.warp import reproject, Resampling

ROOT = Path(__file__).resolve().parent


def coverage(reference, candidates, tolerance):
    a,b = np.array(reference,float)
    delta=b-a
    points=a+np.linspace(0,1,max(2,math.ceil(np.linalg.norm(delta)*2)))[:,None]*delta
    hits=np.zeros(len(points),bool)
    for line in candidates:
        p,q=np.array(line,float)
        v=q-p
        length=np.linalg.norm(v)
        if length < 1e-6:
            continue
        cosine=abs(np.dot(delta,v))/(np.linalg.norm(delta)*length)
        if cosine < math.cos(math.radians(15)):
            continue
        t=np.clip(((points-p)@v)/(length*length),0,1)
        distance=np.linalg.norm(points-(p+t[:,None]*v),axis=1)
        hits |= distance <= tolerance
    return float(hits.mean())


def evaluate():
    reference=json.loads((ROOT/'reference.json').read_text())
    lines=json.loads((ROOT/'outputs/lines.json').read_text())
    data=pickle.loads((ROOT/'data/inputs.pkl').read_bytes())
    sam=np.load(ROOT/'outputs/sam-masks.npz')
    automatic=np.load(ROOT/'outputs/sam-automatic-masks.npz')['masks']
    sets={'classical_all':[x['pixel_xy'] for x in lines['lines']],
          'classical_context':[x['pixel_xy'] for x in lines['lines'] if x['classical_context_selected']],
          'learned_filtered':[x['pixel_xy'] for x in lines['lines'] if x['learned_filtered_selected']]}
    line_metrics=[]
    for item in reference['lines']:
        line_metrics.append({'id':item['id'],'confidence':item['confidence'],
            **{name:coverage(item['xy'],segments,reference['line_tolerance_pixels']) for name,segments in sets.items()}})
    object_metrics=[]
    for item in reference['obstruction_candidates']:
        x1,y1,x2,y2=item['bbox_xyxy']
        hits=[int(mask[y1:y2,x1:x2].sum()) for mask in automatic]
        object_metrics.append({'id':item['id'],'overlapping_candidate_count':sum(n>0 for n in hits),
                               'max_overlap_pixels':max(hits,default=0),
                               'not_obstruction_accuracy':True})
    aligned=data['aligned'];raw=data['raw'];rgb=aligned['rgb'];transform=aligned['transform']
    h,w=rgb.shape[:2]
    origin=raw['origin']
    ox,oy=Transformer.from_crs(4326,origin['crs'],always_xy=True).transform(origin['longitude'],origin['latitude'])
    dsm=np.full((h,w),np.nan,np.float32)
    with MemoryFile(data['inputs']['dsm']) as mem,mem.open() as src:
        reproject(src.read(1),dsm,src_transform=src.transform,src_crs=src.crs,
                  dst_transform=Affine.translation(ox,oy)*transform,dst_crs=origin['crs'],
                  src_nodata=src.nodata,dst_nodata=np.nan,resampling=Resampling.bilinear)
    rr,cc=np.indices((h,w));xx=transform.a*(cc+.5)+transform.b*(rr+.5)+transform.c
    yy=transform.d*(cc+.5)+transform.e*(rr+.5)+transform.f
    models={f['id']:f['plane_model'] for f in raw['refinement']['face_groups']}
    heights=[]
    for index,identifier in enumerate(sam['face_ids']):
        model=models[str(identifier)]
        residual=dsm-(model['a']*xx+model['b']*yy+model['c'])
        metric={'id':str(identifier)}
        for name,mask in [('raw_prior',sam['face_priors'][index]),('sam',sam['faces'][index])]:
            values=residual[mask & np.isfinite(residual) & (dsm!=-9999)]
            metric[name]={'pixels':len(values),'height_rmse_m':float(np.sqrt(np.mean(values**2))) if len(values) else None,
                          'median_absolute_height_error_m':float(np.median(np.abs(values))) if len(values) else None}
        heights.append(metric)
    regions={}
    for item in reference['interior_regions']:
        region=np.zeros((h,w),np.uint8)
        cv2.fillPoly(region,[np.array(item['polygon'],np.int32)],1)
        region=region.astype(bool)
        # Associate identity using prior masks, never select predictions by truth.
        index=max(range(len(sam['faces'])),key=lambda i:int((sam['face_priors'][i]&region).sum()))
        regions[item['id']]={'source_face':str(sam['face_ids'][index]),
            'interior_coverage_fraction':float(sam['faces'][index][region].mean()),
            'scope':'Coverage of selected face interior; not full-face IoU or precision'}
    report={'reference_status':reference['status'],'line_tolerance_pixels':reference['line_tolerance_pixels'],
            'line_coverage':line_metrics,'visible_feature_matches':object_metrics,
            'face_interior_checks':regions,'height_consistency':heights,
            'source_expires_at':data['expires_at'],
            'limitations':['Draft annotations can be wrong; endpoints have pixel uncertainty.',
                'Incomplete reference cannot measure false positives or full obstruction recall.',
                'Both detector methods use Google priors; comparisons are not independent roof accuracy.',
                'Height residuals use existing plane models without refitting; improved image masks can expose more height outliers.',
                'One cached photo cannot establish generalization or production acceptance.']}
    (ROOT/'outputs/evaluation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'line_coverage':line_metrics,'visible_feature_matches':object_metrics,'face_interiors':regions},indent=2))


if __name__=='__main__':
    evaluate()
