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
            occ = [1 if s in self.slots else 0 for s in range(1, 21)]
            self._send(char, bytes([0xAA, 0x30, *occ, 0xFF]))
        elif op == p.OP_DELETE:
            slot = data[2] | (data[3] << 8)
            ok = self.slots.pop(slot, None) is not None
            self._send(char, bytes([0xAA, 0x32, data[2], data[3], 0 if ok else 1, 0xFF]))
        elif op == p.OP_DATA:
            self.chunks.append(bytes(data[8:-1]))
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
