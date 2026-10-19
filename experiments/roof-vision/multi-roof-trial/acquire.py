"""Bounded five-house acquisition. Read-only parcel DB; no retries or app writes."""
from pathlib import Path
import hashlib
import json
import os
import pickle
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from scripts.dev import environment
from backend.property_facts import classify_dwelling
from backend import solar_roof
import psycopg

PROFILES = [
    ('R1', 'GILA BEND ESTATES', 1965),
    ('R2', 'PALO VIENTO 1', 1976),
    ('R3', 'VISTA DE LA TIERRA', 1980),
    ('R4', 'ARROWHEAD BY THE LAKES LOT 1-203', 1988),
    ('R5', 'ANTHEM UNIT 10 AMD', 2000),
]


def select():
    env = environment()
    with psycopg.connect(env['DATABASE_URL'],
                         options='-c default_transaction_read_only=on', connect_timeout=5) as c:
        rows = c.execute('''SELECT p.dataset_id,p.parcel_id,p.address,p.city,p.mcr_name,
          p.year_built,p.puc,p.property_type,ST_AsGeoJSON(p.county_geometry),
          ST_Area(p.county_geometry::geography)
          FROM parcels p JOIN datasets d ON d.id=p.dataset_id AND d.active
          WHERE p.county_geometry IS NOT NULL AND p.year_built IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM roof_reconstructions r
            WHERE r.dataset_id=p.dataset_id AND r.parcel_id=p.parcel_id)''').fetchall()
    chosen = []
    for label, subdivision, year in PROFILES:
        candidates = [r for r in rows if r[4] == subdivision and 400 < r[9] < 2500
                      and classify_dwelling(r[6], r[7]) == 'detached']
        if not candidates:
            raise ValueError(f'No eligible parcel for {label}; stop before paid requests')
        candidates.sort(key=lambda r: (abs(r[5]-year), abs(r[9]-900), r[1]))
        r = candidates[0]
        chosen.append(dict(trial_id=label, dataset_id=r[0], id=r[1], address=r[2],
                           city=r[3], subdivision=r[4], year_built=r[5],
                           geometry=json.loads(r[8]), lot_area_m2=r[9],
                           selection='Distinct subdivision, age and parcel size; roof type unverified',
                           role='holdout_for_future_changes' if label in ('R4', 'R5') else 'development'))
    assert len({(h['dataset_id'], h['id']) for h in chosen}) == 5
    return chosen


def main():
    selection = ROOT/'selection.json'
    if not selection.exists():
        selection.write_text(json.dumps(select(), indent=2))
    homes = json.loads(selection.read_text())
    if '--select-only' in sys.argv:
        print(json.dumps([{k: h[k] for k in ('trial_id','subdivision','year_built','role')} for h in homes]))
        return
    ledger_path = ROOT/'request-ledger.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {
        'authorized_houses': 5, 'budget_usd': 1, 'base_insights_usd': .01,
        'base_data_layers_usd': .075, 'attempts': [], 'retries': False,
        'pricing_basis': 'https://developers.google.com/maps/billing-and-pricing/pricing',
        'billing_account_allowances': 'unverified', 'approval': 'User approved five roofs, $1 cap'}
    os.environ.update(environment())
    original_json = solar_roof._json_request
    original_raster = solar_roof._raster_request
    def persist():
        ledger_path.write_text(json.dumps(ledger, indent=2))
    def json_request(url, key):
        kind = 'insights' if url.startswith(solar_roof.INSIGHTS_ENDPOINT) else 'layers'
        attempt = ledger['attempts'][-1]
        if kind in attempt['requests']:
            raise RuntimeError('Duplicate request blocked')
        charge = ledger['base_insights_usd'] if kind == 'insights' else ledger['base_data_layers_usd']
        spent = sum(a['reserved_base_cost_usd'] for a in ledger['attempts'])
        if spent + charge > .42500001 or spent + charge > ledger['budget_usd']:
            raise RuntimeError('Acquisition request cap reached')
        attempt['requests'].append(kind)
        attempt['reserved_base_cost_usd'] += charge
        persist()  # Reserve before transmission; process failure cannot silently retry.
        try:
            return original_json(url, key)
        except HTTPError as exc:
            # Preserve categorical diagnostics, never messages/URLs/credentials.
            diagnostic = {'http_status': exc.code}
            try:
                error = json.loads(exc.read(65536)).get('error', {})
                status = error.get('status', '')
                if isinstance(status, str) and status.replace('_','').isalnum():
                    diagnostic['google_status'] = status
                diagnostic['reasons'] = [d['reason'] for d in error.get('details', [])
                    if isinstance(d, dict) and isinstance(d.get('reason'), str)
                    and d['reason'].replace('_','').isalnum()]
            except (ValueError, TypeError, AttributeError):
                pass
            attempt['diagnostic'] = diagnostic
            persist()
            raise
        except URLError as exc:
            attempt['diagnostic'] = {'transport_error_type': type(exc.reason).__name__}
            persist()
            raise
    def raster_request(url, key):
        attempt = ledger['attempts'][-1]
        if attempt['raster_attempts'] >= 3:
            raise RuntimeError('Raster request cap reached')
        attempt['raster_attempts'] += 1
        persist()
        return original_raster(url, key)
    solar_roof._json_request = json_request
    solar_roof._raster_request = raster_request
    diagnostic_only = '--diagnostic-retry' in sys.argv
    for home in homes[:1] if diagnostic_only else homes:
        label = home['trial_id']
        if diagnostic_only and any(a.get('diagnostic_retry') for a in ledger['attempts']):
            raise RuntimeError('Single diagnostic retry already used')
        if not diagnostic_only and any(a['trial_id'] == label for a in ledger['attempts']):
            print(label, 'already attempted; no retry', flush=True)
            continue
        ledger['attempts'].append(dict(trial_id=label, started_at=datetime.now(timezone.utc).isoformat(),
            requests=[], raster_attempts=0, reserved_base_cost_usd=0, status='started',
            diagnostic_retry=diagnostic_only))
        persist()
        try:
            if diagnostic_only:
                parcel, point = solar_roof._point(home)
                from urllib.parse import urlencode
                params = {'location.latitude':format(point.y,'.8f'),
                          'location.longitude':format(point.x,'.8f'),'requiredQuality':'HIGH'}
                insights = json_request(solar_roof.INSIGHTS_ENDPOINT+'?'+urlencode(params),
                                        os.environ['GOOGLE_SOLAR_API_KEY'].strip())
                folder = ROOT/'houses'/label
                folder.mkdir(parents=True, exist_ok=True)
                (folder/'diagnostic-insights.json').write_text(json.dumps({
                    'insights':insights,'fetched_at':datetime.now(timezone.utc).isoformat()}, indent=2))
                ledger['attempts'][-1]['status'] = 'diagnostic_success_no_layers_requested'
                persist()
                print(label, ledger['attempts'][-1]['status'], flush=True)
                return
            inputs = solar_roof.fetch_roof_inputs(home)
            folder = ROOT/'houses'/label
            folder.mkdir(parents=True, exist_ok=True)
            content = pickle.dumps({'home':home, 'inputs':inputs}, protocol=5)
            (folder/'source.pkl').write_bytes(content)
            ledger['attempts'][-1].update(status='complete' if inputs.get('rgb') else 'rgb_unavailable',
                source_sha256=hashlib.sha256(content).hexdigest(), expires_at=inputs['expires_at'],
                source_metadata=inputs.get('source_metadata',{}))
        except Exception as exc:
            # No exception text: third-party errors may contain request URLs/credentials.
            ledger['attempts'][-1].update(status='failed', error_type=type(exc).__name__)
        persist()
        print(label, ledger['attempts'][-1]['status'], flush=True)
    print('Completed bounded acquisition; no retries. Reserved base charges USD',
          round(sum(a['reserved_base_cost_usd'] for a in ledger['attempts']), 4), flush=True)


if __name__ == '__main__':
    main()
