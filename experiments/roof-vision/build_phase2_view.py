"""Package generated structural alternatives and meshes for local inspection."""
from pathlib import Path
import base64
import copy
import io
import json
import pickle
import re
from PIL import Image
from phase2_mesh import build_mesh

ROOT=Path(__file__).resolve().parent
VISUAL_ROOT = ROOT
TARGET = VISUAL_ROOT/'outputs/visualizations/structural-roof-prototype.html'
TARGET.parent.mkdir(parents=True, exist_ok=True)
if not TARGET.exists():
    TARGET.write_text((VISUAL_ROOT/'templates/structural-roof-prototype.html').read_text())


def data_image(content,kind='png'):
    return 'data:image/'+kind+';base64,'+base64.b64encode(content).decode()


def compact(value):
    if isinstance(value,float):return round(value,5)
    if isinstance(value,list):return [compact(v) for v in value]
    if isinstance(value,dict):return {k:compact(v) for k,v in value.items()}
    return value


def main():
    model=json.loads((ROOT/'outputs/phase2-structure.json').read_text())
    cached=pickle.loads((ROOT/'data/inputs.pkl').read_bytes())
    reference=Image.open(ROOT/'data/user-roof-reference-2026-10-17.png').convert('RGB')
    reference.thumbnail((960,960))
    buf=io.BytesIO();reference.save(buf,format='JPEG',quality=82)
    candidates=[]
    entries=[entry for entry in model['candidate_models'] if entry.get('roof_faces')]
    if not entries:
        entries=[{'id':'current','description':'Current automatic structural hypothesis',
                  'roof_faces':model['roof_faces'],'selected':True}]
    for entry in entries:
        candidate={**model,'roof_faces':entry['roof_faces']}
        mesh=build_mesh(candidate)
        quality=entry.get('quality',entry.get('scores',{}))
        faces=[]
        for face in entry['roof_faces']:
            source=', '.join(face.get('source_group_ids',[])) or 'new elevation-supported hypothesis'
            descriptor=f'{face["id"]}: {face.get("role","roof").replace("_"," ")}; {source}. {face.get("hypothesis_status","unverified")}. Usable array area not established.'
            faces.append({k:face[k] for k in ('id','parts','role','level_id') if k in face})
            faces[-1]['description']=descriptor
        descriptions={
            'support_rectangle':'Support-based main roof',
            'detected_edge_rectangle':'Image-edge main roof',
            'blended_supported_rectangle':'Blended main roof',
            'support_rectangle-without-child-features':'Without child roof candidates',
        }
        candidates.append({'id':entry['id'],'label':descriptions.get(entry['id'],entry['id'].replace('_',' ')),
            'description':entry.get('description','Automatic structural hypothesis')+' Dormers, lower connections and wall geometry remain experimental.',
            'faces':faces,'mesh':{key:mesh[key] for key in ('vertices','triangles','surfaces')},
            'quality':quality,'selected':entry.get('selected',False)})
    selected=next((c['id'] for c in candidates if c['selected']),candidates[0]['id'])
    inverse=~cached['aligned']['transform']
    payload=compact({'candidates':candidates,'selected':selected,
        'photo':data_image((ROOT/'data/roof.png').read_bytes()),'reference':data_image(buf.getvalue(),'jpeg'),
        'local_to_pixel':list(inverse)[:6],'source_expires_at':cached['expires_at'],
        'automatic_geometry_inputs':['cached source planes','DSM','source support masks','cached image lines'],
        'reference_used_for_geometry':False})
    markup=TARGET.read_text()
    markup=re.sub(r'(<script type="application/json" id="structural-roof-data">).*?(</script>)',
        lambda match:match[1]+json.dumps(payload,separators=(',',':'))+match[2],markup,flags=re.S)
    TARGET.write_text(markup)
    print(json.dumps({'viewer_bytes':TARGET.stat().st_size,'candidates':len(candidates),'selected':selected}))


if __name__=='__main__':main()
