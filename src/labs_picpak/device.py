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


class FrameNotFound(RuntimeError):
    """The frame is not advertising (asleep, out of range, or connected to the phone app)."""


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

    def __init__(self, address: str, timeout: float = 15.0, scan_timeout: float = 12.0):
        self.address = address
        self._timeout = timeout
        self._scan_timeout = scan_timeout
        self._bleak: BleakClient | None = None
        self._queues: dict[int, asyncio.Queue[bytes]] = defaultdict(asyncio.Queue)

    @property
    def _client(self) -> BleakClient:
        if self._bleak is None:
            raise RuntimeError("not connected: use `async with PicPak(...)`")
        return self._bleak

    async def __aenter__(self) -> PicPak:
        # CoreBluetooth only connects to a device seen by a scan in this process, and the
        # frame stops advertising when it sleeps, so look for it first and say so if it is not there.
        found = await BleakScanner.find_device_by_address(self.address, timeout=self._scan_timeout)
        if found is None:
            raise FrameNotFound(f"{self.address} is not advertising: wake the frame (press its button) and retry")
        self._bleak = BleakClient(found, timeout=self._timeout)
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
        """Occupied slots. V1.1.20 replies with opcode 0x31; for other firmware take the first long frame."""
        q31 = self._queues[p.OP_LIST_REPLY]
        while not q31.empty():
            q31.get_nowait()
        await self._client.write_gatt_char(p.FF01_DATA, p.cmd_list(), response=True)
        deadline = asyncio.get_running_loop().time() + 5.0
        while True:
            if not q31.empty():
                await asyncio.sleep(CMD_GAP)
                return p.parse_list(q31.get_nowait())
            for op, q in self._queues.items():
                if (
                    op not in (p.OP_INFO, p.OP_NAME, p.OP_STATUS, p.OP_DATA, 0x02, p.OP_MD5, p.OP_DELETE_REPLY)
                    and not q.empty()
                ):
                    frame = q.get_nowait()
                    if len(frame) > 10:
                        await asyncio.sleep(CMD_GAP)
                        return p.parse_list(frame)
            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError("no list-images response")
            await asyncio.sleep(0.05)

    async def delete(self, slot: int) -> bool:
        """Delete a slot. Deleting an empty slot also reports success (seen on V1.1.20)."""
        replies = (self._queues[p.OP_DELETE_REPLY], self._queues[p.OP_DELETE])
        for q in replies:
            while not q.empty():
                q.get_nowait()
        await self._client.write_gatt_char(p.FF01_DATA, p.cmd_delete(slot), response=True)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5.0
        try:
            while loop.time() < deadline:
                for q in replies:
                    if not q.empty():
                        got, ok = p.parse_delete(q.get_nowait())
                        if got == slot:
                            return ok
                await asyncio.sleep(0.05)
            raise TimeoutError(f"no delete confirmation for slot {slot}")
        finally:
            await asyncio.sleep(CMD_GAP)

    async def upload(self, slot: int, packed: bytes) -> None:
        """Write all chunks with write-response flow control, then commit with the MD5."""
        for pkt in p.data_packets(slot, packed):
            await self._client.write_gatt_char(p.FF01_DATA, pkt, response=True)
        await self._client.write_gatt_char(p.FF01_DATA, p.md5_commit(slot, packed), response=True)
        await asyncio.sleep(UPLOAD_SETTLE)

    async def read_md5(self, slot: int) -> str:
        """The MD5 the frame stores for a slot (hex). Fast: no image transfer."""
        q = self._queues[p.OP_MD5]
        while not q.empty():
            q.get_nowait()
        await self._client.write_gatt_char(p.FF01_DATA, p.cmd_read_md5(slot), response=True)
        deadline = asyncio.get_running_loop().time() + 8.0
        try:
            while True:
                left = deadline - asyncio.get_running_loop().time()
                if left <= 0:
                    raise TimeoutError(f"no MD5 for slot {slot}")
                got, md5 = p.parse_md5(await asyncio.wait_for(q.get(), left))
                if got == slot:  # replies can arrive late for an earlier slot
                    return md5.hex()
        finally:
            await asyncio.sleep(CMD_GAP)

    async def read_image(self, slot: int, timeout: float = 120.0) -> bytes:
        """Download a stored image (packed 2 bpp). Slow: 30-60 s per image."""
        for op in (p.OP_DATA, 0x02):
            q = self._queues[op]
            while not q.empty():
                q.get_nowait()
        await self._client.write_gatt_char(p.FF01_DATA, p.cmd_read(slot), response=True)
        parts: dict[int, bytes] = {}
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            for op in (p.OP_DATA, 0x02):
                q = self._queues[op]
                while not q.empty():
                    chunk = p.parse_chunk(q.get_nowait())
                    if chunk.slot == slot:
                        parts[chunk.number] = chunk.payload
                        if chunk.last:
                            await asyncio.sleep(CMD_GAP)
                            return b"".join(parts[k] for k in sorted(parts))
            if loop.time() > deadline:
                raise TimeoutError(f"slot {slot}: got {len(parts)} chunks, then the frame stopped sending")
            await asyncio.sleep(0.05)

    async def first_free_slot(self) -> int:
        used = set(await self.slots())
        for s in range(1, p.MAX_SLOTS + 1):
            if s not in used:
                return s
        raise RuntimeError("all 500 slots are in use")
