#!/usr/bin/env python3
"""重打包 Ren'Py .rpa（兼容 Vita 的 Python 2.7 运行时）。

关键点（2026-10-31 实测，之前一直失败的原因）：

1. **index 里的 prefix 必须用 `b''`，不能用 `''`**
   Ren'Py 的 `loader.SubFile.__init__` 把 prefix 存在 `self.start`，
   `read()` 里做 `rv1 = self.start[...] + 数据`。
   Python 3 的 `str ''` pickle 后在 Py2 里是 `u''`，
   `u'' + '\x89PNG...'` 会走 unicode 解码 → 二进制被破坏。
   用 `bytes b''` pickle 后 Py2 读出来是 `str ''`，一切正常。

2. **offset 和 length 都要 XOR key**
   RPA-3.0 标准只 XOR offset，但这个合集（Cherry Kiss / Miel）
   的包把 length 也 XOR 了。Ren'Py 的 read_index 两个都 XOR，
   所以照做即可。

3. **index 用 pickle protocol 2**，Py2 能直接读。

用法：
    python rpa_tool.py list   <archive.rpa>
    python rpa_tool.py extract <archive.rpa> <outdir>
    python rpa_tool.py pack    <outdir> <archive.rpa>
    python rpa_tool.py filter  <in.rpa> <out.rpa> --drop tl/en,tl/es
"""
import os
import pickle
import struct
import sys
import zlib

KEY = 0x42424242


# ------------------------------------------------------------------ read
def read_index(path):
    with open(path, "rb") as f:
        head = f.readline().split()
        if not head or not head[0].startswith(b"RPA-"):
            raise ValueError("不是 RPA 文件: %s" % path)
        key = int(head[2], 16)
        f.seek(int(head[1], 16))
        idx = pickle.loads(zlib.decompress(f.read()), encoding="latin1")
    out = {}
    for name, chunks in idx.items():
        if isinstance(name, bytes):
            name = name.decode("latin-1")
        out[name] = [(off ^ key, ln ^ key, pre) for off, ln, pre in chunks]
    return out, key


def iter_rpa(path):
    idx, key = read_index(path)
    with open(path, "rb") as f:
        for name, chunks in idx.items():
            data = b"".join(
                (lambda o, l: (f.seek(o), f.read(l))[1])(off, ln)
                for off, ln, _pre in chunks
            )
            yield name, data


def read_rpa(path):
    return dict(iter_rpa(path))


# ------------------------------------------------------------------ write
def write_rpa(path, items, key=KEY):
    """items: iterable of (name, bytes)"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(b"RPA-3.0 " + b"0" * 16 + b" " + (b"%08x" % key) + b"\n")
        idx = {}
        for name, data in items:
            off = f.tell()
            f.write(data)
            # b'' 不是 ''：见文件头注释第 1 条
            idx[name] = [(off ^ key, len(data) ^ key, b"")]
        idx_off = f.tell()
        f.write(zlib.compress(pickle.dumps(idx, protocol=2)))
        f.seek(0)
        f.write(b"RPA-3.0 " + (b"%016x" % idx_off) + b" " + (b"%08x" % key) + b"\n")
    os.replace(tmp, path)


# ------------------------------------------------------------------ cli
def _extract(archive, outdir):
    n = 0
    for name, data in iter_rpa(archive):
        p = os.path.join(outdir, name.replace("/", os.sep))
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        n += 1
    print("extracted %d files -> %s" % (n, outdir))


def _pack(src, archive):
    items = []
    for dp, _dn, fns in os.walk(src):
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, src).replace(os.sep, "/")
            with open(full, "rb") as f:
                items.append((rel, f.read()))
    write_rpa(archive, items)
    print("packed %d files -> %s (%.2f MB)" % (len(items), archive, os.path.getsize(archive) / 1e6))


def _filter(src, dst, drop):
    prefixes = tuple(drop)
    kept = dropped = 0
    saved = 0
    out = []
    for name, data in iter_rpa(src):
        if name.startswith(prefixes):
            dropped += 1
            saved += len(data)
            continue
        out.append((name, data))
        kept += 1
    write_rpa(dst, out)
    print("kept %d, dropped %d (%.1f KB)" % (kept, dropped, saved / 1024.0))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "list":
        idx, key = read_index(sys.argv[2])
        print("%d entries, key=0x%08x" % (len(idx), key))
        for name in sorted(idx)[:80]:
            print("  ", name)
    elif cmd == "extract":
        _extract(sys.argv[2], sys.argv[3])
    elif cmd == "pack":
        _pack(sys.argv[2], sys.argv[3])
    elif cmd == "filter":
        drop = []
        if "--drop" in sys.argv:
            drop = sys.argv[sys.argv.index("--drop") + 1].split(",")
        _filter(sys.argv[2], sys.argv[3], drop)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
