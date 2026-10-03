import hashlib

import pytest

from labs_picpak import protocol as p


def test_short_commands_match_documented_bytes():
    assert p.cmd_name() == bytes.fromhex("aa0602ff")
    assert p.cmd_status() == bytes.fromhex("aa0702ff")
    assert p.cmd_info() == bytes.fromhex("aa0802ff")
    assert p.cmd_list() == bytes.fromhex("aa30ff")
    assert p.cmd_delete(1) == bytes.fromhex("aa320100ff")
    assert p.cmd_read_md5(258) == bytes.fromhex("aa04020102ff")


@pytest.mark.parametrize("slot", [0, 501])
def test_slot_out_of_range(slot):
    with pytest.raises(ValueError):
        p.cmd_delete(slot)


def test_full_image_is_128_chunks_with_last_flag():
    packed = bytes(range(256)) * 117 + bytes(48)  # 30,000 bytes
    assert len(packed) == 30_000
    pkts = p.data_packets(3, packed)
    assert len(pkts) == 128
    first, last = pkts[0], pkts[-1]
    assert first[:8] == bytes([0xAA, 0x01, 3, 0, 0, 0, 236, 0])
    assert first[-1] == 0xFF and len(first) == 236 + 9
    assert last[4] == 127 and last[5] == 1
    assert last[6] | (last[7] << 8) == 30_000 - 127 * 236
    assert b"".join(pk[8:-1] for pk in pkts) == packed


def test_md5_commit_layout():
    packed = b"\x01" * 30_000
    pkt = p.md5_commit(2, packed)
    assert len(pkt) == 22
    assert pkt[:5] == bytes([0xAA, 0x04, 2, 0, 0])
    assert pkt[5:21] == hashlib.md5(packed).digest()
    assert pkt[-1] == 0xFF


def test_parse_name_sample_capture():
    assert p.parse_name(bytes.fromhex("aa06010650696350616bff")) == "PicPak"


def test_parse_info():
    frame = bytearray(57)
    frame[0], frame[1], frame[2], frame[3], frame[-1] = 0xAA, 0x08, 88, 0x28, 0xFF
    frame[5:11] = b"V0.0.1"
    frame[15:21] = b"V0.4.1"
    info = p.parse_info(frame)
    assert (info.battery, info.hardware, info.firmware, info.serial) == (88, "V0.0.1", "V0.4.1", "")


def test_parse_list_and_delete():
    frame = bytes([0xAA, 0x30, 1, 0, 1, 1] + [0] * 10 + [0xFF])
    assert p.parse_list(frame) == [1, 3, 4]
    assert p.parse_delete(bytes.fromhex("aa32050000ff")) == (5, True)
    assert p.parse_delete(bytes.fromhex("aa32050001ff")) == (5, False)


def test_wrong_opcode_rejected():
    with pytest.raises(p.ProtocolError):
        p.parse_name(bytes.fromhex("aa0801ff"))


def test_read_commands_and_parsers():
    assert p.cmd_read(3) == bytes.fromhex("aa030300ff")
    md5 = bytes(range(16))
    slot, got = p.parse_md5(bytes([0xAA, 0x04, 7, 0, 0x02]) + md5 + bytes([0xFF]))
    assert (slot, got) == (7, md5)
    c = p.parse_chunk(bytes([0xAA, 0x02, 4, 0, 9, 1, 3, 0, 1, 2, 3, 0xFF]))
    assert (c.slot, c.number, c.last, c.payload) == (4, 9, True, b"\x01\x02\x03")
