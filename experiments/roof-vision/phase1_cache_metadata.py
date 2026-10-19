"""Recover only capture dates from the matching local cache, read-only."""
from pathlib import Path
import hashlib
import json
import pickle
import sys

ROOT = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.dev import environment
import psycopg


def main():
    source = pickle.loads((ROOT / 'data/inputs.pkl').read_bytes())
    expected = hashlib.sha256(source['inputs']['dsm']).hexdigest()
    matches = []
    try:
        with psycopg.connect(environment()['DATABASE_URL'],
                             options='-c default_transaction_read_only=on',
                             connect_timeout=5) as connection:
            rows = connection.execute('''SELECT source_metadata, source_fetched_at,
                expires_at, dsm FROM roof_reconstructions WHERE expires_at > now()''')
            for metadata, fetched, expires, dsm in rows:
                if hashlib.sha256(bytes(dsm)).hexdigest() != expected:
                    continue
                matches.append({
                    'source_metadata': {key: (metadata or {}).get(key) for key in
                        ('insights_imagery_date', 'raster_imagery_date')},
                    'source_fetched_at': fetched.isoformat(),
                    'expires_at': expires.isoformat(),
                })
    except psycopg.OperationalError:
        raise SystemExit('Local cache unavailable; no connection details printed.') from None
    report = {'match_basis': 'SHA-256 equality of cached DSM bytes',
              'dsm_sha256': expected, 'matches': matches,
              'provenance': 'Read-only local application cache; no source HTTP requests.'}
    (ROOT / 'data/phase1-cache-metadata.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'matching_cache_rows': len(matches),
                      'capture_dates': [item['source_metadata'] for item in matches]}))


if __name__ == '__main__':
    main()
