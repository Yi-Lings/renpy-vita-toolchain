#!/usr/bin/env python3
"""把 Ren'Py 游戏素材降到「实际用不到的像素全部丢掉」的尺寸。

为什么能提速（2026-10-31 实测推论）：
  * Angel Sex Pet 的 CG 是 1920x1440 RGBA，解码后 11 MB/张；
  * 但游戏 virtual 分辨率只有 1365x768，4:3 的图显示时被缩到 1024x768，
    多出来的像素纯属浪费 CPU（解码）+ 显存；
  * Vita 只有 ~330 MB 可用内存，且 renpy.py 里写死
    RENPY_LESS_MEMORY=True，会关掉预加载 → 每张图都得现解码，卡顿。

做法：
  1. 超过 `--max-w/--max-h` 的图等比缩到框内；
  2. alpha 全 255 的图从 RGBA 转 RGB（省 25% 内存，PNG 也小）；
  3. PNG 用 optimize + compress_level 9 重存。

用法：
    python optimize_images.py <src.rpa> <dst.rpa> --max-w 1366 --max-h 768
    python optimize_images.py <src.rpa> <dst.rpa> --dry-run   # 只统计
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rpa_tool import iter_rpa, write_rpa

try:
    from PIL import Image
except ImportError:
    Image = None

IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def process(data, max_w, max_h):
    """返回 (新字节, 说明)；不需要改就返回 (原字节, None)。"""
    im = Image.open(io.BytesIO(data))
    im.load()
    orig = im.size
    changed = False

    w, h = im.size
    if w > max_w or h > max_h:
        scale = min(float(max_w) / w, float(max_h) / h)
        nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        im = im.resize((nw, nh), Image.LANCZOS)
        changed = True

    if im.mode == "RGBA":
        # 全不透明就转 RGB
        alpha = im.getchannel("A")
        if alpha.getextrema()[0] == 255:
            im = im.convert("RGB")
            changed = True
    elif im.mode == "P":
        im = im.convert("RGBA" if "transparency" in im.info else "RGB")
        changed = True
    elif im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
        changed = True

    if not changed:
        return data, None

    out = io.BytesIO()
    im.save(out, "PNG", optimize=True, compress_level=9)
    new = out.getvalue()
    if len(new) >= len(data):
        # 重存反而更大（小图 / 已经压得很好的图），保留原样
        return data, None
    return new, "%dx%d %s -> %dx%d %s" % (
        orig[0], orig[1], Image.open(io.BytesIO(data)).mode,
        im.size[0], im.size[1], im.mode,
    )


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        return 1
    src, dst = args[0], args[1]
    max_w = max_h = None
    dry = "--dry-run" in args
    if "--max-w" in args:
        max_w = int(args[args.index("--max-w") + 1])
    if "--max-h" in args:
        max_h = int(args[args.index("--max-h") + 1])
    if not max_w or not max_h:
        max_w, max_h = 1366, 768

    items = []
    saved = 0
    changed_n = 0
    total_before = total_after = 0
    for name, data in iter_rpa(src):
        if not name.lower().endswith(IMG_EXT):
            items.append((name, data))
            continue
        total_before += len(data)
        try:
            new, note = process(data, max_w, max_h)
        except Exception as exc:
            print("  !! %s: %s" % (name, exc))
            items.append((name, data))
            total_after += len(data)
            continue
        if note:
            changed_n += 1
            if changed_n <= 10:
                print("  %-40s %s" % (name, note))
        saved += len(data) - len(new)
        total_after += len(new)
        items.append((name, new))

    print()
    print("改动 %d 个文件" % changed_n)
    print("图片总大小 %.1f MB -> %.1f MB  (省 %.1f MB, %.0f%%)" % (
        total_before / 1e6, total_after / 1e6, saved / 1e6,
        100.0 * saved / max(1, total_before)))

    if dry:
        return 0

    write_rpa(dst, items)
    print("已写出 %s (%.2f MB)" % (dst, os.path.getsize(dst) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
