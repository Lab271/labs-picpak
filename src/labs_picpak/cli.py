"""``picpak``: command-line control of PicPak frames."""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

from . import __version__, config
from . import image as img
from .device import FrameNotFound, PicPak, scan


def _frame(args: argparse.Namespace) -> PicPak:
    if not args.frame:
        frames = config.load()
        if len(frames) != 1:
            sys.exit("say which frame: --frame NAME (see `picpak frames`)")
        args.frame = next(iter(frames))
    return PicPak(config.resolve(args.frame))


async def cmd_scan(args: argparse.Namespace) -> None:
    named = {v: k for k, v in config.load().items()}
    found = await scan(args.timeout)
    if not found:
        print("no PicPak found (is it awake, and is the phone app disconnected?)")
    for f in found:
        print(f"{f.address}  rssi={f.rssi}  {f.name}  {named.get(f.address, '')}")


async def cmd_info(args: argparse.Namespace) -> None:
    async with _frame(args) as frame:
        i = await frame.info()
        used = await frame.slots()
    print(f"battery   {i.battery}%")
    print(f"firmware  {i.firmware}  (hardware {i.hardware})")
    print(f"serial    {i.serial or '-'}")
    print(f"images    {len(used)} of 500")


async def cmd_list(args: argparse.Namespace) -> None:
    async with _frame(args) as frame:
        used = await frame.slots()
    print(" ".join(map(str, used)) if used else "no images")


async def cmd_push(args: argparse.Namespace) -> None:
    packed, preview = img.encode(args.image, args.fit, not args.no_dither)
    async with _frame(args) as frame:
        slot = args.slot or await frame.first_free_slot()
        await frame.upload(slot, packed)
    print(f"pushed {args.image} to slot {slot}")
    if args.save_preview:
        preview.save(args.save_preview)


async def cmd_delete(args: argparse.Namespace) -> None:
    async with _frame(args) as frame:
        ok = await frame.delete(args.slot)
    print(f"slot {args.slot}: {'deleted' if ok else 'delete failed'}")


async def cmd_identify(args: argparse.Namespace) -> None:
    label = args.frame or "PicPak"
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        img.label_image(label).save(tmp.name)
        packed, _ = img.encode(tmp.name, "contain")
    async with _frame(args) as frame:
        slot = await frame.first_free_slot()
        await frame.upload(slot, packed)
    print(f"'{label}' shown, stored in slot {slot}")


def cmd_preview(args: argparse.Namespace) -> None:
    _, preview = img.encode(args.image, args.fit, not args.no_dither)
    out = args.out or str(Path(args.image).with_suffix(".picpak.png"))
    preview.save(out)
    print(f"preview written to {out}")


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


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="picpak", description="Drive PicPak e-ink frames over Bluetooth LE.")
    ap.add_argument("--version", action="version", version=f"picpak {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def with_frame(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sp.add_argument("--frame", "-f", help="frame name from `picpak frames`, or a BLE address")
        return sp

    s = sub.add_parser("scan", help="find frames in range")
    s.add_argument("--timeout", type=float, default=8.0)
    s.set_defaults(func=cmd_scan)
    with_frame(sub.add_parser("info", help="battery, firmware, serial, image count")).set_defaults(func=cmd_info)
    with_frame(sub.add_parser("list", help="occupied image slots")).set_defaults(func=cmd_list)

    s = with_frame(sub.add_parser("push", help="send an image to a frame"))
    s.add_argument("image")
    s.add_argument("--slot", type=int, help="slot 1..500 (default: first free slot)")
    s.add_argument("--fit", choices=["cover", "contain"], default="cover")
    s.add_argument("--no-dither", action="store_true", help="nearest colour, no dithering (flat graphics)")
    s.add_argument("--save-preview", metavar="PNG", help="also save what the frame will show")
    s.set_defaults(func=cmd_push)

    s = with_frame(sub.add_parser("delete", help="delete one image slot"))
    s.add_argument("slot", type=int)
    s.set_defaults(func=cmd_delete)

    with_frame(sub.add_parser("identify", help="show the frame's name on its screen")).set_defaults(
        func=cmd_identify
    )

    s = sub.add_parser("preview", help="render an image as the frame would show it (no Bluetooth)")
    s.add_argument("image")
    s.add_argument("--fit", choices=["cover", "contain"], default="cover")
    s.add_argument("--no-dither", action="store_true", help="nearest colour, no dithering (flat graphics)")
    s.add_argument("--out")
    s.set_defaults(func=cmd_preview)

    s = sub.add_parser("name", help="give a scanned frame a name")
    s.add_argument("address")
    s.add_argument("name")
    s.set_defaults(func=cmd_name)
    sub.add_parser("frames", help="list named frames").set_defaults(func=cmd_frames)
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
