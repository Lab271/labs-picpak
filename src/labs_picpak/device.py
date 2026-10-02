"""Async BLE client for one PicPak, built on bleak.

The frame accepts one connected client at a time, so close the phone app first.
Responses arrive as indications; they are routed by opcode into queues and the
caller waits on the queue for the command it sent.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner

from . import protocol as p

ADVERTISED_NAME = "PicPak"
CMD_GAP = 0.3  # seconds between commands; the frame drops back-to-back requests
UPLOAD_SETTLE = 3.0  # seconds for the frame to verify, store and refresh the panel


@dataclass(frozen=True)
class Found:
    address: str  # a per-Mac UUID on macOS, a MAC address on Linux
    name: str
    rssi: int | None


async def scan(timeout: float = 8.0) -> list[Found]:
    """All advertising PicPak frames in range, strongest signal first."""
    hits = await BleakScanner.discover(timeout=timeout, return_adv=True)
    out = [
        Found(d.address, d.name or adv.local_name or "", adv.rssi)
        for d, adv in hits.values()
        if (d.name or adv.local_name or "").startswith(ADVERTISED_NAME)
    ]
    return sorted(out, key=lambda f: -(f.rssi or -999))


class PicPak:
    """Use as ``async with PicPak(address) as frame: ...``."""

    def __init__(self, address: str, timeout: float = 15.0):
        self.address = address
        self._client = BleakClient(address, timeout=timeout)
        self._queues: dict[int, asyncio.Queue[bytes]] = defaultdict(asyncio.Queue)

    async def __aenter__(self) -> PicPak:
        await self._client.connect()
        await self._client.start_notify(p.FF01_DATA, self._on_indication)
        await self._client.start_notify(p.FF02_CTRL, self._on_indication)
        await asyncio.sleep(CMD_GAP)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.disconnect()

    def _on_indication(self, _sender: object, data: bytearray) -> None:
        if len(data) >= 3 and data[0] == p.SOF and data[-1] == p.EOF:
            self._queues[data[1]].put_nowait(bytes(data))

    async def _request(self, char: str, frame: bytes, reply_op: int, timeout: float = 5.0) -> bytes:
        q = self._queues[reply_op]
        while not q.empty():  # drop stale replies
            q.get_nowait()
        await self._client.write_gatt_char(char, frame, response=True)
        try:
            return await asyncio.wait_for(q.get(), timeout)
        finally:
            await asyncio.sleep(CMD_GAP)

    async def info(self) -> p.DeviceInfo:
        return p.parse_info(await self._request(p.FF02_CTRL, p.cmd_info(), p.OP_INFO))

    async def name(self) -> str:
        return p.parse_name(await self._request(p.FF02_CTRL, p.cmd_name(), p.OP_NAME))

    async def slots(self) -> list[int]:
        """Occupied slots. The reply opcode is not documented as 0x30, so accept the first long frame."""
        await self._client.write_gatt_char(p.FF01_DATA, p.cmd_list(), response=True)
        deadline = asyncio.get_running_loop().time() + 5.0
        while True:
            for op, q in self._queues.items():
                if op not in (p.OP_INFO, p.OP_NAME, p.OP_STATUS) and not q.empty():
                    frame = q.get_nowait()
                    if len(frame) > 10:
                        await asyncio.sleep(CMD_GAP)
                        return p.parse_list(frame)
            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError("no list-images response")
            await asyncio.sleep(0.05)

    async def delete(self, slot: int) -> bool:
        _, ok = p.parse_delete(await self._request(p.FF01_DATA, p.cmd_delete(slot), p.OP_DELETE))
        return ok

    async def upload(self, slot: int, packed: bytes) -> None:
        """Write all chunks with write-response flow control, then commit with the MD5."""
        for pkt in p.data_packets(slot, packed):
            await self._client.write_gatt_char(p.FF01_DATA, pkt, response=True)
        await self._client.write_gatt_char(p.FF01_DATA, p.md5_commit(slot, packed), response=True)
        await asyncio.sleep(UPLOAD_SETTLE)

    async def first_free_slot(self) -> int:
        used = set(await self.slots())
        for s in range(1, p.MAX_SLOTS + 1):
            if s not in used:
                return s
        raise RuntimeError("all 500 slots are in use")
