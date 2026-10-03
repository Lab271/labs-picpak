"""Print every indication a PicPak sends while you send it a few commands.

Use when a command times out on new firmware: it shows the reply opcodes the frame really uses.
This is how the V1.1.20 list (0x31) and delete (0x33) replies were found.

    uv run python scripts/sniff.py --frame frame-1 list "delete 1" list
    uv run python scripts/sniff.py --frame frame-1 info screen "show 2"

Commands: info, name, list, screen, "delete N", "show N", "md5 N". Deleting is real: it removes the image.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from bleak import BleakClient, BleakScanner

from labs_picpak import config
from labs_picpak import protocol as p

COMMANDS = {
    "info": lambda: (p.FF02_CTRL, p.cmd_info()),
    "name": lambda: (p.FF02_CTRL, p.cmd_name()),
    "list": lambda: (p.FF01_DATA, p.cmd_list()),
    "screen": lambda: (p.FF01_DATA, p.cmd_screen()),
}
WITH_SLOT = {"delete": p.cmd_delete, "show": p.cmd_show, "md5": p.cmd_read_md5}


def frame_for(cmd: str) -> tuple[str, bytes]:
    word, *rest = cmd.split()
    if word in COMMANDS:
        return COMMANDS[word]()
    if word in WITH_SLOT and rest:
        return p.FF01_DATA, WITH_SLOT[word](int(rest[0]))
    raise SystemExit(f"unknown command {cmd!r}; use one of {sorted(COMMANDS) + [k + ' N' for k in WITH_SLOT]}")


async def main(frame: str, cmds: list[str], wait: float) -> None:
    address = config.resolve(frame)
    t0 = time.monotonic()

    def log(char: str):
        def cb(_sender: object, data: bytearray) -> None:
            b = bytes(data)
            more = " …" if len(b) > 24 else ""
            print(f"{time.monotonic() - t0:6.2f}s RX {char} len={len(b):4} {b[:24].hex(' ')}{more}")

        return cb

    dev = await BleakScanner.find_device_by_address(address, timeout=12)
    if dev is None:
        raise SystemExit(f"{frame} is not advertising: wake it (and close the phone app)")
    async with BleakClient(dev) as client:
        await client.start_notify(p.FF01_DATA, log("FF01"))
        await client.start_notify(p.FF02_CTRL, log("FF02"))
        await asyncio.sleep(0.5)
        for cmd in cmds:
            char, frame_bytes = frame_for(cmd)
            name = "FF01" if char == p.FF01_DATA else "FF02"
            print(f"{time.monotonic() - t0:6.2f}s TX {name} {cmd}: {frame_bytes.hex(' ')}")
            await client.write_gatt_char(char, frame_bytes, response=True)
            await asyncio.sleep(wait)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frame", "-f", required=True, help="frame name or BLE address")
    ap.add_argument("--wait", type=float, default=4.0, help="seconds to listen after each command")
    ap.add_argument("commands", nargs="+")
    a = ap.parse_args()
    asyncio.run(main(a.frame, a.commands, a.wait))
