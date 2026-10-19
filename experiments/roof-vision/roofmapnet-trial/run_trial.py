"""Pinned RoofMapNet evaluation on cached RGB only. No training or API calls."""
from pathlib import Path
import os
import sys
import json
import hashlib
import pickle
import shutil
import resource
import socket
import time

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'cache/matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME',str(ROOT/'cache'))
import cv2
import numpy as np
import torch
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def deny_network(*args,**kwargs):
    raise RuntimeError('Network disabled during cached local inference')


def dummy_inputs(image,device,offset=0.):
    # Upstream evaluation computes unused target bookkeeping. Sentinel labels
    # match no image point and carry no roof geometry. No annotated inputs.
    return {'image':image,'mode':'validation',
            'target':{'jmap':torch.zeros((1,1,128,128),device=device),
                      'joff':torch.zeros((1,1,2,128,128),device=device),
                      'lmap':torch.zeros((1,128,128),device=device)},
            'meta':[{'junc':torch.tensor([[-10000.+offset,-10000.+offset]],device=device),
                     'jtyp':torch.zeros(1,dtype=torch.uint8,device=device),
                     'Lpos':torch.zeros((2,2),device=device),
                     'Lneg':torch.zeros((2,2),device=device)}]}


def main():
    torch.set_num_threads(8)
    torch.manual_seed(0);np.random.seed(0)
    adapted=ROOT/'adapted'
    shutil.copytree(ROOT/'vendor/roofmapnet',adapted/'roofmapnet',dirs_exist_ok=True)
    path=adapted/'roofmapnet/models/regression.py'
    text=path.read_text();assert text.count("device='cuda'")==3
    path.write_text(text.replace("device='cuda'","device=image.device"))
    sys.path.insert(0,str(adapted))
    from roofmapnet.config import C,M
    from roofmapnet.models.regression import MultitaskHead
    from roofmapnet.models.roofmapnet import RoofMapNet
    config=yaml.safe_load((ROOT/'vendor/config/config.yaml').read_text())
    C.update(config);M.update(config['model'])
    source_bytes=(BASE/'data/inputs.pkl').read_bytes()
    source=pickle.loads(source_bytes)  # Trusted export made by this project.
    rgb=source['aligned']['rgb']
    resized=cv2.resize(rgb,(512,512),interpolation=cv2.INTER_LINEAR).astype('float32')
    image=(resized-np.array(M.image.mean,dtype='float32'))/np.array(M.image.stddev,dtype='float32')
    image=torch.from_numpy(image.transpose(2,0,1).copy()).unsqueeze(0)
    socket.create_connection=deny_network;socket.socket.connect=deny_network
    device='cpu'
    started=time.perf_counter()
    model=RoofMapNet(depth=M.depth,head=lambda a,b:MultitaskHead(a,b),
                     num_stacks=M.num_stacks,num_blocks=M.num_blocks,
                     num_classes=sum(sum(M.head_size,[])))
    weights=ROOT/'cache/weight-response'
    state=torch.load(weights,map_location=device,weights_only=True)
    loaded=model.load_state_dict(state,strict=True)
    assert not loaded.missing_keys and not loaded.unexpected_keys
    model=model.to(device).eval()
    load_seconds=time.perf_counter()-started
    print('Strict checkpoint load passed. Parameters:',sum(p.numel() for p in model.parameters()),flush=True)
    out=ROOT/'outputs';out.mkdir(exist_ok=True)
    runs=[];predictions=[]
    for label,offset in [('cold',0.),('warm',0.),('sentinel_check',1234.)]:
        start=time.perf_counter()
        with torch.inference_mode():
            h=model(dummy_inputs(image,device,offset))['preds']
        elapsed=time.perf_counter()-start
        arrays={k:v[0].cpu().numpy() for k,v in h.items()}
        predictions.append(arrays)
        np.savez_compressed(out/f'{label}.npz',**arrays)
        runs.append({'label':label,'inference_seconds':elapsed,
                     'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
        print(json.dumps(runs[-1]),flush=True)
    reference=predictions[1]
    sentinel_invariant=all(np.array_equal(reference[k],predictions[2][k]) for k in ['lines','score','jmap','joff','lmap'])
    assert sentinel_invariant,'Unused target sentinel changed predicted geometry'
    lines,scores=reference['lines'],reference['score']
    unique={}
    for line,score in zip(lines,scores):
        if float(score)<=.1:
            continue
        ordered=sorted(tuple(float(v) for v in p) for p in line)
        key=tuple(ordered[0]+ordered[1])
        unique[key]=(line,float(score))
    ordered=sorted(unique.values(),key=lambda x:-x[1])
    lines=np.array([item[0] for item in ordered]);scores=np.array([item[1] for item in ordered])
    native=lines*np.array([rgb.shape[0]/128,rgb.shape[1]/128])
    thresholds=[.5,.8,.95]
    report={'status':'completed_isolated_evaluation_not_production','device':device,
            'torch_version':torch.__version__,'weights_load':'strict; no missing or unexpected keys',
            'weight_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),
            'source_input_sha256':hashlib.sha256(source_bytes).hexdigest(),
            'source_expires_at':str(source['expires_at']),
            'preprocessing':{'source_shape':list(rgb.shape),'model_input_shape':[1,3,512,512],
                             'resize':'OpenCV bilinear; square resize; no new image detail',
                             'normalization_mean':list(M.image.mean),'normalization_stddev':list(M.image.stddev)},
            'load_seconds':load_seconds,'runs':runs,'sentinel_invariant':sentinel_invariant,
            'cold_warm_identical':all(np.array_equal(predictions[0][k],reference[k]) for k in reference),
            'unique_lines_above_stock_0_1_cutoff':len(lines),
            'line_counts':{str(t):int((scores>=t).sum()) for t in thresholds},
            'google_requests':0,'network_during_inference':'disabled','annotations_used':False,
            'adaptations':['Three hard-coded CUDA target-bookkeeping allocations use image.device',
                           'Blank target maps and unmatched sentinel metadata for image-only inference',
                           'Batch size one, stock configuration and weights, 512-square cached RGB resize',
                           'Exact duplicate cyclic-padding lines removed for display only'],
            'limits':['One house only; no independent accuracy benchmark',
                      'Raw 2D graph lines, not a complete 3D or AHJ-compliant design',
                      'No roof-line editing, manual snapping or geometry repair performed',
                      'Model scores are not calibrated accuracy probabilities',
                      'Evaluation does not establish commercial-use permission']}
    (out/'report.json').write_text(json.dumps(report,indent=2))
    (out/'lines.json').write_text(json.dumps({'coordinate_system':'native RGB pixel-corner coordinates, y then x',
        'lines_yx':native.tolist(),'scores':scores.tolist()},indent=2))
    fig,axes=plt.subplots(1,4,figsize=(16,4.8),facecolor='white')
    for i,ax in enumerate(axes):
        ax.imshow(rgb,interpolation='nearest');ax.axis('off')
        ax.set_xlim(-.5,rgb.shape[1]-.5);ax.set_ylim(rgb.shape[0]-.5,-.5)
        if i==0:
            ax.set_title('Cached photo',loc='left',fontsize=12)
        else:
            threshold=thresholds[i-1]
            for line,score in zip(native,scores):
                if score>=threshold:
                    ax.plot(line[:,1]-.5,line[:,0]-.5,color='#20c4e3',lw=1.1)
            ax.set_title(f'RoofMapNet ≥ {threshold} · {(scores>=threshold).sum()} lines',loc='left',fontsize=12)
    fig.text(.025,.055,'Raw predicted lines at three fixed score thresholds · Same image and scale · No manual edits or supplied roof annotations',fontsize=10)
    fig.text(.025,.02,'Includes solar data from Google · Model output is 2D roof linework; heights, obstructions and AHJ rules still require separate work',fontsize=10)
    fig.tight_layout(rect=(.005,.09,.995,.98));fig.savefig(out/'comparison.png',dpi=170);plt.close(fig)
    print(json.dumps({k:report[k] for k in ['line_counts','sentinel_invariant','cold_warm_identical','load_seconds']},indent=2),flush=True)


if __name__=='__main__':
    main()
