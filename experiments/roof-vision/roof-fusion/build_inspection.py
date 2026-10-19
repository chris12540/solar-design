"""Embed measured fusion outputs into a self-contained photo inspector."""
from pathlib import Path
import base64
import io
import json
import re
import numpy as np
from affine import Affine
from PIL import Image
from rasterio.features import rasterize,shapes
from shapely.geometry import shape

ROOT=Path(__file__).resolve().parent
VISUAL_ROOT = ROOT.parent
TARGET = VISUAL_ROOT/'outputs/visualizations/roof-fusion-inspection.html'
TARGET.parent.mkdir(parents=True, exist_ok=True)
if not TARGET.exists():
    TARGET.write_text((VISUAL_ROOT/'templates/roof-fusion-inspection.html').read_text())


def main():
    report=json.loads((ROOT/'outputs/fusion.json').read_text());result=report['result']
    fields=np.load(ROOT/'outputs/inspection.npz');rgb=fields['rgb'];dsm=fields['dsm'];target=fields['target']
    transform=Affine(*report['coordinate_system']['local_affine']);inverse=~transform
    def rings(geometry):
        p=shape(geometry)
        return [[[round(v,3) for v in inverse*tuple(point)] for point in ring.coords]
                for ring in [p.exterior,*p.interiors]]
    data={'width':rgb.shape[1],'height':rgb.shape[0],'faces':[],'edges':[],
          'coverage':result['coverage_fraction'],'supported':sum(f['coefficients'] is not None for f in result['faces']),
          'raw':[[list(inverse*tuple(point)) for point in line['coordinates']] for line in result['raw_lines_local']],
          'unknown':[ring for p in result['unknown_geometries'] for ring in rings(p)],'residual':[]}
    png=io.BytesIO();Image.fromarray(rgb).save(png,format='PNG')
    data['photo']='data:image/png;base64,'+base64.b64encode(png.getvalue()).decode()
    yy,xx=np.indices(dsm.shape);x,y=transform*(xx+.5,yy+.5)
    bins=np.zeros(dsm.shape,dtype='uint8')
    for face in result['faces']:
        geometry=shape(face['geometry']);point=geometry.representative_point()
        row={'id':face['id'],'state':face['state'],'area':face['area_horizontal_m2'],
             'samples':face['interior_samples'],'rings':rings(face['geometry']),
             'label':list(inverse*(point.x,point.y)),'rmse':face.get('final_rmse_m'),
             'pitch':face.get('pitch_degrees'),'azimuth':face.get('azimuth_true_north_degrees'),
             'google':face.get('google_segment_index'),'joint':face['joint_fit_applied'],
             'reason':face.get('reason','Insufficient interior height samples').replace('_',' ')}
        data['faces'].append(row)
        if face['coefficients'] is not None:
            selected=rasterize([(geometry,1)],out_shape=dsm.shape,transform=transform).astype(bool)&target&np.isfinite(dsm)
            a,b,c=face['coefficients'];difference=abs(dsm-(a*x+b*y+c))
            bins[selected]=np.where(difference[selected]<=.1,1,np.where(difference[selected]<=.2,2,3))
    for value in [1,2,3]:
        for geometry,_ in shapes(bins,mask=bins==value,transform=transform):
            data['residual'].append({'level':value-1,'rings':rings(geometry)})
    def lineparts(g):
        p=shape(g)
        geoms=[p] if p.geom_type=='LineString' else list(p.geoms)
        return [[list(inverse*tuple(point)) for point in part.coords] for part in geoms]
    for edge in result['edges']:
        data['edges'].append({'faces':[result['faces'][i]['id'] for i in edge['faces']],
                              'kind':edge['kind'],'gap':edge.get('final_max_gap_m'),
                              'lines':lineparts(edge['geometry'])})
    text=TARGET.read_text()
    text=re.sub(r'(<script type="application/json" id="roof-fusion-data">).*?(</script>)',
                lambda m:m[1]+json.dumps(data,separators=(',',':'))+m[2],text,flags=re.S)
    if len(text.encode())>1_000_000:
        raise ValueError('Inspector exceeds fragment size limit')
    TARGET.write_text(text)
    print('Inspector bytes:',len(text.encode()),'Residual patches:',len(data['residual']))


if __name__=='__main__':
    main()
