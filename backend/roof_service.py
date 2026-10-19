"""Short-lived, user-scoped roof reconstruction. Reads never fetch paid data."""
from datetime import datetime, timezone, timedelta
from psycopg.types.json import Jsonb
from fastapi import HTTPException


def pipeline_version():
    from backend import roof_geometry, roof_refinement, roof_ranking, roof_fitting, roof_photo
    return '/'.join((roof_geometry.ALGORITHM_VERSION,
                     getattr(roof_refinement,'ALGORITHM_VERSION','refine-1'),
                     getattr(roof_ranking,'ALGORITHM_VERSION','rank-1'),
                     roof_fitting.ALGORITHM_VERSION, roof_photo.ALGORITHM_VERSION))


def _payload(row):
    return {'status':row[3].get('status','needs_review'), 'result':row[3],
            'fetched_at':row[0].astimezone(timezone.utc).isoformat(), 'expires_at':row[1].astimezone(timezone.utc).isoformat(),
            'algorithm_version':row[2]}


def status(c, user, home):
    row = c.execute('''SELECT source_fetched_at,expires_at,algorithm_version,result
      FROM roof_reconstructions WHERE created_by=%s AND dataset_id=%s AND parcel_id=%s
      AND expires_at > now()''',(user,home['dataset_id'],home['id'])).fetchone()
    if row:
        if row[2] != pipeline_version():
            return {'status':'not_run','message':'Roof algorithm updated. Recalculate from saved roof data while it remains fresh.'}
        return _payload(row)
    return {'status':'not_run'}


def reconstruct(c, user, home):
    from backend import roof_geometry, solar_roof, roof_refinement, roof_ranking, roof_fitting, roof_photo
    from backend.solar import SolarUnavailable
    lock_key = ':'.join(['roof',user,str(home['dataset_id']),home['id']])
    if not c.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))',
                     (lock_key,)).fetchone()[0]:
        raise HTTPException(409,'Roof reconstruction is already running for this house. Reopen its record after it finishes.')
    row = c.execute('''SELECT source_fetched_at,expires_at,algorithm_version,result,insights,dsm,roof_mask,source_warnings,rgb,source_metadata
      FROM roof_reconstructions WHERE created_by=%s AND dataset_id=%s AND parcel_id=%s
      AND expires_at > now()''',(user,home['dataset_id'],home['id'])).fetchone()
    version = pipeline_version()
    if row and row[2] == version:
        return {**_payload(row),'reused':True}
    if row:
        inputs = {'fetched_at':row[0].isoformat(),'expires_at':row[1].isoformat(),
                  'insights':row[4],'dsm':bytes(row[5]),'mask':bytes(row[6]),'source_warnings':row[7],
                  'rgb':bytes(row[8]) if row[8] is not None else None,'source_metadata':row[9]}
    else:
        try:
            inputs = solar_roof.fetch_roof_inputs(home)
        except SolarUnavailable as exc:
            raise HTTPException(503,str(exc)) from None
    # Keep timestamps tied to original acquisition, including algorithm reruns.
    fetched = datetime.fromisoformat(inputs['fetched_at'].replace('Z','+00:00'))
    expires = datetime.fromisoformat(inputs['expires_at'].replace('Z','+00:00'))
    now = datetime.now(timezone.utc)
    if fetched.tzinfo is None or expires.tzinfo is None or fetched > now + timedelta(minutes=1):
        raise HTTPException(502,'Roof source timestamps are invalid.')
    expires = min(expires,fetched + timedelta(days=30))
    if expires <= now:
        raise HTTPException(502,'Roof source data expired before reconstruction completed.')
    result = roof_geometry.reconstruct(inputs, home)
    result['warnings'] = list(dict.fromkeys([*result.get('warnings',[]),*inputs.get('source_warnings',[])]))
    result['pipeline_version'] = version
    if result.get('status') == 'needs_review' and result.get('faces') and result.get('roof_outline'):
        try:
            refined = roof_refinement.refine(result,inputs,home)
            refined['design_ready'] = False
            try:
                refined['candidates'] = roof_ranking.rank_candidates(refined,result,inputs)
            except Exception:
                refined['candidates'] = []
                refined.setdefault('warnings',[]).append('Candidate ranking is unavailable; refined geometry was retained.')
            result['refinement'] = refined
        except Exception:
            # Retain acquired source data and raw geometry even if refinement
            # fails. Never refetch paid inputs merely to retry an algorithm.
            result['refinement'] = {'status':'unavailable','face_groups':[],
                'edges':[],'inferred_regions':[],'candidates':[], 'design_ready':False,
                'warnings':['Roof refinement could not produce a safe model. Raw reconstruction was retained.']}
    if result.get('status') == 'needs_review' and result.get('faces') and result.get('roof_outline'):
        try:
            result['photo'] = roof_photo.preview(inputs,result,home)
        except Exception:
            result['photo'] = None
            result.setdefault('warnings',[]).append('Roof photo could not be aligned; no image overlay is shown.')
        try:
            result['fitting'] = roof_fitting.fit(result,inputs,home)
            result['fitting']['design_ready'] = False
        except Exception:
            result['fitting'] = {'status':'unavailable','algorithm_version':roof_fitting.ALGORITHM_VERSION,
                'face_groups':[],'edges':[],'quality':{},'design_ready':False,
                'warnings':['Automatic roof fitting was withheld; raw reconstruction was retained.']}
    # Geometry alone is never a design/compliance approval.
    result.update(design_ready=False,ahj={'status':'pending_rules'})
    c.execute('''INSERT INTO roof_reconstructions
      (created_by,dataset_id,parcel_id,source_fetched_at,expires_at,algorithm_version,insights,dsm,roof_mask,result,source_warnings,rgb,source_metadata)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT(created_by,dataset_id,parcel_id) DO UPDATE SET
        source_fetched_at=EXCLUDED.source_fetched_at,expires_at=EXCLUDED.expires_at,
        algorithm_version=EXCLUDED.algorithm_version,insights=EXCLUDED.insights,
        dsm=EXCLUDED.dsm,roof_mask=EXCLUDED.roof_mask,result=EXCLUDED.result,source_warnings=EXCLUDED.source_warnings,
        rgb=EXCLUDED.rgb,source_metadata=EXCLUDED.source_metadata,updated_at=now()''',
      (user,home['dataset_id'],home['id'],fetched,expires,version,Jsonb(inputs['insights']),
       inputs['dsm'],inputs['mask'],Jsonb(result),Jsonb(inputs.get('source_warnings',[])),
       inputs.get('rgb'),Jsonb(inputs.get('source_metadata',{}))))
    return {'status':result.get('status','needs_review'),'result':result,
            'fetched_at':fetched.astimezone(timezone.utc).isoformat(),'expires_at':expires.astimezone(timezone.utc).isoformat(),
            'algorithm_version':version,'reused':bool(row)}
