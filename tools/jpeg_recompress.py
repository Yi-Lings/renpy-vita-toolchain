#!/usr/bin/env python3
"""把不透明的图片转成 JPEG 数据（文件名仍保留 .png），可选先降采样。

为什么这么做（2026-10-31 实测）：
  Vita 上解一张 1024x768 的 PNG 要 139 ms（PC 上），JPEG 只要 5.2 ms
  —— 快 27 倍；体积只有 PNG 的 13%。游戏的卡顿几乎全在这里。

为什么能保留 .png 文件名：
  Ren'Py 的图片加载走 pygame_sdl2.image.load → SDL_image，
  **按文件内容嗅探格式，不看扩展名**。已用 SDK 的 Python 2.7 实测验证：
  把 JPEG 字节写进 test.png，SDL_image 正常返回 1024x768 的 surface。

限制：
  JPEG 没有 alpha 通道，所以只转 alpha 全 255 的图。
  带透明的（立绘、按钮、logo）保持 PNG。

⚠ 2026-10-31 补的坑：`--max-w/--max-h` 是**必须**的。
  gui_resource.rpa 曾经只跑了 JPEG、没跑降采样，导致
  gui/main_menu.png / gui/game_menu.png / gui/disclaimer.png 三张
  1920x1440 的图一直留在包里，而游戏里写死了 size=(1024,768)。
  解码后 8~11 MB 一张，每次进主菜单都要重解一次 → 10 秒卡顿。
  降采样和 JPEG 必须**在同一个工具里一次做完**，否则很容易漏掉一步。

用法：
    python jpeg_recompress.py <src.rpa> <dst.rpa> [--quality 85] [--dry-run]
                              [--max-w 1366] [--max-h 768]
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

IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp")


def is_opaque(im):
    if im.mode in ("RGB", "L"):
        return True
    if im.mode == "RGBA":
        return im.getchannel("A").getextrema()[0] == 255
    if im.mode == "P":
        return "transparency" not in im.info
    return False


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        return 1
    src, dst = args[0], args[1]
    quality = int(args[args.index("--quality") + 1]) if "--quality" in args else 85
    dry = "--dry-run" in args
    max_w = int(args[args.index("--max-w") + 1]) if "--max-w" in args else None
    max_h = int(args[args.index("--max-h") + 1]) if "--max-h" in args else None
    if (max_w is None) != (max_h is None):
        print("--max-w 和 --max-h 必须同时给或同时不给")
        return 1

    items = []
    n_jpg = n_keep = n_resize = 0
    before = after = 0

    for name, data in iter_rpa(src):
        if not name.lower().endswith(IMG_EXT):
            items.append((name, data))
            continue
        before += len(data)
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
        except Exception:
            items.append((name, data))
            after += len(data)
            continue

        resized = False
        if max_w and max_h and (im.width > max_w or im.height > max_h):
            scale = min(float(max_w) / im.width, float(max_h) / im.height)
            nw, nh = max(1, int(round(im.width * scale))), max(1, int(round(im.height * scale)))
            im = im.resize((nw, nh), Image.LANCZOS)
            resized = True

        if not is_opaque(im):
            # 有 alpha 就保持 PNG；但降采样后仍要重存才能吃到收益
            if not resized:
                n_keep += 1
                items.append((name, data))
                after += len(data)
                continue
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True, compress_level=9)
            new = buf.getvalue()
            # 降采样过的图**必须**换：解码成本按像素算，文件大一点无所谓
            n_resize += 1
            items.append((name, new))
            after += len(new)
            continue

        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=False)
        new = buf.getvalue()

        # 只有明显更小才换，避免小图反而变大；但降采样过的图必须换
        if (not resized) and len(new) >= len(data) * 0.92:
            n_keep += 1
            items.append((name, data))
            after += len(data)
            continue

        n_jpg += 1
        if resized:
            n_resize += 1
        items.append((name, new))
        after += len(new)

    print("转 JPEG: %d 个 (其中降采样 %d 个)    保留 PNG: %d 个" % (n_jpg, n_resize, n_keep))
    print("图片数据 %.1f MB -> %.1f MB (省 %.1f MB, %.0f%%)" % (
        before / 1e6, after / 1e6, (before - after) / 1e6,
        100.0 * (before - after) / max(1, before)))

    if dry:
        return 0

    write_rpa(dst, items)
    print("已写出 %s (%.2f MB)" % (dst, os.path.getsize(dst) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
