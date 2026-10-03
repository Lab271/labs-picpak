# PicPak BLE protocol: what we use and how sure we are

Working reference for `src/labs_picpak/protocol.py`. Every command lists its source and whether we
verified it on our own frames.

**Sources**
- **G**: Andy Copley's reverse-engineering gist, firmware V0.4.1 (updated 2026-09-18):
  <https://gist.github.com/andycopley/a44654da2ef9cb0da0ceaa8711afcade>
- **B**: picpak-ble protocol notes (MIT), tested on shipping firmware in July 2026:
  <https://github.com/akx/picpak-ble/blob/main/PROTOCOL.md>
- **L**: captured by us (Lab271) on our frames, firmware **V1.1.20**, hardware V0.0.1, 2026-10-02/03.

## Transport

- GATT service `0xFF00`. `FF01`: images, slots, display. `FF02`: name, status, info. `FF03`: firmware
  update. **picpak never writes to FF03.**
- One connected client at a time. If the phone app is connected ("pairing mode"), the Mac can't connect.
- The frame stops advertising soon after it wakes. On macOS (CoreBluetooth) a connection only works for a
  device seen by a scan in the same process, so `PicPak.__aenter__` scans for the address first.
- Every message: `AA <opcode> <payload> FF`. Slots 1..500, 16-bit little-endian.

## Commands

| Purpose | TX | RX | Source | On V1.1.20 (L) |
|---|---|---|---|---|
| Device name, read | `AA 06 02 FF` | `AA 06 01 <len> <name> FF` | G, B | not exercised by the CLI yet |
| Device name, write | `AA 06 00 <len> <utf-8> FF` | `AA 06 01 … FF` (01 = written) | B | **untested**: `rename --on-device` |
| Status | `AA 07 02 FF` | `AA 07 01 10 0E 00 00 01 FF` | G | not used. B reads 07 as config: refresh interval u32 + open-door flag |
| Device info | `AA 08 02 FF` | `AA 08 <battery%> <flag> 00 <hw:10> <fw:10> <serial:10> … FF` (57 bytes) | G, B | ✓ battery 62%, `V1.1.20`, serial `D4NHP4N` |
| List slots (legacy) | `AA 30 FF` | `AA 31 <500 bytes, 01 = used> FF` (503 bytes) | B (G said "packetType") | ✓ **reply opcode `0x31`** |
| List slots (compact) | `AA 34 FF` | `AA 35 <count:u16> <used:u16> <len:u16> <bitmap> FF` | B | not used; B: shipping firmware answers only 30/31 |
| Delete slot | `AA 32 <slot:u16> FF` | `AA 33 <slot:u16> <status> FF` (00 = ok) | B (G said "packetType") | ✓ **reply opcode `0x33`**; deleting an empty slot also returns 00 |
| Show slot | `AA 36 <slot:u16> FF` | `AA 37 <slot:u16> <status> FF` | B | **untested**: `show` |
| What's on screen | `AA 38 02 FF` | `AA 39 <type> <slot:u16> <flags> FF` | B | **untested**: `now`. Types: 0 unknown, 1 stored photo, 2 built-in, 3 raw, 4 low battery, 5 blank; flags bit 0 = idle |
| Upload chunk | `AA 01 <slot:u16> <n> <last> <len:u16> <≤236 bytes> FF` × 128 | write responses | G, B | ✓ slots 2 and 3 on both frames |
| Upload commit | `AA 04 <slot:u16> 00 <md5:16> FF` | — | G, B | ✓ |
| Read MD5 | `AA 04 <slot:u16> 02 FF` | `AA 04 <slot:u16> <x> <md5:16> FF` | G | ✓ used by `list`; matches our records |
| Read image | `AA 03 <slot:u16> FF` | `AA 02 …` chunks, then `AA 04 … md5` | G, B | B: **not implemented** in shipping firmware (times out). `pull` kept for later |

After an upload the frame streams the image back as `AA 02 …` packets (G counted ~1,700 indications).
`slots()` ignores those when it looks for the list reply.

## Image format

400 × 300 pixels, 4 colours (0 black, 1 white, 2 yellow, 3 red), 2 bits per pixel, 4 pixels per byte MSB
first: 30,000 bytes. The panel scans **bottom to top**: flip vertically before packing (G, verified by our
uploads). There is no orange: orange becomes yellow (`--no-dither`) or a red/yellow mix (dither).

## Open

- Does a name written with `06 00` change the advertised BLE name? If yes, frames can be found by name on
  any Mac, and `import` on another machine no longer needs a rename.
- Behaviour when uploading to an occupied slot (`push` uses the first free slot to avoid it).
- B: allow ~500 ms after a delete before writing the same slot again.

## How the V1.1.20 replies were found

`scripts/sniff.py` subscribes to FF01 and FF02, sends a few commands and prints every indication with a
timestamp. Use it whenever a command times out on new firmware:

```bash
uv run python scripts/sniff.py --frame frame-1 list "delete 1" list
```
