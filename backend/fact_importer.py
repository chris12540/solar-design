"""Optional assessor fact import, joined by exact dataset source filename and row."""
import argparse
import csv
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from backend.import_data import detect_encoding, file_hash

FACT_TRANSFORM_VERSION = 2
EXPECTED_HEADER = [
    'FolioKey','OwnerName','MailingAddress1','MailingAddress2','MailingCity','MailingState',
    'MailingPostalCode','MailingCountry','SitusAddress','SitusUnitNumber','SitusCity','SitusPostalCode',
    'PropertyType','DeedNumber','DeedDate','DeedType','LandValue','ImprovementValue','FCV','AssessedFCV',
    'LPV','AssessedLPV','PUC','Lot','Parcel_Block','Parcel_Tract','LandClass','ImprvClass','RentalInd',
    'LivingArea','TotalSqFt','ConstrYear','PoolSize','SalePrice','SaleDate','MCR_Key','MCR_Name',
    'NumUnits','TaxAreaCode'
]


def parse_date(value):
    value = (value or '').strip()
    if not value:
        return None
    if re.fullmatch(r'\d{8}', value):
        try:
            return datetime.strptime(value, '%m%d%Y').date()
        except ValueError:
            return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_nonnegative_decimal(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        amount = Decimal(value.replace(',', '').replace('$', ''))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def parse_nonnegative_int(value):
    value = (value or '').strip()
    if not value or not re.fullmatch(r'\d+', value):
        return None
    try:
        number = int(value)
        return number if number <= 2_147_483_647 else None
    except ValueError:
        return None


def inspect_source_files(data_dir, expected_files):
    """Verify hashes and headers before returning a bounded-memory row iterator."""
    expected = {item['name']: item for item in expected_files}
    if not expected:
        raise ValueError('Dataset has no source file manifest')
    paths = {path.name: path for path in Path(data_dir).glob('Secured_Master_BK*.txt')}
    if set(paths) != set(expected):
        raise ValueError('Source file names do not match the dataset manifest')
    files = []
    for name in sorted(paths):
        path, manifest = paths[name], expected[name]
        digest = file_hash(path)
        if digest != manifest.get('sha256'):
            raise ValueError(f'{name}: source hash does not match the dataset manifest')
        encoding = manifest.get('encoding') or detect_encoding(path)
        files.append({'name': name, 'sha256': digest, 'encoding': encoding,
                      'transform_version': FACT_TRANSFORM_VERSION})
        with path.open('r', encoding=encoding, errors='strict', newline='') as source:
            reader = csv.DictReader(source, delimiter='|')
            if reader.fieldnames != EXPECTED_HEADER:
                raise ValueError(f'{name}: unexpected source header')
    def fact_rows():
        for item in files:
            path = paths[item['name']]
            with path.open('r', encoding=item['encoding'], errors='strict', newline='') as source:
                reader = csv.DictReader(source, delimiter='|')
                reader.fieldnames  # Consume the header without discarding the first data row.
                for line, row in enumerate(reader, start=2):
                    valid = not (None in row or len(row) != len(EXPECTED_HEADER) or
                                 any(value is None for value in row.values()))
                    folio = (row.get('FolioKey') or '').strip() if valid else ''
                    valid = valid and bool(re.fullmatch(r'\d{8}[A-Za-z]?', folio))
                    yield {
                        'parse_ok': valid,
                        'parcel_id': '04013:' + folio if valid else None,
                        'source_file': item['name'], 'source_row': line,
                        'source_sha256': item['sha256'],
                        'sale_date': parse_date(row.get('SaleDate')) if valid else None,
                        'fcv': parse_nonnegative_decimal(row.get('FCV')) if valid else None,
                        'num_units': parse_nonnegative_int(row.get('NumUnits')) if valid else None,
                        'puc': ((row.get('PUC') or '').strip() or None) if valid else None,
                        'property_type': ((row.get('PropertyType') or '').strip() or None) if valid else None,
                        'construction_year': parse_nonnegative_int(row.get('ConstrYear')) if valid else None,
                        'rental_ind': ((row.get('RentalInd') or '').strip() or None) if valid else None,
                    }
    return files, fact_rows()


def import_facts(data_dir, dataset_id, database_url):
    """Validate all source files before atomically publishing separate fact tables."""
    with psycopg.connect(database_url) as c:
        row = c.execute('SELECT files,snapshot_date FROM datasets WHERE id=%s', (dataset_id,)).fetchone()
        if not row:
            raise ValueError('Dataset not found')
        files, facts = inspect_source_files(data_dir, row[0])
        manifest_digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('fact-import:' + dataset_id,))
        old = c.execute('SELECT source_files FROM parcel_source_fact_snapshots WHERE dataset_id=%s', (dataset_id,)).fetchone()
        if old and old[0] == files:
            rejected_count = c.execute('''SELECT count(*) FROM rejected_rows
              WHERE dataset_id=%s AND source_file=ANY(%s)''',
              (dataset_id,[item['name'] for item in files])).fetchone()[0]
            return {'dataset_id': dataset_id, 'fact_count': c.execute(
                'SELECT count(*) FROM parcel_source_facts WHERE dataset_id=%s', (dataset_id,)).fetchone()[0],
                'skipped_rejected_rows': rejected_count,
                'source_manifest_sha256': manifest_digest, 'unchanged': True}
        c.execute('''CREATE TEMP TABLE fact_source_stage (
          parse_ok boolean NOT NULL, parcel_id text, source_file text NOT NULL, source_row bigint NOT NULL,
          source_sha256 text NOT NULL, sale_date date, fcv numeric, num_units integer, puc text,
          property_type text, construction_year integer, rental_ind text) ON COMMIT DROP''')
        with c.cursor().copy('''COPY fact_source_stage(parse_ok,parcel_id,source_file,source_row,source_sha256,
          sale_date,fcv,num_units,puc,property_type,construction_year,rental_ind) FROM STDIN''') as cp:
            for fact in facts:
                cp.write_row((fact['parse_ok'], fact['parcel_id'], fact['source_file'], fact['source_row'],
                    fact['source_sha256'], fact['sale_date'], fact['fcv'], fact['num_units'], fact['puc'],
                    fact['property_type'], fact['construction_year'], fact['rental_ind']))
        invalid = c.execute('''SELECT count(*) FROM fact_source_stage s
          LEFT JOIN rejected_rows r ON r.dataset_id=%s AND r.source_file=s.source_file AND r.source_row=s.source_row
          LEFT JOIN parcels p ON p.dataset_id=%s AND p.parcel_id=s.parcel_id
            AND p.source_file=s.source_file AND p.source_row=s.source_row
          WHERE r.source_row IS NULL AND (NOT s.parse_ok OR p.parcel_id IS NULL)''',
          (dataset_id,dataset_id)).fetchone()[0]
        if invalid:
            raise ValueError(f'{invalid} source row(s) are not an exact retained parcel row or known rejection')
        skipped = c.execute('''SELECT count(*) FROM fact_source_stage s JOIN rejected_rows r
          ON r.dataset_id=%s AND r.source_file=s.source_file AND r.source_row=s.source_row''',
          (dataset_id,)).fetchone()[0]
        c.execute('''CREATE TEMP TABLE fact_stage (LIKE parcel_source_facts INCLUDING DEFAULTS) ON COMMIT DROP''')
        c.execute('''INSERT INTO fact_stage(dataset_id,parcel_id,source_file,source_row,source_sha256,
          sale_date,fcv,num_units,puc,property_type,construction_year,rental_ind)
          SELECT %s,s.parcel_id,s.source_file,s.source_row,s.source_sha256,s.sale_date,s.fcv,s.num_units,
            s.puc,s.property_type,s.construction_year,s.rental_ind FROM fact_source_stage s
          JOIN parcels p ON p.dataset_id=%s AND p.parcel_id=s.parcel_id
            AND p.source_file=s.source_file AND p.source_row=s.source_row
          WHERE s.parse_ok''', (dataset_id,dataset_id))
        staged_count = c.execute('SELECT count(*) FROM fact_stage').fetchone()[0]
        parcel_count = c.execute('SELECT count(*) FROM parcels WHERE dataset_id=%s', (dataset_id,)).fetchone()[0]
        if staged_count != parcel_count:
            raise ValueError(f'Fact rows cover {staged_count} of {parcel_count} retained parcels')
        c.execute('DELETE FROM parcel_source_facts WHERE dataset_id=%s', (dataset_id,))
        c.execute('INSERT INTO parcel_source_facts SELECT * FROM fact_stage')
        c.execute('''INSERT INTO parcel_source_fact_snapshots(dataset_id,source_files,source_snapshot_date,transform_version)
          VALUES(%s,%s,%s,%s) ON CONFLICT(dataset_id) DO UPDATE SET source_files=EXCLUDED.source_files,
          source_snapshot_date=EXCLUDED.source_snapshot_date,transform_version=EXCLUDED.transform_version,
          imported_at=now()''', (dataset_id, Jsonb(files), row[1], FACT_TRANSFORM_VERSION))
        return {'dataset_id': dataset_id, 'fact_count': staged_count,
                'skipped_rejected_rows': skipped,
                'source_manifest_sha256': manifest_digest, 'unchanged': False}


def main():
    parser = argparse.ArgumentParser(description='Import optional assessor sale/value facts for an existing dataset.')
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--dataset-id', required=True)
    parser.add_argument('--database-url', default=None)
    args = parser.parse_args()
    import os
    database_url = args.database_url or os.getenv('DATABASE_URL')
    if not database_url:
        parser.error('DATABASE_URL or --database-url is required')
    print(json.dumps(import_facts(args.data_dir, args.dataset_id, database_url), sort_keys=True))


if __name__ == '__main__':
    main()
