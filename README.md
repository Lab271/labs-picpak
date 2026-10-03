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

Wake the frame (press its button) before each command; it stops advertising when it sleeps.
`make help` groups the targets into Operations, Build and Support.

```bash
make scan                           # frames in range
uv run picpak name 8E1F2C3A-… kitchen
make identify FRAME=kitchen         # shows "kitchen" on that frame
make info                           # battery, firmware, serial, image count
make list                           # slot · status · date · source, MD5-checked against the records
make push IMG=photo.jpg             # dither, upload to the first free slot, record it
make push IMG=logo.png ARGS="--no-dither --fit contain"
make pull SLOT=1                    # download an unknown image as a preview (30-60 s)
make delete SLOT=1                  # delete on the frame and forget the record
make dashboard                      # HTML overview of all frames and slots
make export FILE=picpak.zip         # move the state to another machine…
make import FILE=picpak.zip         # …and load it there (merge; ARGS=--replace to overwrite)
```

With one named frame `FRAME=` can be left out. `uv run picpak --help` lists every option.

## State (XDG)

The frame stores pixels and an MD5 per slot, nothing else. picpak keeps the rest:

| Where | What |
|---|---|
| `$XDG_CONFIG_HOME/picpak/frames.toml` (`~/.config/…`) | frame names → Bluetooth addresses |
| `$XDG_DATA_HOME/picpak/library.json` (`~/.local/share/…`) | per frame and slot: source file, MD5, fit, dither, when; last seen battery and firmware |
| `$XDG_DATA_HOME/picpak/previews/<frame>/<slot>.png` | what the frame shows |
| `$XDG_DATA_HOME/picpak/dashboard.html` | generated overview |

`list` compares each slot's MD5 on the frame with the record: **ok** (matches), **changed** (another image
is there), **unknown** (not pushed by picpak: `pull` it to see it), **gone** (recorded, no longer on the frame).

Every frame advertises the name `PicPak`, so frames are remembered by Bluetooth address. On macOS that
address is a UUID that differs per Mac: after `import` on another machine, wake each frame, `scan`, and
`name` it again. Records and previews follow the name, so nothing else changes.

## How it works

| Module | Job |
|---|---|
| `protocol.py` | Byte frames (`0xAA <opcode> <payload> 0xFF`): commands, upload chunks, MD5 commit, response parsing. No I/O. |
| `image.py` | Fit to 400 × 300, Floyd-Steinberg dither to the four colours, pack 2 bits per pixel, flip vertically (the panel scans bottom to top). |
| `device.py` | Async Bluetooth client on [bleak](https://github.com/hbldh/bleak): connect, subscribe to indications, request/response. |
| `config.py` | Frame names ↔ addresses. |
| `library.py` | The state database: records, previews, reconcile with the frame, export/import. |
| `dashboard.py` | The static HTML overview. |
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
