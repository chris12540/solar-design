"""Retain supplied artifacts privately after checking their exact identity."""
from pathlib import Path
from server import EXPECTED, VENDOR
import hashlib
import sys

source = Path(sys.argv[1] if len(sys.argv) > 1 else '/private/tmp/aurora-cad-1.1876.0')
artifacts = {name: (source / name).read_bytes() for name in EXPECTED}
for name, data in artifacts.items():
    if hashlib.sha256(data).hexdigest() != EXPECTED[name]:
        raise SystemExit(f'Unexpected artifact identity: {name}')
VENDOR.mkdir(parents=True, exist_ok=True, mode=0o700)
for name, data in artifacts.items():
    target = VENDOR / name
    if target.exists() and target.read_bytes() != data:
        raise SystemExit(f'Refusing to overwrite different bytes: {target}')
    target.write_bytes(data)
    target.chmod(0o600)
print('Verified captured artifacts retained in ignored runtime/vendor. No downloads.')
