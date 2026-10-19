"""Bounded, georeferenced RGB crops for experimental roof fitting and display."""
import base64
import math

import numpy as np
from affine import Affine
from pyproj import Transformer, CRS
from rasterio.io import MemoryFile
from rasterio.warp import reproject, Resampling

MAX_SOURCE_PIXELS = 4_000_000
MAX_CROP_SIDE = 512
ALGORITHM_VERSION = 'photo-1'


def aligned_rgb(inputs, raw, home=None):
    """Return RGB/valid arrays and pixel-to-local-meter transform, or None.

    Alignment uses raster georeferencing, not inferred registration. A matching
    CRS does not prove that image objects align accurately with measured roofs.
    """
    content = inputs.get('rgb')
    if not content or not raw.get('bounds') or not raw.get('origin'):
        return None
    origin, bounds = raw['origin'], raw['bounds']
    target = CRS.from_user_input(origin['crs'])
    if not target.is_projected or any(axis.unit_name != 'metre' for axis in target.axis_info[:2]):
        raise ValueError('Roof photo requires a projected meter coordinate system')
    ox, oy = Transformer.from_crs('EPSG:4326', target, always_xy=True).transform(
        origin['longitude'], origin['latitude'])
    left, bottom = float(bounds['min_x']) - 2, float(bounds['min_y']) - 2
    right, top = float(bounds['max_x']) + 2, float(bounds['max_y']) + 2
    if not all(math.isfinite(v) for v in (left,bottom,right,top,ox,oy)) or right <= left or top <= bottom:
        raise ValueError('Invalid crop bounds')
    pixel = max(0.1, (right-left)/MAX_CROP_SIDE, (top-bottom)/MAX_CROP_SIDE)
    width, height = math.ceil((right-left)/pixel), math.ceil((top-bottom)/pixel)
    local = Affine(pixel, 0, left, 0, -pixel, top)
    world = Affine(pixel, 0, left+ox, 0, -pixel, top+oy)
    output = np.zeros((3,height,width), dtype=np.uint8)
    valid = np.zeros((height,width), dtype=np.uint8)
    with MemoryFile(content) as mem, mem.open() as src:
        if not src.crs or src.count < 3 or src.width*src.height > MAX_SOURCE_PIXELS:
            raise ValueError('Invalid or oversized RGB source')
        if any(dtype != 'uint8' for dtype in src.dtypes[:3]):
            raise ValueError('Expected byte RGB source')
        for band in range(3):
            reproject(src.read(band+1),output[band],src_transform=src.transform,src_crs=src.crs,
                      dst_transform=world,dst_crs=target,resampling=Resampling.bilinear)
        reproject(src.dataset_mask(),valid,src_transform=src.transform,src_crs=src.crs,
                  dst_transform=world,dst_crs=target,resampling=Resampling.nearest)
    if not np.any(valid):
        raise ValueError('RGB source does not cover roof')
    return {'rgb':np.moveaxis(output,0,-1),'valid':valid>0,'transform':local,
            'bounds':{'min_x':left,'min_y':top-height*pixel,'max_x':left+width*pixel,'max_y':top},
            'pixel_size_m':pixel}


def preview(inputs, raw, home=None):
    aligned = aligned_rgb(inputs,raw,home)
    if aligned is None:
        return None
    rgb, valid = aligned['rgb'], aligned['valid']
    rgba = np.concatenate((np.moveaxis(rgb,-1,0),valid[None].astype(np.uint8)*255),axis=0)
    with MemoryFile() as mem:
        with mem.open(driver='PNG',height=rgb.shape[0],width=rgb.shape[1],count=4,dtype='uint8') as dst:
            dst.write(rgba)
        encoded = base64.b64encode(mem.read()).decode('ascii')
    return {'data_url':'data:image/png;base64,'+encoded,'bounds':aligned['bounds'],
            'imagery_date':inputs.get('source_metadata',{}).get('raster_imagery_date'),
            'alignment_status':'georeferenced','pixel_size_m':aligned['pixel_size_m'],
            'registration_verified':False}
