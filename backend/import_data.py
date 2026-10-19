"""Stream and atomically publish the county assessor pipe-delimited source files."""
import argparse, codecs, csv, hashlib, json, re, sys, tempfile
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from backend.app import DATABASE_URL, SCHEMA, connect, normalize

IMPORT_VERSION = 3  # Bump whenever parsing, normalization, or classification rules change.
EXPECTED = ['FolioKey','OwnerName','MailingAddress1','MailingAddress2','MailingCity','MailingState','MailingPostalCode','MailingCountry','SitusAddress','SitusUnitNumber','SitusCity','SitusPostalCode','PropertyType','DeedNumber','DeedDate','DeedType','LandValue','ImprovementValue','FCV','AssessedFCV','LPV','AssessedLPV','PUC','Lot','Parcel_Block','Parcel_Tract','LandClass','ImprvClass','RentalInd','LivingArea','TotalSqFt','ConstrYear','PoolSize','SalePrice','SaleDate','MCR_Key','MCR_Name','NumUnits','TaxAreaCode']


def detect_encoding(path, override=None):
    if override: return override
    decoder=codecs.getincrementaldecoder('utf-8')('strict')
    try:
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''): decoder.decode(chunk)
            decoder.decode(b'',final=True)
        return 'utf-8'
    except UnicodeDecodeError:
        return 'cp1252'

def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def field(row, name): return (row.get(name) or '').strip()
def classify_residential(property_type):
    """Map the source PropertyType label; unknown labels remain unknown."""
    value=(property_type or '').strip().upper()
    if value=='RESIDENTIAL': return True
    if value in {'COMMERCIAL','VACANT','AG'}: return False
    return None
def folio_ok(s): return bool(re.fullmatch(r'\d{8}[A-Za-z]?',s))
def postal(s): return re.sub(r'[^0-9]','',s)[:5]
def occupancy(row):
    rental=field(row,'RentalInd').upper()
    if rental=='Y': return 'likely_not_owner_occupied','Rental indicator is Y'
    if rental!='N': return 'unknown','Rental indicator is missing or invalid'
    ma, si=field(row,'MailingAddress1'),field(row,'SitusAddress')
    mc, sc=field(row,'MailingCity'),field(row,'SitusCity')
    mz, sz=postal(field(row,'MailingPostalCode')),postal(field(row,'SitusPostalCode'))
    mu=normalize(field(row,'MailingAddress2')); su=normalize(field(row,'SitusUnitNumber'))
    if not all((ma,si,mc,sc,mz,sz)) or field(row,'MailingState').upper()!='AZ' or field(row,'SitusPostalCode')=='' or field(row,'MailingCountry').upper() not in ('USA','US','UNITED STATES','UNITED STATES OF AMERICA'): return 'unknown','Mailing or situs comparison fields are incomplete'
    if normalize(ma)!=normalize(si) or normalize(mc)!=normalize(sc) or mz!=sz or mu!=su:
        return 'likely_not_owner_occupied','Mailing and situs addresses differ'
    return 'likely_owner_occupied','Mailing and situs address, city, ZIP, and unit match'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data-dir', required=True)
    p.add_argument('--snapshot-date', type=lambda x: __import__('datetime').date.fromisoformat(x))
    p.add_argument('--encoding', choices=['utf-8','cp1252'])
    args=p.parse_args(); files=sorted(Path(args.data_dir).glob('Secured_Master_BK*.txt'))
    if not files: p.error('no Secured_Master_BK*.txt files found')
    encodings={f.name:detect_encoding(f,args.encoding) for f in files}
    metadata=[{'name':f.name,'sha256':file_hash(f),'encoding':encodings[f.name],'transform_version':IMPORT_VERSION} for f in files]
    manifest={'files':metadata,'transform_version':IMPORT_VERSION,'snapshot_date':args.snapshot_date.isoformat() if args.snapshot_date else None}
    dataset_id=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with connect() as c:
        for migration in sorted(SCHEMA.parent.glob('*.sql')):
            for statement in migration.read_text().split(';'):
                if statement.strip(): c.execute(statement)
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('dataset:'+dataset_id,))
        if c.execute('SELECT 1 FROM datasets WHERE id=%s',(dataset_id,)).fetchone():
            print('Identical dataset already imported; no changes made.'); return
        # All changes, including activation, commit together. The old active version remains usable on failure.
        c.execute('CREATE TEMP TABLE import_stage (LIKE parcels INCLUDING DEFAULTS) ON COMMIT DROP')
        c.execute('CREATE TEMP TABLE import_rejects (source_file text, source_row bigint, reason text) ON COMMIT DROP')
        reject_spool=tempfile.SpooledTemporaryFile(max_size=1024*1024,mode='w+t',encoding='utf-8',newline='')
        reject_writer=csv.writer(reject_spool,delimiter='|')
        input_rows=imported=0
        with c.cursor().copy('COPY import_stage (dataset_id,parcel_id,apn,address,unit,city,postal_code,year_built,mcr_key,mcr_name,occupancy,occupancy_reason,source_file,source_row,search_norm,property_type,puc,residential) FROM STDIN') as cp:
            for path in files:
                enc=encodings[path.name]
                with path.open('r',encoding=enc,errors='strict',newline='') as f:
                    reader=csv.DictReader(f,delimiter='|')
                    header=reader.fieldnames or []
                    if header != EXPECTED:
                        raise ValueError(f'{path.name}: unexpected header')
                    for line,row in enumerate(reader, start=2):
                        input_rows+=1
                        if None in row or len(row)!=len(EXPECTED) or any(value is None for value in row.values()):
                            reject_writer.writerow((path.name,line,'wrong field count'))
                            continue
                        folio=field(row,'FolioKey')
                        if not folio_ok(folio):
                            reject_writer.writerow((path.name,line,'missing or invalid parcel identifier'))
                            continue
                        addr=field(row,'SitusAddress').upper(); city=field(row,'SitusCity').upper(); zipc=postal(field(row,'SitusPostalCode')); unit=field(row,'SitusUnitNumber').upper() or None
                        occ,reason=occupancy(row)
                        try: year=int(field(row,'ConstrYear')) if field(row,'ConstrYear') else None
                        except ValueError: year=None
                        key=field(row,'MCR_Key')
                        property_type=row.get('PropertyType') or ''
                        puc=row.get('PUC') or ''
                        cp.write_row((dataset_id,'04013:'+folio,folio,addr,unit,city,zipc,year,key or None,field(row,'MCR_Name') or None,occ,reason,path.name,line,normalize(' '.join(x for x in (addr,city,zipc,normalize(unit or '')) if x)),property_type,puc,classify_residential(property_type)))
                        imported+=1
                        if input_rows%100000==0: print(f'Processed {input_rows:,} rows',flush=True)
        # Copy quarantined reasons after the parcel COPY has ended; no rejected field values are stored.
        reject_spool.seek(0)
        with c.cursor().copy('COPY import_rejects (source_file,source_row,reason) FROM STDIN') as rejects_copy:
            for raw in reject_spool:
                filename,line,reason=raw.rstrip('\n').split('|',2)
                rejects_copy.write_row((filename,int(line),reason))
        reject_spool.close()
        # Deduplication deterministic by filename and source line; only the first key is retained.
        c.execute('''CREATE TEMP TABLE import_dupes ON COMMIT DROP AS
          SELECT source_file,source_row FROM (SELECT source_file,source_row,row_number() OVER(PARTITION BY dataset_id,parcel_id ORDER BY source_file,source_row) n FROM import_stage) x WHERE n>1''')
        c.execute("INSERT INTO import_rejects SELECT source_file,source_row,'duplicate parcel identifier' FROM import_dupes")
        c.execute('''INSERT INTO datasets(id,snapshot_date,input_rows,imported_rows,rejected_rows,files,active)
          VALUES(%s,%s,%s,0,0,%s,false)''',(dataset_id,args.snapshot_date,input_rows,Jsonb(metadata)))
        c.execute('''INSERT INTO parcels (
          dataset_id,parcel_id,apn,address,unit,city,postal_code,year_built,mcr_key,mcr_name,
          occupancy,occupancy_reason,source_file,source_row,search_norm,property_type,puc,residential
        ) SELECT
          s.dataset_id,s.parcel_id,s.apn,s.address,s.unit,s.city,s.postal_code,s.year_built,
          s.mcr_key,s.mcr_name,s.occupancy,s.occupancy_reason,s.source_file,s.source_row,
          s.search_norm,s.property_type,s.puc,s.residential
        FROM import_stage s LEFT JOIN import_dupes d USING(source_file,source_row) WHERE d.source_row IS NULL''')
        actual=c.execute('SELECT count(*) FROM parcels WHERE dataset_id=%s',(dataset_id,)).fetchone()[0]
        rejected=input_rows-actual
        c.execute('INSERT INTO rejected_rows SELECT %s,source_file,source_row,reason FROM import_rejects',(dataset_id,))
        c.execute('UPDATE datasets SET imported_rows=%s,rejected_rows=%s,active=false WHERE id=%s',(actual,rejected,dataset_id))
        c.execute('UPDATE datasets SET active=false WHERE active')
        c.execute('UPDATE datasets SET active=true WHERE id=%s',(dataset_id,))
    print(f'Published dataset {dataset_id}: input={input_rows:,}, imported={actual:,}, rejected={rejected:,}',flush=True)

if __name__=='__main__': main()
