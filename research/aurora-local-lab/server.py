"""Loopback-only experimental host. Vendor artifacts are read, never rewritten."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import hashlib
import json
from datetime import datetime, timezone, timedelta
import threading
import subprocess
import sys
import os
import time
import uuid
import re
from source_case_store import SourceCases

ROOT = Path(__file__).resolve().parent
PORT=int(os.environ.get('LAB_PORT','5191'))
HOSTS=(f'127.0.0.1:{PORT}',f'localhost:{PORT}')
ORIGINS=tuple('http://'+host for host in HOSTS)
BRIDGE_ORIGINS=('http://127.0.0.1:5173','http://localhost:5173')
BRIDGE_PATHS=('/model-handoff','/model-return')
VENDOR = ROOT / 'runtime' / 'vendor'
FRONTEND = ROOT / 'runtime' / 'frontend'
EXPECTED = {
    'cad-bundle.js': '065f6e39575ec8b5bc15ddac809aa7178285e0a90852ebe46a04c16249dcfedb',
    'datamodel-api-js.wasm': '315646e459591552df145f90177d0a4ecc2a06ecb2c7278b2a5694cf4ac47fa4',
}


GOOGLE_CACHE = ROOT / 'runtime' / 'google-kimberly'
CACHE_LOCK = threading.RLock()


def source_cache(source='kimberly'):
    if source=='kimberly':return GOOGLE_CACHE
    if not re.fullmatch(r'[a-f0-9]{32}',source):raise ValueError('Invalid source ID')
    return ROOT/'runtime/google-addresses'/source


def google_manifest(source='kimberly'):
    with CACHE_LOCK:
        cache=source_cache(source)
        path = cache / 'manifest.json'
        if not path.exists() or path.is_symlink():
            return None
        try:
            manifest = json.loads(path.read_text())
            expires = datetime.fromisoformat(manifest['expiresAt'])
            fetched = datetime.fromisoformat(manifest['fetchedAt'])
            now = datetime.now(timezone.utc)
            if fetched.tzinfo is None or expires.tzinfo is None or fetched > now + timedelta(minutes=1) or expires > fetched + timedelta(days=30) or expires <= now or expires <= fetched:
                raise ValueError('Expired source')
            if manifest['schema'] != 'roof-lab-google-preview/v1':
                raise ValueError('Unsupported source')
            return manifest
        except (ValueError, KeyError, TypeError):
            # Purge only files owned by this single-address preview cache.
            for name in ('manifest.json', 'image.png', 'preview.png','height.json','height.bin','height-mask.bin','height.bin.pending','height-mask.bin.pending','height.json.pending','height-source.json','height-dsm.tif','height-mask.tif','height-source.json.pending','height-dsm.tif.pending','height-mask.tif.pending'):
                (cache / name).unlink(missing_ok=True)
            return None


SOURCE_CASES=SourceCases(ROOT/'runtime/source-cases',google_manifest,EXPECTED)

def expiry_watch():
    while True:
        google_manifest()
        parent=ROOT/'runtime/google-addresses'
        if parent.exists():
            for folder in parent.iterdir():
                if folder.is_dir() and not folder.is_symlink() and re.fullmatch(r'[a-f0-9]{32}',folder.name):google_manifest(folder.name)
        with CACHE_LOCK:SOURCE_CASES.purge()
        with SELECTION_LOCK:
            for token,record in list(SELECTIONS.items()):
                if record[1]<time.monotonic():SELECTIONS.pop(token,None)
        threading.Event().wait(60)


SELECTIONS={}
SELECTION_LOCK=threading.RLock()
ACQUIRE_LOCK=threading.Lock()
WORKER_PYTHON=Path('/Users/chris/code/solar-designer/.venv/bin/python')


def worker(payload):
    try:
        result=subprocess.run([str(WORKER_PYTHON),'-B',str(ROOT/'address-imagery.py')],
            input=json.dumps(payload),text=True,capture_output=True,timeout=120,cwd=ROOT)
        return json.loads(result.stdout.strip())
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return {'ok':False,'code':'WORKER_UNAVAILABLE'}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        if urlsplit(self.path).path in BRIDGE_PATHS and self.headers.get('Origin') in BRIDGE_ORIGINS:
            self.send_header('Access-Control-Allow-Origin',self.headers['Origin'])
            self.send_header('Vary','Origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' blob: 'unsafe-eval' 'wasm-unsafe-eval'; connect-src 'self' blob:; img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'none'")
        super().end_headers()

    def reply_json(self,data,status=200):
        body=json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if self.headers.get('Host') not in HOSTS or urlsplit(self.path).path not in BRIDGE_PATHS or self.headers.get('Origin') not in BRIDGE_ORIGINS:return self.send_error(403)
        self.send_response(204);self.send_header('Access-Control-Allow-Methods','POST');self.send_header('Access-Control-Allow-Headers','Content-Type');self.end_headers()

    def do_POST(self):
        origin=self.headers.get('Origin');bridge=urlsplit(self.path).path in BRIDGE_PATHS and origin in BRIDGE_ORIGINS
        if self.headers.get('Host') not in HOSTS or (origin not in ORIGINS and not bridge):
            return self.reply_json({'error':'Same-origin request required'},403)
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.reply_json({'error':'JSON required'},415)
        try:
            length=int(self.headers.get('Content-Length','0'))
            limit=25*1024*1024 if urlsplit(self.path).path in ('/source-case-save','/source-case-import','/model-handoff','/model-return') else 4000
            if not 0<length<=limit:raise ValueError()
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict):raise ValueError()
        except (ValueError,TypeError):return self.reply_json({'error':'Invalid request'},400)
        path=urlsplit(self.path).path
        if path in BRIDGE_PATHS:
            try:
                if path=='/model-return':
                    with CACHE_LOCK:packet=SOURCE_CASES.validate(payload['packet'])
                    result=worker({'action':'return-geometry','packet':packet,'target':payload['target']})
                    if not result.get('ok'):raise ValueError()
                    return self.reply_json(result)
                requested=payload['handoff'];origin=requested['result']['origin'];source=None;manifest=None
                candidates=['kimberly'];parent=ROOT/'runtime/google-addresses'
                if parent.exists():candidates += [p.name for p in parent.iterdir() if p.is_dir() and re.fullmatch(r'[a-f0-9]{32}',p.name)]
                for candidate in candidates:
                    current=google_manifest(candidate)
                    if current and abs(current['origin']['latitude']-origin['latitude'])<.00002 and abs(current['origin']['longitude']-origin['longitude'])<.00002:
                        source=candidate;manifest=current;break
                if not manifest:return self.reply_json({'error':'Open this property in roof builder and load its imagery/heights first.'},409)
                try:height=json.loads((source_cache(source)/'height.json').read_text())
                except OSError:return self.reply_json({'error':'Load height data for this property before transferring the generated roof.'},409)
                result=worker({'action':'handoff','handoff':requested,'manifest':manifest,'height':height})
                if not result.get('ok'):raise ValueError()
                with CACHE_LOCK:packet=SOURCE_CASES.save({**result,'sourceId':source,'name':payload.get('name') or 'Generated roof','checkpoint':True})
                return self.reply_json({'caseId':packet['caseId'],'source':source,'expiresAt':packet['expiresAt'],'url':'/?google='+source+'&case='+packet['caseId']})
            except (ValueError,KeyError,TypeError):return self.reply_json({'error':'Model transfer rejected. Check source dates, coordinate frame, building match and available planes.'},400)
        if path in ('/source-case-save','/source-case-import','/source-case-recover'):
            try:
                with CACHE_LOCK:
                    if path=='/source-case-save':packet=SOURCE_CASES.save(payload)
                    elif path=='/source-case-import':packet=SOURCE_CASES.import_packet(payload['packet'])
                    else:
                        SOURCE_CASES.recover(payload['caseId']);packet={'ok':True}
                return self.reply_json(packet)
            except (ValueError,KeyError,TypeError):return self.reply_json({'error':'Source case invalid, expired, or matching imagery unavailable'},400)
        if path=='/address-search':
            query=payload.get('query')
            if not isinstance(query,str) or not 5<=len(query.strip())<=250:
                return self.reply_json({'error':'Enter a full street address'},400)
            result=worker({'action':'search','query':query})
            if not result.get('ok'):return self.reply_json(result,503)
            if result.get('localUnavailable'):return self.reply_json({'error':'Local property database unavailable. Check local database service.'},503)
            public=[]
            with SELECTION_LOCK:
                for target in result['results']:
                    token=uuid.uuid4().hex
                    SELECTIONS[token]=(target,time.monotonic()+900)
                    public.append({'token':token,'address':target['address'],'provider':target['provider']})
            return self.reply_json({'results':public})
        if path=='/height-acquire':
            source=payload.get('source')
            try:
                if not isinstance(source,str) or not google_manifest(source):raise ValueError()
            except ValueError:return self.reply_json({'error':'Unknown or expired image source'},400)
            if not ACQUIRE_LOCK.acquire(blocking=False):return self.reply_json({'error':'Another data request is running'},409)
            try:result=worker({'action':'height','source':source})
            finally:ACQUIRE_LOCK.release()
            return self.reply_json(result,200 if result.get('ok') else 503)
        if path=='/address-imagery':
            token=payload.get('token')
            if not isinstance(token,str) or not re.fullmatch(r'[a-f0-9]{32}',token):
                return self.reply_json({'error':'Invalid address selection'},400)
            with SELECTION_LOCK:record=SELECTIONS.get(token)
            if not record or record[1]<time.monotonic():
                return self.reply_json({'error':'Address selection expired. Search again.'},410)
            if not ACQUIRE_LOCK.acquire(blocking=False):
                return self.reply_json({'error':'Another image is loading. Try again after it finishes.'},409)
            try:result=worker({'action':'acquire','target':record[0]})
            finally:ACQUIRE_LOCK.release()
            if not result.get('ok'):return self.reply_json(result,503)
            return self.reply_json(result)
        return self.reply_json({'error':'Unknown route'},404)

    def do_GET(self):
        if self.headers.get('Host') not in HOSTS:
            return self.send_error(403, 'Loopback host required')
        path = urlsplit(self.path).path
        if path in ('/source-case','/source-cases'):
            query=parse_qs(urlsplit(self.path).query)
            try:
                with CACHE_LOCK:
                    result=SOURCE_CASES.list(query.get('source',[''])[0]) if path=='/source-cases' else SOURCE_CASES.read(query.get('id',[''])[0],query.get('checkpoint',['0'])[0]=='1')
                return self.reply_json(result)
            except (ValueError,KeyError,TypeError):return self.reply_json({'error':'Source case unavailable or expired'},404)
        if path in ('/height.json','/height.bin','/height-mask.bin'):
            source=parse_qs(urlsplit(self.path).query).get('source',['kimberly'])[0]
            try:
                cache=source_cache(source);manifest=google_manifest(source)
            except ValueError:return self.send_error(400,'Invalid source')
            if not manifest:return self.send_error(410,'Source expired or unavailable')
            try:
                metadata=json.loads((cache/'height.json').read_text())
                if metadata['expiresAt']!=manifest['expiresAt'] or metadata['imageSha256']!=manifest['pngSha256']:return self.send_error(409,'Height registration mismatch')
                target=cache/path.lstrip('/')
                if target.is_symlink():return self.send_error(404)
                data=target.read_bytes()
                key={'/height.bin':'sha256','/height-mask.bin':'maskSha256'}.get(path)
                if key and hashlib.sha256(data).hexdigest()!=metadata[key]:return self.send_error(409,'Height checksum mismatch')
            except (OSError,ValueError,KeyError):return self.send_error(404,'Height data not loaded')
            if not google_manifest(source):return self.send_error(410,'Source expired')
            self.send_response(200);self.send_header('Content-Type','application/json' if path.endswith('.json') else 'application/octet-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        if path in ('/google-imagery.json', '/google-imagery.png'):
            source=parse_qs(urlsplit(self.path).query).get('source',['kimberly'])[0]
            try:
                cache=source_cache(source)
                manifest=google_manifest(source)
            except ValueError:return self.send_error(400,'Invalid source ID')
            if not manifest:
                return self.send_error(404, 'No unexpired imagery acquired for this property')
            if path.endswith('.json'):
                data = json.dumps(manifest).encode()
            else:
                image = cache / 'image.png'
                if not image.is_file() or image.is_symlink():
                    return self.send_error(404, 'Imagery unavailable')
                data = image.read_bytes()
                if hashlib.sha256(data).hexdigest() != manifest['pngSha256']:
                    return self.send_error(409, 'Imagery checksum mismatch')
            if not google_manifest(source):
                return self.send_error(410, 'Imagery expired')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json' if path.endswith('.json') else 'image/png')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == '/frontend-capture.json':
            manifest = json.loads((FRONTEND / 'capture-manifest.json').read_text())
            data = json.dumps({'files': sorted(manifest)}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith('/frontend-assets/'):
            name = path.removeprefix('/frontend-assets/')
            manifest = json.loads((FRONTEND / 'capture-manifest.json').read_text())
            manifest.update(json.loads((FRONTEND / 'derived-manifest.json').read_text()))
            if name not in manifest:
                return self.send_error(404, 'Uncaptured frontend asset')
            data = (FRONTEND / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != manifest[name]['sha256']:
                return self.send_error(409, 'Frontend asset identity mismatch')
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == '/demo.json':
            demo = ROOT / 'runtime' / 'demo-design.json'
            if not demo.exists():
                return self.send_error(404, 'Run the verification to create the synthetic demo')
            data = demo.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith('/vendor/'):
            name = path.removeprefix('/vendor/')
            if name not in EXPECTED:
                return self.send_error(404, 'Uncaptured asset')
            data = (VENDOR / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != EXPECTED[name]:
                return self.send_error(409, 'Artifact identity mismatch')
            self.send_response(200)
            self.send_header('Content-Type', 'application/wasm' if name.endswith('.wasm') else 'text/javascript')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == '/health':
            data = json.dumps({'mode': 'isolated-local-lab', 'artifacts': EXPECTED}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(data)
            return
        if path not in ['/', '/index.html', '/app.js', '/style.css', '/frontend-ui.js', '/fold-placement.js', '/case-export.js', '/tab-drafts.js', '/imagery-session.js', '/address-lookup.js', '/height-tools.js', '/height-fit.mjs', '/source-cases.js']:
            return self.send_error(404)
        super().do_GET()


if __name__ == '__main__':
    google_manifest()
    threading.Thread(target=expiry_watch, daemon=True).start()
    print(f'Local CAD lab: http://127.0.0.1:{PORT}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
