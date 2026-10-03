"""What is on which frame: the local state database.

The frame stores only pixels and an MD5 per slot, so picpak keeps the details itself, in the
XDG data directory (``$XDG_DATA_HOME/picpak``, default ``~/.local/share/picpak``):

    library.json            frames -> slots -> {source, md5, fit, dither, pushed_at}
    previews/<frame>/<slot>.png   what the frame shows for that slot
    dashboard.html          generated overview (``picpak dashboard``)

Frame names and addresses live in the config directory (see :mod:`config`). ``export`` and
``import`` move both to another machine as one zip.
"""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image

from . import config

FORMAT = 1


def data_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "picpak"


def preview_path(frame: str, slot: int) -> Path:
    return data_dir() / "previews" / frame / f"{slot}.png"


@dataclass
class Entry:
    slot: int
    source: str
    md5: str
    fit: str = ""
    dither: bool = True
    pushed_at: str = ""
    origin: str = "push"  # push | identify | pull (downloaded from the frame, source unknown)


@dataclass
class FrameState:
    address: str = ""
    slots: dict[int, Entry] = field(default_factory=dict)
    battery: int | None = None
    firmware: str = ""
    serial: str = ""
    seen_at: str = ""
    on_frame: list[int] = field(default_factory=list)  # slots in use at the last `list`
    status: dict[int, str] = field(default_factory=dict)  # slot -> ok | changed | unknown


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load() -> dict[str, FrameState]:
    f = data_dir() / "library.json"
    if not f.exists():
        return {}
    raw = json.loads(f.read_text())
    out: dict[str, FrameState] = {}
    for name, fs in raw.get("frames", {}).items():
        slots = {int(k): Entry(**v) for k, v in fs.pop("slots", {}).items()}
        status = {int(k): v for k, v in fs.pop("status", {}).items()}
        out[name] = FrameState(slots=slots, status=status, **fs)
    return out


def save(frames: dict[str, FrameState]) -> Path:
    f = data_dir() / "library.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    doc = {"format": FORMAT, "frames": {}}
    for name, fs in sorted(frames.items()):
        d = asdict(fs)
        d["slots"] = {str(k): asdict(v) for k, v in sorted(fs.slots.items())}
        d["status"] = {str(k): v for k, v in sorted(fs.status.items())}
        doc["frames"][name] = d
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(f)
    return f


def frame_key(target: str) -> str:
    """The name for a frame: its configured name, else the address itself."""
    by_addr = {v: k for k, v in config.load().items()}
    return target if target in config.load() else by_addr.get(target, target)


def record(frame: str, address: str, entry: Entry, preview: Image.Image | None) -> None:
    frames = load()
    fs = frames.setdefault(frame, FrameState())
    fs.address = address
    fs.slots[entry.slot] = entry
    fs.status[entry.slot] = "ok"
    if entry.slot not in fs.on_frame:
        fs.on_frame = sorted([*fs.on_frame, entry.slot])
    if preview is not None:
        p = preview_path(frame, entry.slot)
        p.parent.mkdir(parents=True, exist_ok=True)
        preview.save(p)
    save(frames)


def forget(frame: str, slot: int) -> None:
    frames = load()
    fs = frames.get(frame)
    if fs:
        fs.slots.pop(slot, None)
        fs.status.pop(slot, None)
        fs.on_frame = [s for s in fs.on_frame if s != slot]
        save(frames)
    preview_path(frame, slot).unlink(missing_ok=True)


def reconcile(frame: str, address: str, used: list[int], md5s: dict[int, str]) -> FrameState:
    """Compare the frame's slots and MD5s with the records; store and return the result."""
    frames = load()
    fs = frames.setdefault(frame, FrameState())
    fs.address, fs.on_frame, fs.seen_at = address, used, now()
    fs.status = {}
    for s in used:
        e = fs.slots.get(s)
        if e is None:
            fs.status[s] = "unknown"  # not pushed by picpak and not pulled yet
        elif md5s.get(s) == e.md5:
            fs.status[s] = "ok"
        else:
            fs.status[s] = "changed"  # the frame holds a different image than recorded
    for s in list(fs.slots):  # records for slots the frame no longer has
        if s not in used:
            fs.status[s] = "gone"
    save(frames)
    return fs


def rename(old: str, new: str) -> None:
    """Rename a frame everywhere: config name, library records and preview folder.

    ``old`` may be a name or an address (records made before the frame was named are keyed by address).
    """
    cfg = config.load()
    if new in cfg:
        raise ValueError(f"{new!r} is already a frame name")
    address = cfg.pop(old, old)
    cfg[new] = address
    config.save(cfg)
    frames = load()
    for key in (old, address):
        if key in frames:
            fs = frames.pop(key)
            frames.setdefault(new, fs)
            src = data_dir() / "previews" / key
            if src.exists():
                dst = data_dir() / "previews" / new
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dst)
    save(frames)


# ---- migration -------------------------------------------------------------------


def export(path: str | Path) -> Path:
    """Zip config (frame names) and data (library, previews) into one file."""
    path = Path(path)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"format": FORMAT, "exported_at": now()}, indent=2))
        if config.path().exists():
            z.write(config.path(), "config/frames.toml")
        base = data_dir()
        for f in sorted(base.rglob("*")):
            if f.is_file() and f.name != "dashboard.html":
                z.write(f, f"data/{f.relative_to(base)}")
    return path


def import_(path: str | Path, replace: bool = False) -> tuple[int, int]:
    """Load an export. Merges by default (local wins on conflicts); ``replace`` overwrites.

    Returns (frames, slot records) now known. BLE addresses on macOS differ per Mac:
    after importing, rebind each frame with ``picpak scan`` and ``picpak name``.
    """
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "manifest.json" not in names:
            raise ValueError(f"{path} is not a picpak export")
        if json.loads(z.read("manifest.json")).get("format") != FORMAT:
            raise ValueError("unsupported export format")
        if replace and data_dir().exists():
            shutil.rmtree(data_dir())
        incoming_names: dict[str, str] = {}
        if "config/frames.toml" in names:
            import tomllib

            incoming_names = dict(tomllib.loads(z.read("config/frames.toml").decode()).get("frames", {}))
        incoming_lib: dict = {}
        if "data/library.json" in names:
            incoming_lib = json.loads(z.read("data/library.json")).get("frames", {})
        for n in names:
            if n.startswith("data/previews/"):
                target = data_dir() / n.removeprefix("data/")
                if replace or not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(n))

    cfg = {} if replace else config.load()
    for k, v in incoming_names.items():
        cfg.setdefault(k, v)
    config.save(cfg)

    local = {} if replace else load()
    for name, fs in incoming_lib.items():
        slots = {int(k): Entry(**v) for k, v in fs.pop("slots", {}).items()}
        status = {int(k): v for k, v in fs.pop("status", {}).items()}
        cur = local.setdefault(name, FrameState(**fs))
        for s, e in slots.items():
            cur.slots.setdefault(s, e)
        for s, st in status.items():
            cur.status.setdefault(s, st)
    save(local)
    return len(local), sum(len(f.slots) for f in local.values())
