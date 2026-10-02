# labs-picpak

The Lab271 PicPak drive: control [PicPak](https://www.picpak.tech) colour e-ink frames from a laptop over Bluetooth LE, without the phone app.

> **Unofficial.** Lab271 is not affiliated with the maker of PicPak. This tool is built on a
> reverse-engineered description of the Bluetooth protocol (firmware V0.4.1) by Andy Copley:
> <https://gist.github.com/andycopley/a44654da2ef9cb0da0ceaa8711afcade>. A firmware update can break it.
> The tool never touches the firmware-update channel (FF03).

## What the frame is

- 4.2" e-ink, 400 × 300 pixels, four colours: black, white, yellow, red.
- Bluetooth LE only in firmware V0.4.1 (the ESP32-C3 has Wi-Fi, the firmware doesn't use it).
- One connected client at a time: close the phone app before using this tool.
- 500 image slots. An image is 30,000 bytes, uploaded in 128 chunks and committed with an MD5.

## Install

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
make dev            # creates .venv with the picpak command
uv run picpak --help
```

On macOS, allow Bluetooth for your terminal app the first time (System Settings → Privacy & Security → Bluetooth).

## Use

```bash
picpak scan                         # wake the frame first; lists frames in range
picpak name 8E1F2C3A-… kitchen      # remember a frame under a name
picpak identify -f kitchen          # shows "kitchen" on that frame, to check which one is which
picpak info -f kitchen              # battery, firmware, serial, image count
picpak preview photo.jpg            # photo.picpak.png: what the frame will show (no Bluetooth)
picpak push photo.jpg -f kitchen    # dither, upload to the first free slot
picpak push logo.png -f desk --fit contain --slot 12
picpak list -f desk                 # occupied slots
picpak delete 12 -f desk
```

Every frame advertises the name `PicPak`, and the serial number can be empty. So frames are remembered by
their Bluetooth address in `~/.config/picpak/frames.toml`. On macOS that address is a UUID that is stable on
one Mac but different on another Mac, so the file is per machine and not part of this repo.

## How it works

| Module | Job |
|---|---|
| `protocol.py` | Byte frames (`0xAA <opcode> <payload> 0xFF`): commands, upload chunks, MD5 commit, response parsing. No I/O. |
| `image.py` | Fit to 400 × 300, Floyd-Steinberg dither to the four colours, pack 2 bits per pixel, flip vertically (the panel scans bottom to top). |
| `device.py` | Async Bluetooth client on [bleak](https://github.com/hbldh/bleak): connect, subscribe to indications, request/response. |
| `config.py` | Frame names ↔ addresses. |
| `cli.py` | The `picpak` command. |

## Open questions

- How to switch which stored slot is on screen is not documented. A new upload appears to show right away
  (unverified on our frames).
- What happens when you upload to an occupied slot is unverified, so `push` uses the first free slot by default.
- The response to *list images* has no documented opcode; the client takes the first long frame on FF01.

## Develop

```bash
make check    # ruff, pyright, pytest with coverage
make help
```

The unit tests run without hardware: `tests/unit/test_device.py` drives the client against a fake frame.

## License

Apache 2.0, see [LICENSE](LICENSE).
