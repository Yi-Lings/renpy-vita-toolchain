#!/usr/bin/env python3
"""Generate Vita sce_sys artwork from a game's own logo.

Hard rules learned the hard way (0x8010113D = "incorrect LiveArea asset
image formats"):
  * every asset must be 8-bit indexed (PNG colour type 3, bit depth 8)
  * icon0 and bg must be opaque (no alpha)
  * startup may keep alpha, but must still be 8-bit
  * no interlacing
"""
import os
import struct
import sys

from PIL import Image

SCE = sys.argv[1]
LOGO = sys.argv[2]
ALT = sys.argv[3] if len(sys.argv) > 3 else None
TITLE_LINE = sys.argv[4] if len(sys.argv) > 4 else ""


def fit(img, size, bg=(16, 16, 20)):
    w, h = size
    canvas = Image.new("RGB", size, bg)
    r = min(w / img.width, h / img.height)
    nw, nh = max(1, int(img.width * r)), max(1, int(img.height * r))
    resized = img.convert("RGBA").resize((nw, nh), Image.LANCZOS)
    canvas.paste(resized, ((w - nw) // 2, (h - nh) // 2), resized)
    return canvas


def save8(img, path):
    """Opaque, non-interlaced, 8-bit indexed."""
    img.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT).save(path, "PNG", optimize=True)


def info(p):
    d = open(p, "rb").read()
    return struct.unpack(">II", d[16:24]), d[24], d[25], d[28]


os.makedirs(os.path.join(SCE, "livearea", "contents"), exist_ok=True)
logo = Image.open(LOGO)
alt = Image.open(ALT) if ALT else logo

targets = [
    (fit(logo, (128, 128)), os.path.join(SCE, "icon0.png")),
    (fit(logo, (960, 544)), os.path.join(SCE, "pic0.png")),
    (fit(logo, (840, 500)), os.path.join(SCE, "livearea", "contents", "bg.png")),
    (fit(alt, (280, 158)), os.path.join(SCE, "livearea", "contents", "startup.png")),
]
for img, path in targets:
    save8(img, path)
    (w, h), bit, ctype, inter = info(path)
    ok = "OK" if (ctype == 3 and bit == 8 and inter == 0) else "!! 不合规"
    print(f"  {os.path.basename(path):12} {w}x{h}  bit={bit} ctype={ctype} interlace={inter}  "
          f"{os.path.getsize(path)/1024:.1f}KB  {ok}")

TEMPLATE = f"""<?xml version="1.0" encoding="utf-8"?>
<livearea style="a1" format-ver="01.00" content-rev="1">
\t<livearea-background>
\t\t<image>bg.png</image>
\t</livearea-background>
\t<frame id="frame1" style="a">
\t\t<liveitem>
\t\t\t<type>a</type>
\t\t\t<text x="0" y="0" align="left" color="0xFFFFFF" size="12">START</text>
\t\t\t<text x="0" y="32" align="left" color="0xAAAAAA" size="8">{TITLE_LINE}</text>
\t\t</liveitem>
\t</frame>
</livearea>
"""
open(os.path.join(SCE, "livearea", "contents", "template.xml"), "w", encoding="utf-8").write(TEMPLATE)
print("  template.xml 已生成")
