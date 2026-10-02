import numpy as np
from PIL import Image

from labs_picpak import image as img


def test_pack_size_and_roundtrip():
    rng = np.random.default_rng(271)
    idx = rng.integers(0, 4, size=(img.H, img.W), dtype=np.uint8)
    packed = img.pack(idx)
    assert len(packed) == img.PACKED_SIZE == 30_000
    assert np.array_equal(img.unpack(packed), idx)


def test_pack_is_msb_first_and_flipped_vertically():
    idx = np.zeros((img.H, img.W), dtype=np.uint8)
    idx[-1, :4] = [3, 2, 1, 0]  # bottom-left pixels of the picture
    packed = img.pack(idx)
    assert packed[0] == (3 << 6) | (2 << 4) | (1 << 2) | 0  # bottom row is sent first


def test_dither_uses_only_the_palette_and_keeps_solid_colours():
    red = Image.new("RGB", (img.W, img.H), (255, 0, 0))
    idx = img.dither(red)
    assert idx.shape == (img.H, img.W)
    assert set(np.unique(idx)) == {3}


def test_fit_modes():
    tall = Image.new("RGB", (100, 400), (0, 0, 0))
    assert img.fit(tall, "cover").size == (img.W, img.H)
    contained = img.fit(tall, "contain")
    assert contained.size == (img.W, img.H)
    assert contained.getpixel((0, 0)) == (255, 255, 255)  # letterbox is white


def test_encode_file(tmp_path):
    src = tmp_path / "src.png"
    Image.new("RGB", (800, 600), (255, 255, 0)).save(src)
    packed, preview = img.encode(src)
    assert len(packed) == 30_000
    assert preview.size == (img.W, img.H)
    assert preview.getpixel((10, 10)) == (255, 255, 0)


def test_nearest_maps_dark_navy_to_black_and_orange_to_yellow():
    im = Image.new("RGB", (img.W, img.H), (2, 12, 23))
    im.paste((255, 141, 51), (0, 0, 10, 10))
    idx = img.nearest(im)
    assert idx[50, 50] == 0 and idx[5, 5] == 2
