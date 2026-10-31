#!/usr/bin/env python3
"""Convert sce_sys LiveArea artwork to the format the Vita installer accepts.

0x8010113D = "incorrect LiveArea asset image formats". The rules, per
Hammerill/livearea-specs and two independently hardware-verified fixes:
  * every asset must be 8-bit (indexed palette, PNG colour type 3)
  * icon0 and bg must be opaque (no alpha)
  * startup may keep alpha, but must still be 8-bit
  * no interlacing
"""
import os
import struct
import sys

from PIL import Image

SCE = sys.argv[1] if len(sys.argv) > 1 else r"F:\PSV移植\build\MaidMansion\sce_sys"

# name -> allow_alpha
TARGETS = {
    os.path.join(SCE, "icon0.png"): False,
    os.path.join(SCE, "pic0.png"): False,
    os.path.join(SCE, "livearea", "contents", "bg.png"): False,
    os.path.join(SCE, "livearea", "contents", "startup.png"): True,
}


def png_info(path):
    d = open(path, "rb").read()
    w, h = struct.unpack(">II", d[16:24])
    return w, h, d[24], d[25], d[28]  # width, height, bitdepth, colortype, interlace


for path, allow_alpha in TARGETS.items():
    if not os.path.exists(path):
        print(f"  缺失: {path}")
        continue
    im = Image.open(path)
    orig = png_info(path)

    if allow_alpha and im.mode in ("RGBA", "LA"):
        rgba = im.convert("RGBA")
        # quantise to 256 colours keeping transparency
        im8 = rgba.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
    else:
        im8 = im.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)

    im8.save(path, "PNG", optimize=True)
    now = png_info(path)
    ok = "OK" if (now[3] == 3 and now[2] == 8 and now[4] == 0) else "!! 仍不合规"
    print(f"  {os.path.basename(path):14} {orig[0]}x{orig[1]} ctype {orig[3]}->{now[3]} "
          f"bit {orig[2]}->{now[2]} interlace={now[4]}  {os.path.getsize(path)/1024:.1f}KB  {ok}")
