"""Embed cached Phase 1 evidence into a self-contained inspection view."""
from pathlib import Path
import base64
import io
import json
import re
import numpy as np
import cv2
from PIL import Image

ROOT = Path(__file__).resolve().parent
VISUAL_ROOT = ROOT
TARGET = VISUAL_ROOT/'outputs/visualizations/phase-one-roof-evidence.html'
TARGET.parent.mkdir(parents=True, exist_ok=True)
if not TARGET.exists():
    TARGET.write_text((VISUAL_ROOT/'templates/phase-one-roof-evidence.html').read_text())


def image_data(content):
    return 'data:image/png;base64,'+base64.b64encode(content).decode()


def main():
    reference = json.loads((ROOT/'phase1-reference.json').read_text())
    planes = json.loads((ROOT/'outputs/phase1-planes.json').read_text())
    evidence = json.loads((ROOT/'outputs/phase1-evidence.json').read_text())
    fields = np.load(ROOT/'outputs/phase1-alignment-fields.npz')
    archive = np.load(ROOT/'outputs/sam-masks.npz')
    dsm = fields['dsm_m']
    low, high = np.percentile(dsm[np.isfinite(dsm)], [2, 98])
    gray = np.rint(np.clip((dsm-low)/(high-low), 0, 1)*255).astype('uint8')
    png = io.BytesIO()
    Image.fromarray(gray).save(png, format='PNG')
    (ROOT/'outputs/phase1-height.png').write_bytes(png.getvalue())
    seam_checks = {item['reference_id']:item for item in evidence['seam_checks']}
    annotations = []
    for item in reference['lines']+reference['regions']+reference['features']:
        detail = item['label']+' — '+item['note']
        check = seam_checks.get(item['id'])
        if check:
            distance = check.get('distance_from_visible_seam_to_analytic_intersection_m')
            if distance:
                detail += f" Plane intersection differs by at most {distance['max']:.2f} m along sampled seam; below draft annotation uncertainty, not measured accuracy."
            else:
                detail += ' Source ownership does not reliably separate both sides; connection remains unresolved.'
        annotations.append({**item, 'detail':detail})
    source_planes = []
    for item in planes['planes']:
        identifier = item['group_id']
        index = list(archive['face_ids']).index(identifier)
        contours, _ = cv2.findContours(archive['face_priors'][index].astype('uint8'), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        path = ''.join('M'+'L'.join(f'{x+.5:.2f},{y+.5:.2f}' for x,y in contour[:,0,:])+'Z' for contour in contours if len(contour)>=3)
        source_ids = ', '.join(item['source_plane_ids'])
        support = item['support']
        rmse = item['source_model_interior_residuals']['rmse_m']
        cv = item['spatial_crossvalidation']['max_held_out_rmse_m']
        concern = ' Smaller-region stability needs care.' if item['concerns'] else ''
        source_planes.append({'id':identifier, 'label':source_ids, 'path':path,
            'detail':f'{source_ids}: {support["prior_horizontal_area_m2"]:.2f} m² source support; {support["interior_pixel_count"]} interior samples. Interior height RMSE {rmse:.3f} m; worst spatial hold-out {cv:.3f} m.{concern} These are source consistency checks, not physical accuracy.'})
    payload = {
        'photo':image_data((ROOT/'data/roof.png').read_bytes()), 'height':image_data(png.getvalue()),
        'annotations':annotations, 'planes':source_planes,
        'height_legend':f'Relative DSM shade: darker lower, lighter higher · display range {low:.2f}–{high:.2f} m; outer 2% clipped for display only',
        'overviews':{
            'reference':'Photo-only reference: visible perimeter/seams, three uncertain connection regions and four appearance features. No complete footprint or obstruction inventory asserted.',
            'height':'Actual cached elevation grid, not a reconstructed model. Main roof slopes are supported; mixed boundary pixels and small joins need separate treatment.',
            'support':f'Eight source regions cover {planes["mask_coverage"]["coverage_of_target_mask_by_source_footprint"]:.2%} of cached roof mask. Similar slopes can occur at different heights; no duplicates or missing plane confirmed.',
            'photo':'Original cached 248 × 220 image, displayed larger without adding detail. Capture: September 27, 2023.'},
        'reference_sha256':evidence['reference_sha256'], 'expires_at':evidence['source_expires_at']
    }
    markup = TARGET.read_text()
    markup = re.sub(r'(<script type="application/json" id="phase-one-data">).*?(</script>)',
                    lambda m:m[1]+json.dumps(payload,separators=(',',':'))+m[2],markup,flags=re.S)
    TARGET.write_text(markup)
    print(f'Embedded Phase 1 evidence: {TARGET.stat().st_size} bytes')


if __name__ == '__main__':
    main()
