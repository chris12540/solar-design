"""Loopback-only experimental host. Vendor artifacts are read, never rewritten."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
from datetime import datetime, timezone, timedelta
import threading

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / 'runtime' / 'vendor'
FRONTEND = ROOT / 'runtime' / 'frontend'
EXPECTED = {
    'cad-bundle.js': '065f6e39575ec8b5bc15ddac809aa7178285e0a90852ebe46a04c16249dcfedb',
    'datamodel-api-js.wasm': '315646e459591552df145f90177d0a4ecc2a06ecb2c7278b2a5694cf4ac47fa4',
}


GOOGLE_CACHE = ROOT / 'runtime' / 'google-kimberly'
CACHE_LOCK = threading.RLock()


def google_manifest():
    with CACHE_LOCK:
        path = GOOGLE_CACHE / 'manifest.json'
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
            for name in ('manifest.json', 'image.png', 'preview.png'):
                (GOOGLE_CACHE / name).unlink(missing_ok=True)
            return None


def expiry_watch():
    while True:
        google_manifest()
        threading.Event().wait(60)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' blob: 'unsafe-eval' 'wasm-unsafe-eval'; connect-src 'self' blob:; img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'none'")
        super().end_headers()

    def do_GET(self):
        if self.headers.get('Host') not in ['127.0.0.1:5191', 'localhost:5191']:
            return self.send_error(403, 'Loopback host required')
        path = urlsplit(self.path).path
        manifest = google_manifest()
        if path in ('/google-imagery.json', '/google-imagery.png'):
            if not manifest:
                return self.send_error(404, 'No unexpired imagery acquired for this property')
            if path.endswith('.json'):
                data = json.dumps(manifest).encode()
            else:
                image = GOOGLE_CACHE / 'image.png'
                if not image.is_file() or image.is_symlink():
                    return self.send_error(404, 'Imagery unavailable')
                data = image.read_bytes()
                if hashlib.sha256(data).hexdigest() != manifest['pngSha256']:
                    return self.send_error(409, 'Imagery checksum mismatch')
            if not google_manifest():
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
        if path not in ['/', '/index.html', '/app.js', '/style.css', '/frontend-ui.js', '/fold-placement.js', '/case-export.js', '/tab-drafts.js', '/imagery-session.js']:
            return self.send_error(404)
        super().do_GET()


if __name__ == '__main__':
    google_manifest()
    threading.Thread(target=expiry_watch, daemon=True).start()
    print('Local CAD lab: http://127.0.0.1:5191', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 5191), Handler).serve_forever()
