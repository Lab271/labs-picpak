"""Local names for frames: ``~/.config/picpak/frames.toml``.

Both frames advertise as "PicPak" and the serial can be empty, so a frame is
remembered by its BLE address. On macOS that address is a UUID that is stable
on one Mac but differs between Macs, which is why this file is local and not
committed.

    [frames]
    kitchen = "8E1F2C3A-...."
    desk = "41B7D0E2-...."
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path


def path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "picpak" / "frames.toml"


def load() -> dict[str, str]:
    f = path()
    if not f.exists():
        return {}
    return dict(tomllib.loads(f.read_text()).get("frames", {}))


def save(frames: dict[str, str]) -> Path:
    f = path()
    f.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[frames]"] + [f'{k} = "{v}"' for k, v in sorted(frames.items())]
    f.write_text("\n".join(lines) + "\n")
    return f


def resolve(target: str) -> str:
    """A configured name, or an address used as is."""
    return load().get(target, target)
