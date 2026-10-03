"""``picpak``: command-line control of PicPak frames."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import tempfile
import webbrowser
from pathlib import Path

from . import __version__, config, dashboard, library
from . import image as img
from .device import FrameNotFound, PicPak, scan


def _target(args: argparse.Namespace) -> tuple[str, str]:
    """(frame name for the library, BLE address)."""
    if not args.frame:
        frames = config.load()
        if len(frames) != 1:
            sys.exit("say which frame: --frame NAME (see `picpak frames`)")
        args.frame = next(iter(frames))
    address = config.resolve(args.frame)
    return library.frame_key(args.frame), address


async def cmd_scan(args: argparse.Namespace) -> None:
    named = {v: k for k, v in config.load().items()}
    found = await scan(args.timeout)
    if not found:
        print("no PicPak found (is it awake, and is the phone app disconnected?)")
    for f in found:
        print(f"{f.address}  rssi={f.rssi}  {f.name}  {named.get(f.address, '')}")


async def cmd_info(args: argparse.Namespace) -> None:
    name, address = _target(args)
    async with PicPak(address) as frame:
        i = await frame.info()
        used = await frame.slots()
    frames = library.load()
    fs = frames.setdefault(name, library.FrameState(address=address))
    fs.battery, fs.firmware, fs.serial, fs.seen_at = i.battery, i.firmware, i.serial, library.now()
    library.save(frames)
    print(f"battery   {i.battery}%")
    print(f"firmware  {i.firmware}  (hardware {i.hardware})")
    print(f"serial    {i.serial or '-'}")
    print(f"images    {len(used)} of 500")


async def cmd_list(args: argparse.Namespace) -> None:
    name, address = _target(args)
    async with PicPak(address) as frame:
        used = await frame.slots()
        md5s = {} if args.fast else {s: await frame.read_md5(s) for s in used}
    fs = library.load().get(name) if args.fast else library.reconcile(name, address, used, md5s)
    print(f"{name}: {len(used)} image(s)")
    for s in sorted(set(used) | set(fs.slots if fs else {})):
        e = fs.slots.get(s) if fs else None
        st = (fs.status.get(s) if fs else None) or ("on frame" if s in used else "")
        src = Path(e.source).name if e else "?"
        when = e.pushed_at[:16].replace("T", " ") if e else ""
        print(f"  {s:>3}  {st:8}  {when:16}  {src}")


async def cmd_push(args: argparse.Namespace) -> None:
    name, address = _target(args)
    packed, preview = img.encode(args.image, args.fit, not args.no_dither)
    async with PicPak(address) as frame:
        slot = args.slot or await frame.first_free_slot()
        await frame.upload(slot, packed)
    library.record(name, address, library.Entry(
        slot=slot, source=str(Path(args.image).resolve()), md5=hashlib.md5(packed).hexdigest(),
        fit=args.fit, dither=not args.no_dither, pushed_at=library.now()), preview)
    print(f"pushed {args.image} to {name} slot {slot}")
    if args.save_preview:
        preview.save(args.save_preview)


async def cmd_delete(args: argparse.Namespace) -> None:
    name, address = _target(args)
    if not args.local_only:
        async with PicPak(address) as frame:
            if not await frame.delete(args.slot):
                sys.exit(f"{name} slot {args.slot}: delete failed on the frame (record kept)")
    library.forget(name, args.slot)
    print(f"{name} slot {args.slot}: deleted{' (record only)' if args.local_only else ''}")


async def cmd_pull(args: argparse.Namespace) -> None:
    name, address = _target(args)
    print(f"downloading {name} slot {args.slot} (30-60 s; keep the frame awake)...")
    async with PicPak(address) as frame:
        packed = await frame.read_image(args.slot)
    preview = img.to_image(img.unpack(packed))
    known = library.load().get(name, library.FrameState()).slots.get(args.slot)
    entry = known or library.Entry(slot=args.slot, source="(on frame, source unknown)",
                                   md5=hashlib.md5(packed).hexdigest(), origin="pull")
    library.record(name, address, entry, preview)
    if args.out:
        preview.save(args.out)
    print(f"slot {args.slot} saved: {args.out or library.preview_path(name, args.slot)}")


async def cmd_identify(args: argparse.Namespace) -> None:
    name, address = _target(args)
    label = args.frame or "PicPak"
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        img.label_image(label).save(tmp.name)
        packed, preview = img.encode(tmp.name, "contain")
    async with PicPak(address) as frame:
        slot = await frame.first_free_slot()
        await frame.upload(slot, packed)
    library.record(name, address, library.Entry(
        slot=slot, source=f"identify: {label}", md5=hashlib.md5(packed).hexdigest(), fit="contain",
        pushed_at=library.now(), origin="identify"), preview)
    print(f"'{label}' shown, stored in slot {slot}")


def cmd_preview(args: argparse.Namespace) -> None:
    _, preview = img.encode(args.image, args.fit, not args.no_dither)
    out = args.out or str(Path(args.image).with_suffix(".picpak.png"))
    preview.save(out)
    print(f"preview written to {out}")


def cmd_dashboard(args: argparse.Namespace) -> None:
    out = dashboard.render()
    print(f"dashboard: {out}")
    if not args.no_open:
        webbrowser.open(out.as_uri())


def cmd_export(args: argparse.Namespace) -> None:
    print(f"exported frame names, records and previews to {library.export(args.file)}")


def cmd_import(args: argparse.Namespace) -> None:
    n_frames, n_slots = library.import_(args.file, replace=args.replace)
    print(f"imported: {n_frames} frame(s), {n_slots} slot record(s) ({'replaced' if args.replace else 'merged'})")
    print("Bluetooth addresses differ per Mac: wake each frame, `picpak scan`, then `picpak name ADDRESS NAME`.")


def cmd_name(args: argparse.Namespace) -> None:
    frames = config.load()
    frames[args.name] = args.address
    print(f"{args.name} = {args.address}  ({config.save(frames)})")


def cmd_frames(_args: argparse.Namespace) -> None:
    frames = config.load()
    if not frames:
        print(f"no named frames yet: run `picpak scan`, then `picpak name ADDRESS NAME` ({config.path()})")
    for k, v in sorted(frames.items()):
        print(f"{k:12} {v}")
    print(f"config  {config.path()}\ndata    {library.data_dir()}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="picpak", description="Drive PicPak e-ink frames over Bluetooth LE.")
    ap.add_argument("--version", action="version", version=f"picpak {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def with_frame(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sp.add_argument("--frame", "-f", help="frame name from `picpak frames`, or a BLE address")
        return sp

    def with_render(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sp.add_argument("--fit", choices=["cover", "contain"], default="cover")
        sp.add_argument("--no-dither", action="store_true", help="nearest colour, no dithering (flat graphics)")
        return sp

    s = sub.add_parser("scan", help="find frames in range")
    s.add_argument("--timeout", type=float, default=8.0)
    s.set_defaults(func=cmd_scan)
    with_frame(sub.add_parser("info", help="battery, firmware, serial, image count")).set_defaults(func=cmd_info)

    s = with_frame(sub.add_parser("list", help="slots with source, date and status (ok/changed/unknown/gone)"))
    s.add_argument("--fast", action="store_true", help="skip the MD5 check per slot")
    s.set_defaults(func=cmd_list)

    s = with_render(with_frame(sub.add_parser("push", help="send an image to a frame")))
    s.add_argument("image")
    s.add_argument("--slot", type=int, help="slot 1..500 (default: first free slot)")
    s.add_argument("--save-preview", metavar="PNG", help="also save what the frame will show")
    s.set_defaults(func=cmd_push)

    s = with_frame(sub.add_parser("delete", help="delete a slot on the frame and its record"))
    s.add_argument("slot", type=int)
    s.add_argument("--local-only", action="store_true", help="forget the record, leave the frame alone")
    s.set_defaults(func=cmd_delete)

    s = with_frame(sub.add_parser("pull", help="download a stored image as a preview (slow)"))
    s.add_argument("slot", type=int)
    s.add_argument("--out", help="also save as this PNG")
    s.set_defaults(func=cmd_pull)

    with_frame(sub.add_parser("identify", help="show the frame's name on its screen")).set_defaults(
        func=cmd_identify
    )

    s = with_render(sub.add_parser("preview", help="render an image as the frame would show it (no Bluetooth)"))
    s.add_argument("image")
    s.add_argument("--out")
    s.set_defaults(func=cmd_preview)

    s = sub.add_parser("dashboard", help="HTML overview of all frames and slots (XDG data dir)")
    s.add_argument("--no-open", action="store_true", help="write it, don't open a browser")
    s.set_defaults(func=cmd_dashboard)

    s = sub.add_parser("export", help="frame names, records and previews to one zip")
    s.add_argument("file")
    s.set_defaults(func=cmd_export)
    s = sub.add_parser("import", help="load an export (merge; --replace to overwrite)")
    s.add_argument("file")
    s.add_argument("--replace", action="store_true")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("name", help="give a scanned frame a name")
    s.add_argument("address")
    s.add_argument("name")
    s.set_defaults(func=cmd_name)
    sub.add_parser("frames", help="named frames and where the state lives").set_defaults(func=cmd_frames)
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = args.func(args)
    if asyncio.iscoroutine(result):
        try:
            asyncio.run(result)
        except TimeoutError as e:
            sys.exit(f"timeout: {e or 'no response from the frame'}")
        except FrameNotFound as e:
            sys.exit(str(e))


if __name__ == "__main__":
    main()
