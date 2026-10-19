"""Embed actual cached detector and fitted geometry into the comparison viewer."""
from pathlib import Path
import base64
import json
import pickle
import re
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent
VISUAL_ROOT = ROOT
TARGET = VISUAL_ROOT/'outputs/visualizations/connected-roof-comparison.html'
TARGET.parent.mkdir(parents=True, exist_ok=True)
if not TARGET.exists():
    TARGET.write_text((VISUAL_ROOT/'templates/connected-roof-comparison.html').read_text())


def ring_path(points):
    return 'M'+'L'.join(f'{float(x):.2f},{float(y):.2f}' for x,y in points)+'Z'


def main():
    source=pickle.loads((ROOT/'data/inputs.pkl').read_bytes())
    result=json.loads((ROOT/'outputs/connected-roof.json').read_text())
    inverse=~source['aligned']['transform']
    def local_path(part):
        return ''.join(ring_path([inverse*tuple(p) for p in ring])
                       for ring in [part['polygon'],*part.get('holes',[])])
    masks=[]
    for mask in np.load(ROOT/'outputs/sam-masks.npz')['faces']:
        contours,_=cv2.findContours(mask.astype('uint8'),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        masks.append(''.join(ring_path(c[:,0,:]+.5) for c in contours if len(c)>=3))
    payload={
        'photo':'data:image/png;base64,'+base64.b64encode((ROOT/'data/roof.png').read_bytes()).decode(),
        'masks':masks,
        'polygons':[local_path(part) for group in result['face_groups'] for part in group['parts']],
        'exclusions':[local_path(p) for p in result.get('obstruction_candidates',[])],
        'summary':f"{len(result['face_groups'])} source planes retained · No face overlaps · Dashed: obstruction candidates",
        'algorithm_version':result['algorithm_version'],
        'expires_at':source['expires_at'],
    }
    markup=TARGET.read_text()
    markup=re.sub(r'(<script type="application/json" id="roof-proof-data">).*?(</script>)',
        lambda m:m[1]+json.dumps(payload,separators=(',',':'))+m[2],markup,flags=re.S)
    TARGET.write_text(markup)
    print(f'Updated comparison: {TARGET.stat().st_size} bytes')


if __name__=='__main__':
    main()
