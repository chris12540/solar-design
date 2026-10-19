"""Cached-only experiment and same-scale scientific comparison."""
from pathlib import Path
import hashlib
import json
import pickle
import os
import time

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'cache/matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME',str(ROOT/'cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path as PlotPath
from affine import Affine
import numpy as np
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.warp import reproject, Resampling
from shapely.geometry import mapping
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from cleanup import reconstruct


def counts(records):
    return {'polygons':len(records),
            'vertices':sum(len(r['geometry'].exterior.coords)-1+
                           sum(len(h.coords)-1 for h in r['geometry'].interiors) for r in records),
            'holes':sum(len(r['geometry'].interiors) for r in records)}


def load_cached():
    content=(BASE/'data/inputs.pkl').read_bytes()
    source=pickle.loads(content)
    origin=source['raw']['origin']
    ox,oy=Transformer.from_crs(4326,origin['crs'],always_xy=True).transform(origin['longitude'],origin['latitude'])
    world=Affine.translation(ox,oy)*source['aligned']['transform']
    rgb=source['aligned']['rgb']
    h,w=rgb.shape[:2]
    fields={}
    for name,method in [('dsm',Resampling.bilinear),('mask',Resampling.nearest)]:
        target=np.full((h,w),np.nan,dtype='float64') if name=='dsm' else np.zeros((h,w),dtype='uint8')
        with MemoryFile(source['inputs'][name]) as mem,mem.open() as src:
            reproject(src.read(1),target,src_transform=src.transform,src_crs=src.crs,
                      dst_transform=world,dst_crs=origin['crs'],src_nodata=src.nodata,
                      dst_nodata=np.nan if name=='dsm' else 0,resampling=method)
        fields[name]=target
    return source,content,rgb,fields,world,origin['crs']


def main():
    source,content,rgb,fields,world,crs=load_cached()
    result=reconstruct(source['inputs']['insights'],fields['dsm'],fields['mask'],world,crs)
    out=ROOT/'outputs';out.mkdir(exist_ok=True)
    np.savez_compressed(out/'arrays.npz',raw=result['labels'],clean=result['cleaned_labels'],
                        candidate=result['candidate_labels'],
                        residual_m=result['residual_m'],strong=result['strong'],target=result['target'])
    features=[]
    for r in result['records']:
        plane=next((p for p in result['models'] if p['id']==r['label']),None)
        properties={'label':r['label'],'state':'unresolved' if r['label']==0 else 'google_plane_supported_candidate',
                    'horizontal_area_m2':r['geometry'].area,'design_ready':False}
        if plane:
            properties.update({k:v for k,v in plane.items() if k!='bounds'})
        features.append({'type':'Feature','properties':properties,'geometry':mapping(r['geometry'])})
    def support_feature(r,state):
        return {'type':'Feature','properties':{'label':r['label'],'state':state,'design_ready':False},
                'geometry':mapping(r['geometry'])}
    exported={'type':'FeatureCollection','coordinate_system':{'crs':str(crs),'origin_xy':result['origin'].tolist(),
              'geometry_units':'local projected meters','height_units':'source ASL meters'},'features':features,
              'unresolved_exclusions':[support_feature(r,'unresolved_exclusion') for r in result['exclusions']],
              'height_supported_surfaces':[support_feature(r,'height_supported_only_not_panel_ready') for r in result['effective_records']],
              'interpretation':'features are candidate geometry; exclude unresolved_exclusions from any support analysis; height_supported_surfaces already subtract them. No surface is design ready.'}
    (out/'polygons.json').write_text(json.dumps(exported,indent=2))
    raw_known=[r for r in result['raw_records'] if r['label']>0]
    clean_known=[r for r in result['records'] if r['label']>0]
    models={p['id']:p for p in result['models']}
    rows=[]
    yy,xx=np.indices(fields['dsm'].shape)
    x,y=result['local_transform']*(xx+.5,yy+.5)
    for label in models:
        a,b,c=models[label]['coefficients'];residual=fields['dsm']-(a*x+b*y+c)
        row={'label':label,'google_segment_index':label-1}
        for name,grid,records in [('raw',result['labels'],raw_known),('clean',result['cleaned_labels'],clean_known)]:
            selected=(grid==label)&np.isfinite(residual)
            row[name]={'pixel_count':int(selected.sum()),'candidate_projected_area_m2':sum(r['geometry'].area for r in records if r['label']==label),
                       'dsm_rmse_m':float(np.sqrt(np.mean(residual[selected]**2))) if selected.any() else None,
                       'dsm_absolute_p95_m':float(np.quantile(abs(residual[selected]),.95)) if selected.any() else None}
        rows.append(row)
        row['clean']['height_supported_projected_area_m2']=sum(r['geometry'].area for r in result['effective_records'] if r['label']==label)
    union=unary_union([r['geometry'] for r in clean_known])
    report={'status':'experimental_2d_candidates_not_accepted_design','source_input_sha256':hashlib.sha256(content).hexdigest(),
            'expires_at':str(source['expires_at']),'google_requests':0,'model_inference':False,'house_count':1,
            'additional_complete_cached_houses':0,'held_out_validation':'unavailable',
            'diagnostics':result['diagnostics'],'raw_known':counts(raw_known),'clean_known':counts(clean_known),
            'overlap_m2':max(0.,sum(r['geometry'].area for r in clean_known)-union.area),'planes':rows,
            'final_exclusion_area_m2':sum(r['geometry'].area for r in result['exclusions']),
            'automatic_photo_edge_scoring':False,
            'limits':['No surveyed boundary or obstruction ground truth','Missing planes remain unresolved',
                      'Google pitch, azimuth and center height unchanged','Imagery capture dates differ by 20 days',
                      'Cleanup is not physical accuracy validation or AHJ approval']}
    (out/'report.json').write_text(json.dumps(report,indent=2))
    inverse=~result['local_transform']

    def draw(ax,title,records,exclusions=None):
        ax.imshow(rgb,interpolation='nearest')
        for r in (exclusions if exclusions is not None else [r for r in records if r['label']==0]):
            geom=orient(r['geometry'],sign=1.)
            vertices=[];codes=[]
            for ring in [geom.exterior,*geom.interiors]:
                coords=np.array([inverse*tuple(p) for p in ring.coords])-.5
                vertices.extend(coords)
                codes.extend([PlotPath.MOVETO]+[PlotPath.LINETO]*(len(coords)-2)+[PlotPath.CLOSEPOLY])
            ax.add_patch(PathPatch(PlotPath(vertices,codes),facecolor='#faac3255',edgecolor='#d67e16',lw=.4))
        for r in records:
            geom=r['geometry']
            if r['label']==0:
                continue
            else:
                for ring in [geom.exterior,*geom.interiors]:
                    coords=np.array([inverse*tuple(p) for p in ring.coords])-.5
                    ax.plot(coords[:,0],coords[:,1],color='#51dbff',lw=1.0)
        ax.set_xlim(-.5,rgb.shape[1]-.5);ax.set_ylim(rgb.shape[0]-.5,-.5)
        ax.set_title(title,fontsize=12,loc='left');ax.axis('off')

    fig,axes=plt.subplots(1,3,figsize=(16,5.6),facecolor='white')
    draw(axes[0],'Cached photograph',[])
    draw(axes[1],'Original Google planes + height assignment',result['raw_records'])
    draw(axes[2],'Joint boundary cleanup',result['records'],result['exclusions'])
    fig.text(.03,.04,'Cyan: candidate roof boundaries · Orange: unresolved height support, not confirmed obstructions · Same image and scale',fontsize=10)
    fig.text(.03,.015,'Includes solar data from Google · No invented roof planes · No AHJ approval · Single-house experiment',fontsize=10)
    fig.tight_layout(rect=(.01,.07,.99,.98));fig.savefig(out/'comparison.png',dpi=160);plt.close(fig)
    print(json.dumps({k:v for k,v in report.items() if k not in ['planes','limits']},indent=2))


if __name__=='__main__':
    main()
