# Aurora benchmark

Scores a saved roof reconstruction against an Aurora Solar DXF design of the same house. It exists so roof accuracy can be measured, not eyeballed. Aurora is a reference, not surveyed ground truth. See [the accuracy plan](../../../docs/roof-accuracy-plan.md).

## Run

```sh
# 1. Save the app's reconstruction for a house (reads the local database; makes no paid calls)
.venv/bin/python experiments/roof-vision/aurora-benchmark/export_result.py \
    --parcel-id <parcel-id> --out experiments/roof-vision/aurora-benchmark/private/<house>/result.json
# 2. Put Aurora's DXF next to it as private/<house>/design.dxf, then score it
.venv/bin/python experiments/roof-vision/aurora-benchmark/benchmark.py \
    --dxf .../design.dxf --result .../result.json --panel-reference 119 --out .../report.json
# 3. Accept the current scores as the floor, then gate future changes against it
... benchmark.py ... --write-baseline .../baseline.json
... benchmark.py ... --baseline .../baseline.json        # exit code 1 on regression
```

Tests (no real data needed; the private-house test skips when `private/` is empty):

```sh
.venv/bin/python -m unittest discover -s experiments/roof-vision/aurora-benchmark -p "test_*.py" -v
```

## What is scored

The DXF has no georeference, so its outline is registered to ours by rotation and shift (maximising outline IoU). That fit absorbs any constant offset between the two sources, so overlap numbers are slightly optimistic. Scores are reported for three pipeline stages: `raw`, `refined` and `fitted`, so a regression can be traced to the stage that caused it.

| Report section | Meaning |
|---|---|
| `outline` | IoU, area ratio, missing (Aurora-only) and extra (ours-only) area and regions, edge distance in both directions |
| `stages.<stage>` | Face count, area-weighted best-face IoU (all faces and faces of at least 3 m2), face recall (area of Aurora faces reproduced at IoU of at least 0.5), unmatched faces, which of our faces merge several Aurora faces, which Aurora faces we split |
| `obstructions` | Recall of Aurora vents and skylights, false positives, and whether a false positive sits on an Aurora roof face (a likely raised roof step) |
| `panels` | Aurora's module count, size and count per face, optionally against a reference count (for example Google's maximum) |
| `orientation` | Azimuth and pitch error per face, only when a reference is supplied |

Face ids (`A0`, `A1`, ...) rank Aurora faces by area, largest first, and are stable for a given DXF.

## Regression gate

`GATES` in `benchmark.py` lists the gated metrics, which direction is better and the allowed slack. A metric that gets worse by more than its slack fails the run. Improvements never fail. Metrics missing from the baseline or the report are skipped.

## Private data

The repository is public. `private/` is git-ignored and holds, per house: `design.dxf`, `result.json`, `baseline.json`, `report.json`. Do not commit any of it.

`result.json` is derived from Google Solar data. `export_result.py` records the source expiry in `_export.expires_at` and drops the photo. The private test skips a house once its data has expired. Delete the folder by then; generated files are outside the app's automatic cache purge.

## Known limits

- Only the largest connected structure in the DXF is scored as the roof (designs often include neighbouring roofs for shading); `--all-structures` keeps everything. The ignored area is listed in `meta.dxf.warnings`.
- DXF face polygons come from noding the `Buildings` lines. Sliver faces under 0.05 m2 are dropped. A DXF whose roof lines do not close will give fewer faces; check `meta.dxf.warnings`.
- The DXF carries no azimuth, pitch or heights. Orientation scoring needs a separate reference. The `--reference` file format (`{"A0": {"azimuth_deg": .., "pitch_deg": ..}}`) is provisional until Aurora's per-face export is available.
- Only the `Buildings`, `Modules` and `Obstructions` layers are used. `Setbacks`, `Fire_Pathways` and `Property_Lines` are counted but not scored yet.
- One house is not a result. Add more designs before drawing conclusions.
