#!/usr/bin/env python3
"""Pack a .vpk matching the layout of known-working homebrew VPKs.

Differences from a naive zip that matter in practice:
  * sce_sys/param.sfo must be the *first* entry
  * every entry is DEFLATE-compressed (method 8), never STORED
  * no non-ASCII file names inside the archive
"""
import os
import sys
import zipfile


def order_key(rel):
    if rel == "sce_sys/param.sfo":
        return (0, rel)
    if rel.startswith("sce_sys/"):
        return (1, rel)
    if rel == "eboot.bin":
        return (2, rel)
    return (3, rel)


def main(src, dst):
    files = []
    for root, _, names in os.walk(src):
        for n in names:
            p = os.path.join(root, n)
            rel = os.path.relpath(p, src).replace("\\", "/")
            files.append((p, rel))
    files.sort(key=lambda t: order_key(t[1]))

    total = sum(os.path.getsize(p) for p, _ in files)
    print(f"packing {len(files)} entries, {total/1024/1024:.1f} MB -> {os.path.basename(dst)}", flush=True)

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p, rel in files:
            z.write(p, rel, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)

    with zipfile.ZipFile(dst) as z:
        infos = z.infolist()
        print(f"done: {os.path.getsize(dst)/1024/1024:.2f} MB")
        print(f"  first entry : {infos[0].filename}")
        print(f"  compress    : {sorted(set(i.compress_type for i in infos))}")
        print(f"  non-ascii   : {sum(1 for i in infos if any(ord(c) > 127 for c in i.filename))}")
        names = z.namelist()
        print(f"  backslash   : {sum(1 for n in names if chr(92) in n)}")
        for w in ("sce_sys/param.sfo", "eboot.bin"):
            print(f"  {w}: {'OK' if w in names else 'MISSING'}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
