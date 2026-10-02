"""Image encoding for the PicPak panel: 400x300, four colours, 2 bits per pixel.

The panel scans bottom to top, so the image is flipped vertically before packing
(a vertical flip only; a 180-degree rotation would also mirror it).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 400, 300
PACKED_SIZE = W * H * 2 // 8  # 30,000 bytes
PALETTE = np.array([(0, 0, 0), (255, 255, 255), (255, 255, 0), (255, 0, 0)], dtype=np.float32)
PALETTE_NAMES = ("black", "white", "yellow", "red")


def fit(img: Image.Image, mode: str = "cover") -> Image.Image:
    """Scale to 400x300. ``cover`` crops to fill, ``contain`` letterboxes on white."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    if mode == "cover":
        return ImageOps.fit(img, (W, H), Image.Resampling.LANCZOS)
    if mode == "contain":
        canvas = Image.new("RGB", (W, H), "white")
        thumb = ImageOps.contain(img, (W, H), Image.Resampling.LANCZOS)
        canvas.paste(thumb, ((W - thumb.width) // 2, (H - thumb.height) // 2))
        return canvas
    raise ValueError(f"unknown fit mode {mode!r}")


def dither(img: Image.Image) -> np.ndarray:
    """Floyd-Steinberg to the 4-colour palette. Returns an (H, W) array of palette indices."""
    buf = np.asarray(img.convert("RGB"), dtype=np.float32).copy()
    h, w, _ = buf.shape
    out = np.zeros((h, w), dtype=np.uint8)
    for y in range(h):
        row = buf[y]
        for x in range(w):
            px = np.clip(row[x], 0, 255)
            idx = int(np.argmin(((PALETTE - px) ** 2).sum(axis=1)))
            out[y, x] = idx
            err = px - PALETTE[idx]
            if x + 1 < w:
                row[x + 1] += err * (7 / 16)
            if y + 1 < h:
                nxt = buf[y + 1]
                if x > 0:
                    nxt[x - 1] += err * (3 / 16)
                nxt[x] += err * (5 / 16)
                if x + 1 < w:
                    nxt[x + 1] += err * (1 / 16)
    return out


def pack(indices: np.ndarray) -> bytes:
    """Pack palette indices 4 pixels per byte, MSB first, after the vertical flip."""
    if indices.shape != (H, W):
        raise ValueError(f"expected {(H, W)}, got {indices.shape}")
    flat = np.flipud(indices).astype(np.uint8).reshape(-1, 4)
    packed = (flat[:, 0] << 6) | (flat[:, 1] << 4) | (flat[:, 2] << 2) | flat[:, 3]
    return packed.astype(np.uint8).tobytes()


def unpack(packed: bytes) -> np.ndarray:
    """Inverse of :func:`pack`: bytes -> (H, W) palette indices, right side up."""
    data = np.frombuffer(packed.ljust(PACKED_SIZE, b"\x00")[:PACKED_SIZE], dtype=np.uint8)
    idx = np.stack([(data >> 6) & 3, (data >> 4) & 3, (data >> 2) & 3, data & 3], axis=1).reshape(H, W)
    return np.flipud(idx)


def to_image(indices: np.ndarray) -> Image.Image:
    """Render palette indices as an RGB image (what the frame will show)."""
    return Image.fromarray(PALETTE.astype(np.uint8)[indices], "RGB")


def encode(path: str | Path, mode: str = "cover") -> tuple[bytes, Image.Image]:
    """File -> (30,000 packed bytes, preview image)."""
    idx = dither(fit(Image.open(path), mode))
    return pack(idx), to_image(idx)


def label_image(text: str) -> Image.Image:
    """A plain card with one word on it, used by ``picpak identify``."""
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=72)
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    draw.rectangle((0, 0, W, 24), fill=(255, 0, 0))
    draw.text(((W - tw) / 2 - box[0], (H - th) / 2 - box[1]), text, fill="black", font=font)
    return img
