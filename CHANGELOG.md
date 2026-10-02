# Changelog

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
