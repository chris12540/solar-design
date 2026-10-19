"""Isolated SAM2 experiment. Prompts are automatic Google geometry priors, not truth."""
from pathlib import Path
import os, sys, json, pickle, time, resource, threading
ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / 'vendor' / 'sam2'
if not VENDOR.exists():
    VENDOR = ROOT / 'vendor' / 'sam2-code'
sys.path.insert(0, str(VENDOR))
try:
    import lzma
except ModuleNotFoundError:
    # pyenv CPython 3.14 lacks _lzma; use installed matching Homebrew extension.
    sys.path.append('/opt/homebrew/opt/python@3.14/Frameworks/Python.framework/Versions/3.14/lib/python3.14/lib-dynload')
    import lzma
import _lzma
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2
import torch
from rasterio.features import rasterize
from rasterio.io import MemoryFile
from rasterio.warp import reproject, Resampling
from pyproj import Transformer
from affine import Affine


def raster_record(record, shape, transform):
    polygon = record.get('polygon', [])
    if not polygon:
        return np.zeros(shape, bool)
    geom = {'type': 'Polygon', 'coordinates': [polygon] + record.get('holes', [])}
    return rasterize([(geom, 1)], out_shape=shape, transform=transform).astype(bool)


def source_masks(raw, shape, transform):
    refined = raw.get('refinement') or raw.get('refined') or {}
    groups = refined.get('face_groups') or raw.get('face_groups')
    if not groups:
        grouped = {}
        for face in raw['faces']:
            key = str(face.get('source_plane_id', face['id']))
            grouped.setdefault(key, []).append(face)
        groups = [{'id': key, 'parts': parts} for key, parts in grouped.items()]
    ids, masks = [], []
    for group in groups:
        mask = np.zeros(shape, bool)
        for part in group.get('parts', [group]):
            mask |= raster_record(part, shape, transform)
        if mask.any():
            ids.append(group['id'])
            masks.append(mask)
    return ids, np.stack(masks)


def prompt_for(mask, positive_masks=None):
    ys, xs = np.where(mask)
    box = np.array([xs.min(), ys.min(), xs.max(), ys.max()], dtype=np.float32)
    points = []
    for item in positive_masks if positive_masks is not None else [mask]:
        # Largest inscribed-circle center is deterministic, away from boundaries.
        dist = cv2.distanceTransform(item.astype(np.uint8), cv2.DIST_L2, 5)
        y, x = np.unravel_index(dist.argmax(), dist.shape)
        points.append([float(x), float(y)])
    return dict(point_coords=np.array(points, dtype=np.float32),
                point_labels=np.ones(len(points), dtype=np.int32), box=box,
                multimask_output=True)


def overlap(pred, prior):
    intersection = np.logical_and(pred, prior).sum()
    return {'iou': float(intersection / max(1, np.logical_or(pred, prior).sum())),
            'prior_recall': float(intersection / max(1, prior.sum())),
            'predicted_pixels': int(pred.sum()), 'prior_pixels': int(prior.sum())}


def overlay(rgb, masks, colors):
    result = rgb.astype(float).copy()
    for mask, color in zip(masks, colors):
        result[mask] = .52 * result[mask] + .48 * np.array(color)
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(result, contours, -1, color, 1)
    return Image.fromarray(np.clip(result, 0, 255).astype('uint8'))


def preview(rgb, google, source, whole, faces, ids, target):
    colors = [(255, 92, 70), (60, 200, 255), (255, 208, 60), (175, 100, 255),
              (50, 225, 135), (255, 120, 210), (110, 150, 255), (215, 245, 70)]
    colors = [colors[i % len(colors)] for i in range(len(ids))]
    panels = [Image.fromarray(rgb), overlay(rgb, [google], [(30, 220, 100)]),
              overlay(rgb, source, colors), overlay(rgb, [whole], [(255, 160, 20)]),
              overlay(rgb, faces, colors)]
    labels = ['RGB crop', 'Google mask (source prior)', 'Google face priors',
              'SAM whole-roof prompt', 'SAM face prompts (overlaps blended)']
    width, height = rgb.shape[1], rgb.shape[0]
    scale = min(2, 480 / width)
    pw, ph = round(width * scale), round(height * scale)
    canvas = Image.new('RGB', (pw * 3, (ph + 50) * 2 + 50), '#141a23')
    draw = ImageDraw.Draw(canvas)
    for i, (panel, label) in enumerate(zip(panels, labels)):
        x, y = (i % 3) * pw, (i // 3) * (ph + 50)
        canvas.paste(panel.resize((pw, ph)), (x, y + 30))
        draw.text((x + 8, y + 8), label, fill='white')
    text_y = ph + 58
    draw.text((pw * 2 + 8, text_y), 'SAM masks have no semantic class.\nPrompts derived from Google geometry.\nPrior overlap is not independent accuracy.\nFace colors follow source ordering:\n' + ', '.join(map(str, ids)), fill='white')
    draw.text((10, canvas.height - 35), 'Includes solar data from Google. Image/geometry dates may differ; registration unverified.', fill='white')
    canvas.save(target)


def main():
    out = ROOT / 'outputs'; out.mkdir(exist_ok=True)
    with (ROOT / 'data' / 'inputs.pkl').open('rb') as f:
        data = pickle.load(f)  # Trusted local export only.
    raw, aligned = data['raw'], data['aligned']
    rgb = np.ascontiguousarray(aligned['rgb'])
    shape, transform = rgb.shape[:2], aligned['transform']
    ids, priors = source_masks(raw, shape, transform)
    google = aligned.get('google_mask')
    google_source = 'aligned.google_mask'
    if google is None:
        outline = raster_record(raw['roof_outline'], shape, transform)
        origin = raw['origin']
        ox, oy = Transformer.from_crs('EPSG:4326', origin['crs'], always_xy=True).transform(origin['longitude'], origin['latitude'])
        world = Affine(transform.a, transform.b, transform.c + ox, transform.d, transform.e, transform.f + oy)
        google = np.zeros(shape, dtype=np.uint8)
        with MemoryFile(data['inputs']['mask']) as mem, mem.open() as src:
            reproject(src.read(1), google, src_transform=src.transform, src_crs=src.crs, dst_transform=world, dst_crs=origin['crs'], resampling=Resampling.nearest)
        _, labels = cv2.connectedComponents((google > 0).astype(np.uint8), connectivity=4)
        candidates = [i for i in np.unique(labels) if i != 0]
        selected = max(candidates, key=lambda i: np.count_nonzero((labels == i) & outline))
        google = labels == selected
        google_source = 'Cached Google mask, georeferenced nearest-neighbor warp; connected component chosen by maximum raw-outline overlap'
    google = np.asarray(google, dtype=bool)
    prompts = [prompt_for(priors.any(axis=0), priors)] + [prompt_for(m) for m in priors]
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    print(f'SAM device: {device}', flush=True)
    def sync():
        if device == 'mps': torch.mps.synchronize()
    memory = {'rss_sampled_max_bytes': 0, 'mps_allocated_sampled_max_bytes': 0,
              'mps_driver_sampled_max_bytes': 0, 'sample_interval_seconds': .05, 'scope': 'Model load + warm/steady prompted runs + automatic mask generation; includes framework process RSS',
              'true_peak': False}
    stopped = threading.Event()
    try:
        import psutil
        process = psutil.Process()
    except ImportError:
        process = None
    def sample():
        while not stopped.is_set():
            if process:
                memory['rss_sampled_max_bytes'] = max(memory['rss_sampled_max_bytes'], process.memory_info().rss)
            if device == 'mps':
                memory['mps_allocated_sampled_max_bytes'] = max(memory['mps_allocated_sampled_max_bytes'], torch.mps.current_allocated_memory())
                memory['mps_driver_sampled_max_bytes'] = max(memory['mps_driver_sampled_max_bytes'], torch.mps.driver_allocated_memory())
            stopped.wait(.05)
    thread = threading.Thread(target=sample, daemon=True); thread.start()
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor
    from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
    start = time.perf_counter()
    model = build_sam2('configs/sam2.1/sam2.1_hiera_t.yaml', str(ROOT / 'models' / 'sam2.1_hiera_tiny.pt'), device=device, apply_postprocessing=False)
    predictor = SAM2ImagePredictor(model)
    sync(); load_seconds = time.perf_counter() - start
    def run():
        sync(); begin = time.perf_counter()
        predictor.set_image(rgb)
        sync(); embedding_seconds = time.perf_counter() - begin
        selected, scores, all_scores = [], [], []
        for prompt in prompts:
            masks, values, _ = predictor.predict(**prompt)
            index = int(np.argmax(values))
            selected.append(masks[index].astype(bool))
            scores.append(float(values[index])); all_scores.append(values.astype(float).tolist())
        sync()
        return np.stack(selected), scores, all_scores, time.perf_counter() - begin, embedding_seconds
    with torch.inference_mode():
        masks, scores, all_scores, warm_seconds, warm_embedding = run()
        steady = []; embeddings = []
        for i in range(3):
            masks, scores, all_scores, seconds, embed = run()
            steady.append(seconds); embeddings.append(embed)
            print(f'SAM steady {i+1}/3: {seconds:.3f}s', flush=True)
    sync(); auto_start = time.perf_counter()
    generator = SAM2AutomaticMaskGenerator(model, points_per_side=16, points_per_batch=32, pred_iou_thresh=.75, stability_score_thresh=.85, min_mask_region_area=0)
    with torch.inference_mode():
        automatic = generator.generate(rgb)
    sync(); auto_seconds = time.perf_counter() - auto_start
    small = [m for m in automatic if 4 <= int(m['area']) <= 200 and np.count_nonzero(m['segmentation'] & google) / max(1, int(m['area'])) >= .5]
    auto_masks = np.stack([m['segmentation'] for m in small]) if small else np.zeros((0, *shape), bool)
    np.savez_compressed(out / 'sam-automatic-masks.npz', masks=auto_masks)
    auto_meta = {'runtime_seconds': auto_seconds, 'generated_masks': len(automatic), 'candidate_count': len(small), 'filter': 'area 4..200 pixels; >=50% mask lies in Google roof component', 'settings': {'points_per_side':16, 'points_per_batch':32, 'pred_iou_thresh':.75, 'stability_score_thresh':.85, 'min_mask_region_area':0}, 'masks': [{k:v for k,v in m.items() if k != 'segmentation'} for m in small], 'limitation': 'Generic appearance regions, not semantic obstructions. Roof intersection filter uses Google prior; no manual reference used.'}
    (out / 'sam-automatic-metrics.json').write_text(json.dumps(auto_meta, indent=2, default=lambda v: v.tolist() if hasattr(v, 'tolist') else str(v)))
    auto_image = overlay(rgb, auto_masks, [(255, 80, 160)] * len(small)).resize((rgb.shape[1]*3, rgb.shape[0]*3))
    auto_canvas = Image.new('RGB', (auto_image.width, auto_image.height + 70), '#141a23')
    auto_canvas.paste(auto_image, (0, 35)); auto_draw = ImageDraw.Draw(auto_canvas)
    auto_draw.text((8, 8), f'SAM automatic small regions: {len(small)} candidates; no semantic class', fill='white')
    auto_draw.text((8, auto_image.height + 43), 'Includes solar data from Google. Candidates are not validated obstructions.', fill='white')
    auto_canvas.save(out / 'sam-automatic-comparison.png')
    stopped.set(); thread.join()
    memory['process_ru_maxrss_bytes'] = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)  # macOS bytes
    memory['rss_source'] = 'psutil sampled' if process else 'unavailable; see process_ru_maxrss_bytes'
    whole, faces = masks[0], masks[1:]
    union = priors.any(axis=0)
    metrics = []
    for i, (face_id, pred, prior) in enumerate(zip(ids, faces, priors)):
        other = np.any(np.delete(priors, i, axis=0), axis=0)
        metrics.append({'id': face_id, **overlap(pred, prior), 'sam_predicted_iou_score': scores[i+1],
                        'cross_face_leakage_pixels': int((pred & other).sum()),
                        'cross_face_leakage_fraction_of_prediction': float((pred & other).sum() / max(1, pred.sum())),
                        'outside_roof_prior_fraction_of_prediction': float((pred & ~union).sum() / max(1, pred.sum()))})
    metadata = {'model': 'SAM2.1 Hiera tiny', 'device': device, 'torch_version': torch.__version__, 'lzma_extension_origin': _lzma.__file__,
                'source': 'https://github.com/facebookresearch/sam2', 'input_shape': list(rgb.shape),
                'checkpoint_bytes': (ROOT / 'models' / 'sam2.1_hiera_tiny.pt').stat().st_size,
                'postprocessing': False, 'mps_fallback_enabled': os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK') == '1', 'automatic_mask_generator': auto_meta, 'google_mask_source': google_source,
                'prompts': 'Automatic Google-derived bounding box + largest-inscribed-circle positive point per face; whole-roof prompt has one positive point per face. No manual reference prompts.',
                'selection': 'Highest SAM predicted IoU score of 3 masks; no selection by Google overlap.',
                'prompt_count': len(prompts), 'face_count': len(ids), 'source_metadata': {'fetched_at': data.get('source_fetched_at'), 'expires_at': data.get('expires_at'), 'raster_imagery_date': raw.get('photo', {}).get('imagery_date'), 'insights_imagery_date': data['inputs']['insights'].get('imageryDate')},
                'runtime': {'model_load_seconds': load_seconds, 'warm_end_to_end_seconds': warm_seconds,
                            'warm_image_embedding_seconds': warm_embedding, 'steady_end_to_end_seconds': steady,
                            'steady_image_embedding_seconds': embeddings, 'steady_median_seconds': float(np.median(steady)),
                            'scope': 'set_image + all prompts (whole roof + each face), synchronized; excludes Python/imports/data/metrics/preview'},
                'memory': memory, 'whole_roof_google_prior_overlap': overlap(whole, google), 'face_metrics': metrics,
                'sam_all_candidate_scores': all_scores,
                'limitations': ['Prior overlap is not independent accuracy; prompts contain Google shape information.',
                               'Cross-face leakage is overlap with other Google face priors; not verified physical ridge leakage.',
                               'SAM produces generic instance masks; no obstruction class or validated obstruction detection.',
                               'Georeferencing is not verified object registration; source timestamps may differ.',
                               'Memory samples are lower bounds, not a true peak. ru_maxrss is process lifetime high-water mark.']}
    np.savez_compressed(out / 'sam-masks.npz', whole=whole, faces=faces, face_priors=priors, google=google, face_ids=np.array(ids))
    (out / 'sam-metrics.json').write_text(json.dumps(metadata, indent=2, default=str))
    (out / 'sam-prompts.json').write_text(json.dumps([{key: value.tolist() if hasattr(value, 'tolist') else value for key, value in p.items()} for p in prompts], indent=2))
    preview(rgb, google, priors, whole, faces, ids, out / 'sam-comparison.png')
    print(json.dumps({'device': device, 'faces': len(ids), 'runtime': metadata['runtime'], 'whole_overlap': metadata['whole_roof_google_prior_overlap'], 'memory': memory}), flush=True)

if __name__ == '__main__':
    main()
