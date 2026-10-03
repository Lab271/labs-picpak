"""PicPak BLE wire protocol: pure frame builders and parsers, no I/O.

Based on the reverse-engineered protocol for firmware V0.4.1:
https://gist.github.com/andycopley/a44654da2ef9cb0da0ceaa8711afcade

Every message is ``0xAA <opcode> <payload> 0xFF``. Slots are 1-indexed, 16-bit little-endian.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

SERVICE = "0000ff00-0000-1000-8000-00805f9b34fb"
FF01_DATA = "0000ff01-0000-1000-8000-00805f9b34fb"  # image data, list, delete, read
FF02_CTRL = "0000ff02-0000-1000-8000-00805f9b34fb"  # name, status, device info
# FF03 is OTA firmware update. This package never writes to it.

SOF, EOF = 0xAA, 0xFF
MAX_PAYLOAD = 236
MAX_SLOTS = 500

OP_DATA = 0x01
OP_READ = 0x03
OP_MD5 = 0x04
OP_NAME = 0x06
OP_STATUS = 0x07
OP_INFO = 0x08
OP_LIST = 0x30
OP_LIST_REPLY = 0x31  # seen on firmware V1.1.20: aa 31 <500 slot bytes> ff
OP_DELETE = 0x32
OP_DELETE_REPLY = 0x33  # seen on firmware V1.1.20: aa 33 <slot lo> <slot hi> <result> ff


class ProtocolError(ValueError):
    """A frame that does not match the documented shape."""


def _slot(slot: int) -> bytes:
    if not 1 <= slot <= MAX_SLOTS:
        raise ValueError(f"slot must be 1..{MAX_SLOTS}, got {slot}")
    return bytes([slot & 0xFF, (slot >> 8) & 0xFF])


def _check(frame: bytes | bytearray, opcode: int, min_len: int = 3) -> None:
    if len(frame) < min_len or frame[0] != SOF or frame[-1] != EOF or frame[1] != opcode:
        raise ProtocolError(f"expected opcode 0x{opcode:02x}, got {bytes(frame).hex(' ')}")


# ---- commands (client -> device) -------------------------------------------------

def cmd_name() -> bytes:
    return bytes([SOF, OP_NAME, 0x02, EOF])


def cmd_status() -> bytes:
    return bytes([SOF, OP_STATUS, 0x02, EOF])


def cmd_info() -> bytes:
    return bytes([SOF, OP_INFO, 0x02, EOF])


def cmd_list() -> bytes:
    return bytes([SOF, OP_LIST, EOF])


def cmd_delete(slot: int) -> bytes:
    return bytes([SOF, OP_DELETE]) + _slot(slot) + bytes([EOF])


def cmd_read(slot: int) -> bytes:
    return bytes([SOF, OP_READ]) + _slot(slot) + bytes([EOF])


def cmd_read_md5(slot: int) -> bytes:
    return bytes([SOF, OP_MD5]) + _slot(slot) + bytes([0x02, EOF])


def data_packets(slot: int, packed: bytes) -> list[bytes]:
    """Split a packed image into upload chunks for FF01."""
    if not packed:
        raise ValueError("empty image")
    chunks = [packed[i : i + MAX_PAYLOAD] for i in range(0, len(packed), MAX_PAYLOAD)]
    if len(chunks) > 256:
        raise ValueError("image too large: packet number is one byte")
    out = []
    for n, payload in enumerate(chunks):
        last = n == len(chunks) - 1
        header = bytes([SOF, OP_DATA]) + _slot(slot) + bytes(
            [n, 0x01 if last else 0x00, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF]
        )
        out.append(header + payload + bytes([EOF]))
    return out


def md5_commit(slot: int, packed: bytes, flag: int = 0x00) -> bytes:
    """The packet that commits an upload: MD5 over the packed pixel bytes."""
    return bytes([SOF, OP_MD5]) + _slot(slot) + bytes([flag & 0xFF]) + hashlib.md5(packed).digest() + bytes([EOF])


# ---- responses (device -> client) ------------------------------------------------

@dataclass(frozen=True)
class DeviceInfo:
    battery: int
    hardware: str
    firmware: str
    serial: str


def _ascii(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


def parse_info(frame: bytes | bytearray) -> DeviceInfo:
    """Parse the 0x08 device-info response (57 bytes)."""
    _check(frame, OP_INFO, min_len=36)
    b = bytes(frame)
    return DeviceInfo(battery=b[2], hardware=_ascii(b[5:15]), firmware=_ascii(b[15:25]), serial=_ascii(b[25:35]))


def parse_name(frame: bytes | bytearray) -> str:
    _check(frame, OP_NAME, min_len=5)
    n = frame[3]
    return bytes(frame[4 : 4 + n]).decode("ascii", errors="replace")


def parse_list(frame: bytes | bytearray) -> list[int]:
    """Occupied slot numbers from a list-images response."""
    if len(frame) < 3 or frame[0] != SOF or frame[-1] != EOF:
        raise ProtocolError(f"bad list response: {bytes(frame[:8]).hex(' ')}…")
    return [i + 1 for i, v in enumerate(frame[2:-1]) if v == 0x01]


def parse_delete(frame: bytes | bytearray) -> tuple[int, bool]:
    """(slot, success) from a delete response (0x33 on V1.1.20; 0x32 as documented for V0.4.1)."""
    if len(frame) >= 6 and frame[1] == OP_DELETE:
        _check(frame, OP_DELETE, min_len=6)
    else:
        _check(frame, OP_DELETE_REPLY, min_len=6)
    return frame[2] | (frame[3] << 8), frame[4] == 0x00


def parse_md5(frame: bytes | bytearray) -> tuple[int, bytes]:
    """(slot, 16-byte MD5) from a read-MD5 response."""
    _check(frame, OP_MD5, min_len=22)
    return frame[2] | (frame[3] << 8), bytes(frame[5:21])


@dataclass(frozen=True)
class Chunk:
    slot: int
    number: int
    last: bool
    payload: bytes


def parse_chunk(frame: bytes | bytearray) -> Chunk:
    """An image data packet (upload shape, also used when the frame streams an image back)."""
    if len(frame) < 9 or frame[0] != SOF or frame[-1] != EOF:
        raise ProtocolError(f"bad data packet: {bytes(frame[:8]).hex(' ')}…")
    n = frame[6] | (frame[7] << 8)
    return Chunk(frame[2] | (frame[3] << 8), frame[4], frame[5] == 0x01, bytes(frame[8 : 8 + n]))
