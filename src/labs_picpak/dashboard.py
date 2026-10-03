"""A static HTML dashboard of all frames and slots, written to the XDG data directory."""

from __future__ import annotations

import html
from pathlib import Path

from . import library

STATUS_TEXT = {
    "ok": "on frame, matches record",
    "changed": "on frame, different image than recorded",
    "unknown": "on frame, not recorded (pull it to see it)",
    "gone": "recorded, no longer on frame",
}

CSS = """
:root{--bg:#020c17;--panel:#082646;--line:#12263f;--text:#fff;--muted:#8aa0b8;--tq:#1ee8ed;--warn:#ff8d33}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 "Inter","Avenir Next",system-ui,sans-serif;padding:32px 24px}
h1{font-size:28px;font-weight:900;letter-spacing:-.03em;margin:0 0 4px}
.meta,.k,code{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace;font-size:12px;color:var(--muted)}
section{margin-top:32px}h2{font-size:20px;margin:0 0 4px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px;margin-top:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px 12px 12px 0;overflow:hidden}
.card img{width:100%;aspect-ratio:4/3;object-fit:cover;display:block;background:#061323}
.noimg{aspect-ratio:4/3;display:grid;place-items:center;color:var(--muted);background:#061323}
.body{padding:10px 12px}.slot{font-weight:800}.src{word-break:break-all}
.ok{color:var(--tq)}.changed,.unknown{color:var(--warn)}.gone{color:var(--muted)}
"""


def render() -> Path:
    frames = library.load()
    parts = [
        f"<!doctype html><meta charset=utf-8><title>picpak</title><style>{CSS}</style>",
        "<h1>picpak</h1>",
        f'<div class="meta">generated {html.escape(library.now())} \\ {len(frames)} frame(s)</div>',
    ]
    for name, fs in sorted(frames.items()):
        slots = sorted(set(fs.on_frame) | set(fs.slots))
        info = " \\ ".join(
            x
            for x in [
                f"battery {fs.battery}%" if fs.battery is not None else "",
                f"firmware {fs.firmware}" if fs.firmware else "",
                f"serial {fs.serial}" if fs.serial else "",
                f"last seen {fs.seen_at}" if fs.seen_at else "never listed",
            ]
            if x
        )
        parts.append(
            f"<section><h2>{html.escape(name)}</h2><div class=meta>{html.escape(info)}<br>"
            f"<code>{html.escape(fs.address)}</code></div><div class=grid>"
        )
        for s in slots:
            e = fs.slots.get(s)
            st = fs.status.get(s, "ok" if e else "unknown")
            prev = library.preview_path(name, s)
            img = (
                f'<img src="{prev.relative_to(library.data_dir()).as_posix()}" alt="slot {s}">'
                if prev.exists()
                else '<div class="noimg">no preview</div>'
            )
            src = html.escape(Path(e.source).name) if e else "?"
            when = html.escape(e.pushed_at) if e else ""
            how = (f"{e.fit or '-'} \\ {'dither' if e.dither else 'no dither'} \\ {e.origin}") if e else ""
            parts.append(
                f"<div class=card>{img}<div class=body><span class=slot>slot {s}</span> "
                f'<span class="k {st}">\\ {html.escape(STATUS_TEXT.get(st, st))}</span>'
                f"<div class=src>{src}</div><div class=k>{when}</div><div class=k>{html.escape(how)}</div>"
                "</div></div>"
            )
        parts.append("</div></section>")
    out = library.data_dir() / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts) + "\n")
    return out
