"""PicPak client against a fake frame that answers like firmware V0.4.1."""

import asyncio
import hashlib

import pytest

from labs_picpak import device
from labs_picpak import protocol as p


class FakeFrame:
    """Stands in for bleak.BleakClient: answers writes with indications."""

    def __init__(self, address, timeout=None):
        self.address = address
        self.callbacks = {}
        self.slots = {1: b"x"}
        self.chunks: list[bytes] = []
        self.committed: dict[int, bytes] = {}

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def start_notify(self, char, cb):
        self.callbacks[char] = cb

    def _send(self, char, frame):
        asyncio.get_running_loop().call_soon(self.callbacks[char], None, bytearray(frame))

    async def write_gatt_char(self, char, data, response=True):
        op = data[1]
        if char == p.FF02_CTRL and op == p.OP_INFO:
            info = bytearray(57)
            info[0], info[1], info[2], info[-1] = 0xAA, 0x08, 77, 0xFF
            info[15:21] = b"V0.4.1"
            self._send(char, info)
        elif op == p.OP_LIST:
            occ = [1 if s in self.slots else 0 for s in range(1, 501)]
            self._send(char, bytes([0xAA, 0x31, *occ, 0xFF]))  # V1.1.20 shape
        elif op == p.OP_DELETE:
            slot = data[2] | (data[3] << 8)
            ok = self.slots.pop(slot, None) is not None
            self._send(char, bytes([0xAA, 0x33, data[2], data[3], 0 if ok else 1, 0xFF]))  # V1.1.20 shape
        elif op == p.OP_DATA:
            self.chunks.append(bytes(data[8:-1]))
        elif op == p.OP_READ:
            slot = data[2] | (data[3] << 8)
            img = self.slots[slot]
            parts = [img[i : i + 236] for i in range(0, len(img), 236)]
            for n, part in enumerate(parts):
                last = 1 if n == len(parts) - 1 else 0
                self._send(char, bytes([0xAA, 0x02, data[2], data[3], n, last, len(part), 0]) + part + b"\xff")
        elif op == p.OP_MD5 and len(data) == 6:
            slot = data[2] | (data[3] << 8)
            # a late reply for another slot first, then the right one
            self._send(char, bytes([0xAA, 0x04, 99, 0, 0x02]) + bytes(16) + b"\xff")
            md5 = hashlib.md5(self.slots[slot]).digest()
            self._send(char, bytes([0xAA, 0x04, data[2], data[3], 0x02]) + md5 + b"\xff")
        elif op == p.OP_MD5 and len(data) == 22:
            img = b"".join(self.chunks)
            assert data[5:21] == hashlib.md5(img).digest()
            self.slots[data[2] | (data[3] << 8)] = img


class FakeScanner:
    visible = True

    @staticmethod
    async def find_device_by_address(address, timeout=None):
        return address if FakeScanner.visible else None


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(device, "BleakClient", FakeFrame)
    monkeypatch.setattr(device, "BleakScanner", FakeScanner)
    FakeScanner.visible = True
    monkeypatch.setattr(device, "CMD_GAP", 0)
    monkeypatch.setattr(device, "UPLOAD_SETTLE", 0)


def test_info_slots_upload_delete(fake):
    async def run():
        async with device.PicPak("ADDR") as frame:
            assert (await frame.info()).firmware == "V0.4.1"
            assert await frame.slots() == [1]
            free = await frame.first_free_slot()
            assert free == 2
            await frame.upload(free, bytes(30_000))
            client = frame._client
            assert client.slots[2] == bytes(30_000)
            assert await frame.read_md5(2) == hashlib.md5(bytes(30_000)).hexdigest()
            assert await frame.read_image(2) == bytes(30_000)
            assert await frame.delete(1) is True
            assert await frame.delete(9) is False

    asyncio.run(run())


def test_sleeping_frame_gives_a_clear_error(fake):
    FakeScanner.visible = False

    async def run():
        async with device.PicPak("ADDR"):
            pass

    with pytest.raises(device.FrameNotFound, match="wake the frame"):
        asyncio.run(run())
