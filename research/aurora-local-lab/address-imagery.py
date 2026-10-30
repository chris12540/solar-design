"""Isolated worker for address lookup and explicit imagery acquisition.

JSON stdin/stdout only. No keys, provider URLs or exception messages returned.
"""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

ROOT=Path(__file__).resolve().parent
PRODUCTION=Path('/Users/chris/code/solar-designer')
sys.path.insert(0,str(PRODUCTION))


def config():
    from scripts.dev import environment
    return environment()


def local_search(query):
    import psycopg
    values=config()
    if urlsplit(values['DATABASE_URL']).hostname not in ('localhost','127.0.0.1','::1'):
        raise RuntimeError('Local database required')
    terms=re.findall(r'[A-Z0-9]+',query.upper())
    aliases={'WEST':'W','EAST':'E','NORTH':'N','SOUTH':'S','ARIZONA':'AZ','STREET':'ST','AVENUE':'AVE','ROAD':'RD','DRIVE':'DR','LANE':'LN'}
    terms=[aliases.get(term,term) for term in terms]
    if not terms or len(terms)>30:return []
    expression="upper(address || ' ' || city || ' AZ ' || postal_code)"
    filters=' AND '.join(expression+' LIKE %s' for _ in terms)
    with psycopg.connect(values['DATABASE_URL'],connect_timeout=5,options='-c default_transaction_read_only=on -c statement_timeout=10000') as c:
        rows=c.execute('''SELECT DISTINCT ON (parcel_id) address,city,postal_code,parcel_id,
          ST_AsGeoJSON(county_geometry)::json FROM parcels WHERE county_geometry IS NOT NULL AND '''+filters+
          ' ORDER BY parcel_id,dataset_id LIMIT 12',tuple('%'+term+'%' for term in terms)).fetchall()
    return [{'address':f'{r[0]}, {r[1]}, AZ {r[2]}','geometry':r[4],
             'identity':'parcel:'+r[3],'provider':'local-parcels'} for r in rows]


def google_search(query):
    from urllib.request import Request, build_opener
    from backend.solar_roof import _NoRedirect
    values=config()
    key=values.get('GOOGLE_GEOCODING_API_KEY') or values.get('GOOGLE_MAPS_API_KEY') or values.get('GOOGLE_SOLAR_API_KEY')
    if not key:raise RuntimeError('Google API key missing')
    url='https://maps.googleapis.com/maps/api/geocode/json?'+urlencode({'address':query,'key':key})
    with build_opener(_NoRedirect()).open(Request(url),timeout=20) as response:
        data=response.read(2000001)
        if len(data)>2000000:raise RuntimeError('Geocoding response too large')
        data=json.loads(data)
    if data.get('status')=='ZERO_RESULTS':return []
    if data.get('status')!='OK':
        raise ValueError('GEOCODING_'+str(data.get('status','FAILED')))
    results=[]
    for result in data.get('results',[])[:12]:
        geometry=result.get('geometry',{});point=geometry.get('location',{})
        if geometry.get('location_type') not in ('ROOFTOP','RANGE_INTERPOLATED') or result.get('partial_match'):continue
        lat,lng=point.get('lat'),point.get('lng')
        if type(lat) not in (float,int) or type(lng) not in (float,int) or not math.isfinite(lat) or not math.isfinite(lng) or abs(lat)>90 or abs(lng)>180:continue
        results.append({'address':result['formatted_address'],'latitude':lat,'longitude':lng,
            'identity':'place:'+result['place_id'],'provider':'Google Maps',
            'geocodeFetchedAt':datetime.now(timezone.utc).isoformat()})
    return results


def acquire(target):
    # Keep the already-acquired legacy preview reusable for the same parcel.
    legacy=ROOT/'runtime/google-kimberly'
    matches_legacy=False
    if target.get('geometry') and (legacy/'manifest.json').exists():
        from shapely.geometry import shape, Point
        try:
            origin=json.loads((legacy/'manifest.json').read_text())['origin']
            matches_legacy=shape(target['geometry']).covers(Point(origin['longitude'],origin['latitude']))
        except (ValueError,KeyError,TypeError):pass
    if matches_legacy:
        cache,source=legacy,'kimberly'
    else:
        source=hashlib.sha256(target['identity'].encode()).hexdigest()[:32]
        cache=ROOT/'runtime/google-addresses'/source
    spec=importlib.util.spec_from_file_location('google_imagery',ROOT/'google-imagery.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    manifest=module.acquire(target,cache)
    return {'source':source,'address':manifest['address'],'expiresAt':manifest['expiresAt']}


def run(payload):
    if payload.get('action')=='search':
        query=payload.get('query','').strip()
        if not 5<=len(query)<=250:raise ValueError('INVALID_QUERY')
        local_error=False
        try:results=local_search(query)
        except Exception:results=[];local_error=True
        return {'results':results,'localUnavailable':local_error}
    if payload.get('action')=='acquire':return acquire(payload['target'])
    if payload.get('action') in ('handoff','return-geometry'):
        from model_handoff import convert_generated,return_geometry
        if payload['action']=='handoff':return convert_generated(payload['handoff'],payload['manifest'],payload['height'])
        return return_geometry(payload['packet'],payload['target'])
    if payload.get('action')=='height':
        source=payload['source']
        if source!='kimberly' and not re.fullmatch(r'[a-f0-9]{32}',source):raise ValueError('INVALID_SOURCE')
        cache=ROOT/'runtime/google-kimberly' if source=='kimberly' else ROOT/'runtime/google-addresses'/source
        spec=importlib.util.spec_from_file_location('height_data',ROOT/'height-data.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.acquire(cache)
    raise ValueError('INVALID_ACTION')


if __name__=='__main__':
    try:print(json.dumps({'ok':True,**run(json.loads(sys.stdin.read(25*1024*1024)))}))
    except Exception as exc:
        from urllib.error import HTTPError
        code='REQUEST_FAILED'
        if isinstance(exc,ValueError) and str(exc).startswith(('GEOCODING_','INVALID_','HEIGHT_','INSUFFICIENT_')):code=str(exc)
        reasons=[]
        if isinstance(exc,HTTPError):
            try:
                error=json.loads(exc.read(8192)).get('error',{})
                reasons=[item['reason'] for item in error.get('details',[]) if item.get('reason')]
            except Exception:pass
        print(json.dumps({'ok':False,'code':code,'errorType':type(exc).__name__,
                          'httpStatus':getattr(exc,'code',None),'reasons':reasons}))
        raise SystemExit(1)
