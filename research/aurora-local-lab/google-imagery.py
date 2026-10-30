"""Acquire only the explicitly requested property's Google Solar imagery.

CLI acquisition is separate from the loopback server: viewing a page never bills.
Credentials stay server-side. Production modules and database are read-only.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
PRODUCTION = Path('/Users/chris/code/solar-designer')
CACHE = ROOT / 'runtime' / 'google-kimberly'


def main():
    sys.path.insert(0, str(PRODUCTION))
    from scripts.dev import environment
    import psycopg
    from backend import solar_roof
    import numpy as np
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    config = environment()
    if urlsplit(config['DATABASE_URL']).hostname not in ('localhost', '127.0.0.1', '::1'):
        raise RuntimeError('Local database required')
    # Never reacquire on a repeated CLI invocation while an unexpired result exists.
    manifest_path = CACHE / 'manifest.json'
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        image_path = CACHE/'image.png'
        if datetime.fromisoformat(existing['expiresAt']) > datetime.now(timezone.utc) and image_path.is_file() and hashlib.sha256(image_path.read_bytes()).hexdigest() == existing['pngSha256']:
            print(json.dumps({'status': 'reused', 'expiresAt': existing['expiresAt']}))
            return
        raise RuntimeError('Existing imagery expired; remove it through expiry cleanup before a new explicit acquisition')
    target_address = config.get('ROOF_LAB_ADDRESS', '').strip()
    target_parcel = config.get('ROOF_LAB_PARCEL_ID', '').strip()
    if not target_address or not target_parcel:
        raise RuntimeError('Configure ROOF_LAB_ADDRESS and ROOF_LAB_PARCEL_ID locally')
    with psycopg.connect(config['DATABASE_URL'], connect_timeout=5,
                         options='-c default_transaction_read_only=on -c statement_timeout=10000') as c:
        row = c.execute('''SELECT ST_AsGeoJSON(county_geometry)::json FROM parcels
          WHERE address=%s AND parcel_id=%s AND county_geometry IS NOT NULL LIMIT 1''',
          (target_address.upper(), target_parcel)).fetchone()
    if not row:
        raise RuntimeError('Requested parcel unavailable')
    key = config.get('GOOGLE_SOLAR_API_KEY', '').strip()
    if not key:
        raise RuntimeError('Google Solar key missing')
    home = {'geometry': row[0]}
    parcel, point = solar_roof._point(home)
    from urllib.parse import urlencode
    fetched = datetime.now(timezone.utc)
    insights = solar_roof._json_request(solar_roof.INSIGHTS_ENDPOINT + '?' + urlencode({
        'location.latitude': format(point.y, '.8f'), 'location.longitude': format(point.x, '.8f'),
        'requiredQuality': 'HIGH'}), key)
    center = solar_roof._inside_parcel(insights, parcel)
    if center is None:
        raise RuntimeError('Google building lies outside requested parcel')
    layers = solar_roof._json_request(solar_roof.LAYERS_ENDPOINT + '?' + urlencode({
        'location.latitude': format(center.y, '.8f'), 'location.longitude': format(center.x, '.8f'),
        'radiusMeters': '40', 'view': 'IMAGERY_LAYERS', 'requiredQuality': 'HIGH',
        'pixelSizeMeters': '0.1'}), key)
    warnings, metadata = solar_roof._validate_source_match(insights, layers)
    # RGB only for manual tracing. No DSM/mask downloads or reconstruction call.
    rgb = solar_roof._raster_request(layers.get('rgbUrl'), key)
    local_crs = f'+proj=aeqd +lat_0={center.y:.12f} +lon_0={center.x:.12f} +datum=WGS84 +units=m +no_defs'
    with MemoryFile(rgb) as source_file, source_file.open() as source:
        if source.count < 3 or not source.crs or source.width * source.height > 4_000_000:
            raise RuntimeError('Unsupported RGB raster')
        transform, width, height = calculate_default_transform(source.crs, local_crs, source.width,
            source.height, *source.bounds, resolution=.1)
        if width * height > 4_000_000:
            raise RuntimeError('Reprojected image too large')
        output = np.zeros((3, height, width), dtype=np.uint8)
        for band in range(3):
            reproject(source=rasterio.band(source, band+1), destination=output[band],
                src_transform=source.transform, src_crs=source.crs, dst_transform=transform,
                dst_crs=local_crs, resampling=Resampling.bilinear)
        with MemoryFile() as png:
            with png.open(driver='PNG', width=width, height=height, count=3, dtype='uint8') as dst:
                dst.write(output)
            png_bytes = png.read()
        original_grid = {'crs': source.crs.to_string(), 'transform': list(source.transform)[:6],
                         'width': source.width, 'height': source.height}
    expiry = fetched + timedelta(days=30)
    if datetime.now(timezone.utc) >= expiry:
        raise RuntimeError('Source expired during preparation')
    manifest = {'schema': 'roof-lab-google-preview/v1', 'address': target_address,
        'fetchedAt': fetched.isoformat(), 'expiresAt': expiry.isoformat(),
        'attribution': 'Source: Includes solar data from Google', 'provider': 'Google Solar API',
        'captureDate': metadata.get('raster_imagery_date'), 'warnings': warnings,
        'origin': {'latitude': center.y, 'longitude': center.x}, 'localCRS': local_crs,
        'originalGrid': original_grid, 'width': width, 'height': height,
        'pixelToEditor': [transform.a, transform.b, transform.c+(transform.a+transform.b)/2,
                          transform.d, transform.e, transform.f+(transform.d+transform.e)/2],
        'pngSha256': hashlib.sha256(png_bytes).hexdigest(),
        'sourceSha256': hashlib.sha256(rgb).hexdigest(), 'byteLength': len(png_bytes),
        'requests': {'buildingInsights': 1, 'dataLayers': 1, 'rgbDownload': 1},
        'usage': 'Transient manual solar-design preview; permanent library/export disabled'}
    CACHE.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, data in [('manifest.json', json.dumps(manifest).encode()), ('image.png', png_bytes)]:
        path = CACHE/name
        path.write_bytes(data)
        path.chmod(0o600)
    print(json.dumps({'status': 'acquired', 'width': width, 'height': height,
                      'captureDate': manifest['captureDate'], 'expiresAt': manifest['expiresAt'],
                      'requests': manifest['requests'], 'warnings': warnings}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never print signed URLs, credential-bearing response bodies or tracebacks.
        from urllib.error import HTTPError
        reasons=[]
        if isinstance(exc, HTTPError):
            try:
                error=json.loads(exc.read(8192)).get('error',{})
                reasons=[item.get('reason') for item in error.get('details',[]) if item.get('reason')]
                reasons += [item.get('reason') for item in error.get('errors',[]) if item.get('reason')]
            except Exception:
                pass
        print(json.dumps({'status': 'failed', 'errorType': type(exc).__name__,
                          'httpStatus': exc.code if isinstance(exc, HTTPError) else None,
                          'reasons': reasons}))
        raise SystemExit(1)
