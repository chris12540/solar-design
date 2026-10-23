"""Export one saved roof reconstruction from the local database to a JSON file.

Reads only; never fetches paid data. The photo is dropped from the export. The
output is Google-derived and keeps the source expiry in `_export.expires_at`;
delete it by then. Keep it under the ignored private/ folder.

    .venv/bin/python experiments/roof-vision/aurora-benchmark/export_result.py \
        --parcel-id <parcel-id> --out experiments/roof-vision/aurora-benchmark/private/house/result.json
"""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def database_url(env=None):
    env = os.environ if env is None else env
    if env.get('DATABASE_URL'):
        return env['DATABASE_URL']
    dotenv = ROOT / '.env'
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if line.startswith('DATABASE_URL='):
                return line.split('=', 1)[1].strip()
    raise SystemExit('DATABASE_URL is not set and not found in .env')


def strip(result):
    out = dict(result)
    if isinstance(out.get('photo'), dict):
        out['photo'] = {k: v for k, v in out['photo'].items() if k != 'data_url'}
    return out


def export(parcel_id, out, dataset_id=None):
    import psycopg
    sql = '''SELECT result, source_fetched_at, expires_at, algorithm_version, dataset_id
             FROM roof_reconstructions WHERE parcel_id=%s AND expires_at > now()'''
    args = [parcel_id]
    if dataset_id:
        sql += ' AND dataset_id=%s'
        args.append(dataset_id)
    sql += ' ORDER BY source_fetched_at DESC LIMIT 1'
    with psycopg.connect(database_url()) as c:
        row = c.execute(sql, args).fetchone()
    if not row:
        raise SystemExit(f'no unexpired roof reconstruction for parcel {parcel_id}')
    payload = strip(row[0])
    payload['_export'] = {'parcel_id': parcel_id, 'dataset_id': str(row[4]),
                          'fetched_at': row[1].isoformat(), 'expires_at': row[2].isoformat(),
                          'algorithm_version': row[3]}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload))
    return payload['_export']


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--parcel-id', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--dataset-id')
    args = p.parse_args(argv)
    meta = export(args.parcel_id, args.out, args.dataset_id)
    print(f"wrote {args.out}; source expires {meta['expires_at']}")


if __name__ == '__main__':
    main()
