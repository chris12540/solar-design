import csv
import hashlib

from backend.fact_importer import (EXPECTED_HEADER, import_facts, inspect_source_files, parse_date,
    parse_nonnegative_decimal, parse_nonnegative_int)


def _row(**overrides):
    values={name:'' for name in EXPECTED_HEADER}
    values.update({'FolioKey':'12345678','SaleDate':'10132026','FCV':'245000',
        'RentalInd':'Y','NumUnits':'1','PUC':'0141','PropertyType':'RESIDENTIAL','ConstrYear':'1998'})
    values.update(overrides)
    return values


def _source(tmp_path, rows):
    path=tmp_path/'Secured_Master_BK01.txt'
    with path.open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=EXPECTED_HEADER,delimiter='|',lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    return path, [{'name':path.name,'sha256':digest,'encoding':'utf-8'}]


def test_source_fact_importer_parses_only_safe_fields_and_exact_source_identity(tmp_path):
    path, manifest=_source(tmp_path,[_row(),_row(FolioKey='87654321',SaleDate='02312026',FCV='-1',NumUnits='not-a-number')])
    files, facts=inspect_source_files(tmp_path,manifest)
    facts=list(facts)
    assert files[0]['sha256']==manifest[0]['sha256']
    assert facts[0]=={'parse_ok':True,'parcel_id':'04013:12345678','source_file':path.name,'source_row':2,
        'source_sha256':manifest[0]['sha256'],'sale_date':parse_date('10132026'),
        'fcv':parse_nonnegative_decimal('245000'),'num_units':1,'puc':'0141',
        'property_type':'RESIDENTIAL','construction_year':1998,'rental_ind':'Y'}
    assert facts[1]['sale_date'] is None and facts[1]['fcv'] is None and facts[1]['num_units'] is None
    assert 'OwnerName' not in facts[0] and 'MailingAddress1' not in facts[0]


def test_source_hash_mismatch_and_invalid_source_dates_remain_unknown(tmp_path):
    _source(tmp_path,[_row()])
    try:
        inspect_source_files(tmp_path,[{'name':'Secured_Master_BK01.txt','sha256':'0'*64,'encoding':'utf-8'}])
    except ValueError as exc:
        assert 'hash' in str(exc)
    else:
        raise AssertionError('changed source was accepted')
    assert parse_date('02312026') is None
    assert parse_date('') is None
    assert parse_nonnegative_decimal('NaN') is None
    assert parse_nonnegative_int('-1') is None


def test_fact_import_is_idempotent_and_hash_failure_keeps_prior_facts(tmp_path,appmod):
    path, _=_source(tmp_path,[_row(),_row()])
    with path.open('a',encoding='utf-8') as file:
        file.write('malformed|row\n')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    dataset='fact-import-fixture'
    manifest=[{'name':path.name,'sha256':digest,'encoding':'utf-8','transform_version':3}]
    with appmod.connect() as c:
        c.execute('''INSERT INTO datasets(id,input_rows,imported_rows,rejected_rows,files,active)
          VALUES(%s,1,1,0,%s,false)''',(dataset,__import__('json').dumps(manifest)))
        c.execute('''INSERT INTO parcels(dataset_id,parcel_id,apn,address,city,postal_code,occupancy,
          occupancy_reason,source_file,source_row,search_norm)
          VALUES(%s,'04013:12345678','12345678','1 TEST ST','PHOENIX','85001','unknown','fixture',%s,2,'1 TEST ST')''',
          (dataset,path.name))
        c.execute("INSERT INTO rejected_rows(dataset_id,source_file,source_row,reason) VALUES(%s,%s,3,'duplicate parcel identifier'),(%s,%s,4,'wrong field count')",
          (dataset,path.name,dataset,path.name))
    first=import_facts(tmp_path,dataset,appmod.DATABASE_URL)
    retry=import_facts(tmp_path,dataset,appmod.DATABASE_URL)
    assert first['fact_count']==1 and first['skipped_rejected_rows']==2 and retry['unchanged'] is True
    path.write_text(path.read_text().replace('245000','275000'))
    try:
        import_facts(tmp_path,dataset,appmod.DATABASE_URL)
    except ValueError as exc:
        assert 'hash' in str(exc)
    else:
        raise AssertionError('changed source was accepted')
    with appmod.connect() as c:
        stored=c.execute('SELECT fcv,rental_ind FROM parcel_source_facts WHERE dataset_id=%s',(dataset,)).fetchone()
    assert stored[0]==245000 and stored[1]=='Y'
