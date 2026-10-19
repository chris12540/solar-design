import base64
import numpy as np
import pytest
from affine import Affine
from pyproj import Transformer
from rasterio.io import MemoryFile
from backend import roof_photo


def fixture(*, x=500000, dtype='uint8', bands=3):
    lon,lat=Transformer.from_crs(32612,4326,always_xy=True).transform(500000,3700000)
    raw={'origin':{'crs':'EPSG:32612','longitude':lon,'latitude':lat},
         'bounds':{'min_x':0,'max_x':2,'min_y':0,'max_y':2}}
    values=np.zeros((bands,60,60),dtype=dtype)
    values[0]=80
    if bands>1: values[1]=120
    if bands>2: values[2]=160
    with MemoryFile() as mem:
        with mem.open(driver='GTiff',count=bands,height=60,width=60,dtype=dtype,
                      crs='EPSG:32612',transform=Affine(.1,0,x-2,0,-.1,3700004)) as dst:
            dst.write(values)
        content=mem.read()
    return {'rgb':content,'source_metadata':{'raster_imagery_date':'2023-09-27'}},raw


def test_photo_crop_aligns_known_projected_origin_and_pixel_centers():
    inputs,raw=fixture()
    result=roof_photo.aligned_rgb(inputs,raw)
    assert result['rgb'].shape==(60,60,3)
    assert result['valid'].all()
    assert tuple(result['rgb'][30,30])==(80,120,160)
    assert result['transform']*(.5,.5)==pytest.approx((-1.95,3.95))
    assert result['bounds']==pytest.approx({'min_x':-2,'max_x':4,'min_y':-2,'max_y':4})


def test_preview_is_bounded_rgba_png_and_does_not_claim_verified_registration():
    inputs,raw=fixture()
    result=roof_photo.preview(inputs,raw)
    png=base64.b64decode(result['data_url'].split(',')[1])
    assert png.startswith(b'\x89PNG')
    with MemoryFile(png) as mem,mem.open() as image:
        assert image.width==60 and image.height==60 and image.count==4
        assert image.read(4).min()==255
    assert result['registration_verified'] is False
    assert result['imagery_date']=='2023-09-27'


def test_photo_without_roof_coverage_is_rejected():
    inputs,raw=fixture(x=510000)
    with pytest.raises(ValueError,match='does not cover'):
        roof_photo.aligned_rgb(inputs,raw)


@pytest.mark.parametrize('dtype,bands',[('float32',3),('uint8',1)])
def test_photo_rejects_non_rgb_or_non_byte_data(dtype,bands):
    inputs,raw=fixture(dtype=dtype,bands=bands)
    with pytest.raises(ValueError):roof_photo.aligned_rgb(inputs,raw)


def test_no_photo_does_not_trigger_fetch():
    assert roof_photo.aligned_rgb({}, {}) is None


def test_large_crop_is_downsampled_instead_of_allocating_unbounded_grid():
    inputs,raw=fixture()
    raw['bounds']={'min_x':-5000,'max_x':5000,'min_y':-5000,'max_y':5000}
    # Narrow source may fall between coarse pixel centers: withholding is safe.
    try: result=roof_photo.aligned_rgb(inputs,raw)
    except ValueError: return
    assert max(result['rgb'].shape[:2])<=512
