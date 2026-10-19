"""Display saved raw model predictions; no inference, fitting or annotation."""
from pathlib import Path
import os
import json
import pickle
import numpy as np

ROOT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'cache/matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME',str(ROOT/'cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

source=pickle.loads((ROOT.parent/'data/inputs.pkl').read_bytes())
rgb=source['aligned']['rgb']
saved=json.loads((ROOT/'outputs/lines.json').read_text())
lines=np.array(saved['lines_yx']);scores=np.array(saved['scores'])
fig,axes=plt.subplots(1,2,figsize=(12,6.2),facecolor='white')
for i,ax in enumerate(axes):
    ax.imshow(rgb,interpolation='nearest');ax.axis('off')
    ax.set_xlim(-.5,rgb.shape[1]-.5);ax.set_ylim(rgb.shape[0]-.5,-.5)
    ax.set_title(['Cached photograph','RoofMapNet raw lines · score ≥ 0.8'][i],loc='left',fontsize=13)
    if i:
        for line,score in zip(lines,scores):
            if score>=.8:
                ax.plot(line[:,1]-.5,line[:,0]-.5,color='#20c4e3',lw=1.3)
fig.text(.03,.05,'Image-only inference · No drawn roof lines supplied · No manual edits or geometric cleanup',fontsize=11)
fig.text(.03,.02,'Includes solar data from Google · 2D line predictions; not a complete roof model or approved design',fontsize=11)
fig.tight_layout(rect=(.005,.085,.995,.98))
fig.savefig(ROOT/'outputs/focus.png',dpi=160)
