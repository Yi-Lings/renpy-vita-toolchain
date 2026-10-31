#!/usr/bin/env python3
"""Inspect Ren'Py .rpa archives without needing Ren'Py itself.

Reports: file count, total size, video presence, and image resolution
histogram (read straight from PNG/JPEG headers inside the archive).
"""
import io
import os
import pickle
import struct
import sys
import zlib


def read_index(path):
    with open(path, "rb") as f:
        header = f.readline()
        parts = header.split()
        magic = parts[0].decode("latin-1")
        if magic.startswith("RPA-3"):
            offset = int(parts[1], 16)
            key = int(parts[2], 16)
            f.seek(offset)
            index = pickle.loads(zlib.decompress(f.read()), encoding="latin1")
            return "3", key, index
        if magic.startswith("RPA-2"):
            offset = int(parts[1], 16)
            f.seek(offset)
            index = pickle.loads(zlib.decompress(f.read()), encoding="latin1")
            return "2", 0, index
        raise ValueError("unknown rpa magic: %r" % magic)


def entries(index, key):
    """Yield (name, [(start, length, prefix), ...])."""
    for name, value in index.items():
        if isinstance(name, bytes):
            name = name.decode("latin-1")
        out = []
        if isinstance(value, list) and value and isinstance(value[0], tuple):
            for item in value:
                # This packer XORs *both* the offset and the length with the
                # header key (verified against real archives).
                if len(item) == 3:
                    off, ln, prefix = item
                    out.append(((off ^ key), (ln ^ key), prefix))
                else:
                    off, ln = item
                    out.append(((off ^ key), (ln ^ key), b""))
        yield name, out


def image_size(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    if data[:2] == b"\xff\xd8":
        i = 2
        n = len(data)
        while i < n - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
        return None
    return None


def main(path):
    ver, key, index = read_index(path)
    items = list(entries(index, key))
    print(f"### {os.path.basename(path)}   format=RPA-{ver}   files={len(items)}")
    with open(path, "rb") as f:
        total = 0
        vids = []
        res = {}
        biggest = []
        for name, chunks in items:
            size = sum(c[1] for c in chunks)
            total += size
            ext = os.path.splitext(name)[1].lower()
            if ext in (".webm", ".mp4", ".ogv", ".avi", ".mkv", ".mpg", ".mpeg", ".mov"):
                vids.append((name, size))
            elif ext in (".png", ".jpg", ".jpeg", ".webp"):
                try:
                    start, ln, prefix = chunks[0]
                    f.seek(start)
                    head = f.read(min(65536, ln))
                    if prefix:
                        head = prefix + head
                    dim = image_size(head)
                    if dim:
                        res[dim] = res.get(dim, 0) + 1
                except Exception:
                    pass
            if size > 2 * 1024 * 1024:
                biggest.append((size, name))
    print(f"    总解压大小: {total/1024/1024:.1f} MB")
    if vids:
        print(f"    !! 视频文件 {len(vids)} 个 (Vita 版无法播放):")
        for n, s in sorted(vids, key=lambda x: -x[1])[:6]:
            print(f"       {s/1024/1024:8.1f} MB  {n}")
    else:
        print("    视频文件: 无")
    if res:
        print("    图片分辨率分布 (top 8):")
        for (w, h), c in sorted(res.items(), key=lambda x: -x[1])[:8]:
            print(f"       {w}x{h}  x{c}")
    if biggest:
        print("    最大文件 (top 5):")
        for s, n in sorted(biggest, reverse=True)[:5]:
            print(f"       {s/1024/1024:8.1f} MB  {n}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        try:
            main(p)
        except Exception as e:
            print(f"### {p}  ERROR: {e}")
        print()
