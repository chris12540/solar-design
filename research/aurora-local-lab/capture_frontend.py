"""Capture named public JavaScript chunks; never fetch account or design APIs."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import gzip
import hashlib
import io
import json
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent / 'runtime' / 'frontend'
ORIGIN = 'https://v2.aurorasolar.com/'
MAX_FILE = 25 * 1024 * 1024
MAX_CAPTURE = 100 * 1024 * 1024
BOOT_HASH = '42976d01ffe5ecd1b87b9e083b645944c88d42d4010c69ea8fdb4a56e3b9194f'


class StaticOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith(ORIGIN):
            raise ValueError('Unexpected static-asset redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def capture(chunk):
    name = f'{chunk}.{index[chunk]}.prod.js'
    target = ROOT / name
    if target.exists():
        data = target.read_bytes()
        previous = manifest.get(name)
        if not previous or previous['sha256'] != hashlib.sha256(data).hexdigest():
            raise ValueError(f'Unverified existing asset: {name}')
        return name, previous
    request = urllib.request.Request(ORIGIN + name, headers={'Accept-Encoding': 'identity'})
    with urllib.request.build_opener(StaticOnlyRedirect()).open(request, timeout=30) as response:
        content_type = response.headers.get('Content-Type', '')
        if 'javascript' not in content_type:
            raise ValueError(f'Expected JavaScript, received {content_type}: {name}')
        raw = response.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            raise ValueError(f'Asset exceeds capture limit: {name}')
        data = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(MAX_FILE + 1) if raw[:2] == b'\x1f\x8b' else raw
        if len(data) > MAX_FILE:
            raise ValueError(f'Decoded asset exceeds capture limit: {name}')
    target.write_bytes(data)
    target.chmod(0o600)
    return name, {'url': ORIGIN + name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'chunk': chunk}


if __name__ == '__main__':
    if hashlib.sha256((ROOT / 'frontend.0.14683.9.js').read_bytes()).hexdigest() != BOOT_HASH:
        raise SystemExit('Frontend bootstrap identity mismatch')
    index = json.loads((ROOT / 'chunk-index.json').read_text())
    manifest_path = ROOT / 'capture-manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    requested = sys.argv[1:]
    if requested == ['--cad-ui']:
        requested = [name for name in index if ('cad-core' in name or 'cad-pro-routes' in name or 'src_index_tsx' in name) and 'homeowner' not in name]
        requested += ['translations-en-US', 'graphql-schema']
    for name in requested:
        if name not in index or not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
            raise SystemExit(f'Unknown chunk: {name}')
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(capture, chunk) for chunk in requested]
            failures = []
            for future in as_completed(futures):
                try:
                    name, item = future.result()
                except Exception as error:
                    failures.append(error)
                    continue
                manifest[name] = item
                if sum(entry['bytes'] for entry in manifest.values()) > MAX_CAPTURE:
                    raise ValueError('Capture exceeds total size limit')
                manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
                manifest_path.chmod(0o600)
                print(f"Captured {item['chunk']}: {item['bytes']} bytes", flush=True)
            if failures:
                raise failures[0]
    finally:
        # Keep completed identities even when a later requested chunk fails.
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        manifest_path.chmod(0o600)
