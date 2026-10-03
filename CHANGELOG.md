# Changelog

## [Unreleased]

### Added
- State database in the XDG data directory: every `push`, `identify` and `pull` is recorded with source,
  MD5, fit, dither and time, plus a preview PNG.
- `list` shows slot, status, date and source; status comes from each slot's MD5 on the frame
  (ok / changed / unknown / gone). `--fast` skips the MD5 check.
- `pull SLOT`: download a stored image as a preview (for images not pushed by picpak).
- `dashboard`: static HTML overview of all frames and slots, opened in the browser.
- `export FILE` / `import FILE [--replace]`: move frame names, records and previews to another machine.
- `delete` also forgets the record; `--local-only` forgets the record without touching the frame.
- `info` stores battery, firmware and serial for the dashboard.
- Make targets for all frame operations, and `make help` grouped into Operations, Build and Support.
- `rename OLD NEW` (`make rename`): rename a frame, or name one known only by address, keeping records and previews.
  `--on-device` also writes the name to the frame (`aa 06 00 <len> <name> ff`).
- `show SLOT` puts a stored picture on the screen (`aa 36`); `now` reports what the screen shows (`aa 38`).
  Both from the picpak-ble protocol notes (MIT).

### Fixed
- `delete` timed out after a successful delete on firmware V1.1.20: it replies with opcode 0x33, not 0x32.
  The list reply is 0x31 (503 bytes). Both captured on the device; V0.4.1 opcodes are still accepted.
- `list` no longer mistakes the image packets the frame streams back after an upload for the slot list.

## [0.1.0] - 2026-10-02

### Added
- `picpak` command: `scan`, `name`, `frames`, `identify`, `info`, `list`, `push`, `delete`, `preview`.
- `protocol.py`: frame builders and parsers for the PicPak BLE protocol (firmware V0.4.1).
- `image.py`: fit, Floyd-Steinberg dither to black/white/yellow/red, 2 bpp packing with the vertical flip.
- `device.py`: async bleak client with per-opcode response queues and a 0.3 s gap between commands.
- Local frame names in `~/.config/picpak/frames.toml`.
- `--no-dither` on `push` and `preview`: nearest colour, cleaner for flat graphics.
- Unit tests, including the client against a fake frame (no hardware needed).

### Fixed
- Connect scans for the frame first (CoreBluetooth only connects to a device seen in this process) and says
  "wake the frame" when it is asleep, instead of a bleak stack trace.

### Verified on hardware
- `scan`, `info` and `push` work on a frame with firmware **V1.1.20** (hardware V0.0.1), newer than the documented
  V0.4.1. The frame reports a serial.
