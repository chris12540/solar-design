# Local roof reconstruction experiments

Research scripts for reconstructing roof faces from image linework, Google Solar plane measurements, and cached DSM heights. Separate from the application backend; no roof result is design-ready or an AHJ compliance approval.

## Current direction

`roofmapnet-trial/` tests RGB-only roof-line graph prediction. `roof-fusion/` polygonizes that graph, checks interior height support, jointly fits compatible planes, and retains unresolved regions. `multi-roof-trial/` prepares a bounded five-house comparison with a request ledger and network-disabled local inference. Acquisition is currently blocked by the Solar API key's source-IP restriction; no multi-house quality result exists yet.

`google-cleanup/` and root-level Phase 1/Phase 2 files preserve earlier investigations. The template-based structural/3D prototype was rejected by the user. Keep 3D deferred; passing topology checks does not demonstrate a physically correct roof.

## Private inputs and outputs

This public repository includes original scripts, synthetic tests, dependency snapshots, empty visualization templates, and upstream source manifests. Raw assessor records, property imagery, saved Google responses, derived house geometry, manually drawn reference annotations, logs, experiment reports containing property-specific measurements, and model binaries are not included. Existing local files remain in the original workspace.

Create a separate experimental environment from `requirements.lock.txt`; the application requirements are independent. The snapshot reflects the development machine and may require compatible platform/Python wheels. Scripts require trusted locally generated `data/inputs.pkl` and, for some historical evaluations, private `reference.json` / `phase1-reference.json`. Never unpickle downloaded or untrusted inputs.

RoofMapNet wrappers expect authors' source under `roofmapnet-trial/vendor/` and a compatible runtime copy under `roofmapnet-trial/adapted/`. See `source-manifest.json` and wrapper code for pinned source and the three device-allocation substitutions. Weights are expected at `roofmapnet-trial/cache/weight-response`. Those third-party assets are not redistributed. The upstream model is non-commercial academic research; commercial permission has not been obtained. Other model experiments likewise require their respective upstream sources and licenses.

Visualization builders copy a data-free template into ignored `outputs/visualizations/`, then embed local experiment data. Generated visualizations remain private. The templates are fragments intended for the Codex visualization host, not standalone application pages.

## Verification

With experimental dependencies installed:

```sh
python -m unittest discover -s experiments/roof-vision/roof-fusion -p test_fusion.py -v
python -m unittest discover -s experiments/roof-vision/google-cleanup -p test_cleanup.py -v
```

Multi-roof acquisition is a paid action. It must be explicitly authorized and bounded before running `acquire.py`; existing authorization and ledgers are local, not bundled. Do not run acquisition to diagnose setup. `run_batch.py` is offline, freezes model/algorithm hashes, and refuses expired inputs. Its current selection stage uses existing local detached-home proxies; actual roof types require inspecting acquired imagery.

Google-derived sources and derivatives retain the original acquisition expiry. Generated experiment files are outside the application's automatic cache purge and require explicit local cleanup. No commercial-use or retention permission is implied by this repository.
