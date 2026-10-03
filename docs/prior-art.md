# Prior art: other PicPak projects

Found on GitHub on 2026-10-03 (`gh search repos picpak`). Descriptions are the projects' own. Check here
before reverse-engineering anything new: most protocol questions have been answered by someone.

| Project | What it is | Use to us |
|---|---|---|
| [akx/picpak-ble](https://github.com/akx/picpak-ble) | "An independent Python client for the PicPak e-ink photo frame" (MIT) | **Main protocol source** besides the gist: name write, show slot, screen status, compact inventory, config, action bindings. Its [PROTOCOL.md](https://github.com/akx/picpak-ble/blob/main/PROTOCOL.md) is the first thing to read |
| [Andy Copley's gist](https://gist.github.com/andycopley/a44654da2ef9cb0da0ceaa8711afcade) | Reverse-engineered BLE protocol, firmware V0.4.1 | Original basis of this repo: upload, image format, MD5 |
| [PofMagicfingers/picpak-ha](https://github.com/PofMagicfingers/picpak-ha) | Home Assistant integration (`custom_components/picpak`) | If the frames ever move into Home Assistant |
| [GottZ/open-PicPak](https://github.com/GottZ/open-PicPak) | "The open firmware, tooling and documentation the PicPak e-ink frame should have shipped with" | Firmware replacement; also panel and hardware documentation |
| [varanu5/picpak-tesserae-client](https://github.com/varanu5/picpak-tesserae-client) | "Open ESP32-C3 firmware turning the PicPak … into a battery-powered Tesserae client" | Alternative firmware |
| [kohlhofer/picpak-semiotic](https://github.com/kohlhofer/picpak-semiotic) | Open firmware: weather, headlines, ISS passes | Example of what custom firmware can show |
| [Frankynov/picpak-studio](https://github.com/Frankynov/picpak-studio) | "A macOS poster editor for 4-colour e-paper PicPak panels. SwiftUI" | Designing images for the 4-colour panel |
| [MayeoinBread/inkstudio](https://github.com/MayeoinBread/inkstudio) | "Open-source app for Picpak hardware" | Alternative app |
| [DangerBlack/picpak-cli](https://github.com/DangerBlack/picpak-cli) | "A simple cli to send picture to picpak" | Another CLI; has a PROTOCOL.md |
| [dmellok/tesserae](https://github.com/dmellok/tesserae) | Has a PicPak device profile (`docs/hardware/picpak.md`, `devices/picpak_client/`) | Hardware notes |

**Custom firmware** (open-PicPak, tesserae, semiotic) replaces the factory firmware. That is out of
scope for picpak: the gist warns that a failed flash can brick the frame or damage the panel.

## Why labs-picpak exists anyway

picpak-ble covers the protocol well. This repo adds what we need for two frames on more than one machine:
named frames, a record of what is in each slot (checked against the frame's MD5s), a dashboard, and
export/import of that state.
