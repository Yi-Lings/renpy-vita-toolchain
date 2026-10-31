#!/usr/bin/env python3
"""Extract specific files out of a Ren'Py .rpa archive."""
import os
import pickle
import sys
import zlib


def load(path):
    with open(path, "rb") as f:
        p = f.readline().split()
        key = int(p[2], 16)
        f.seek(int(p[1], 16))
        return key, pickle.loads(zlib.decompress(f.read()), encoding="latin1")


def main(rpa, outdir, wanted):
    key, idx = load(rpa)
    os.makedirs(outdir, exist_ok=True)
    with open(rpa, "rb") as f:
        for name, value in idx.items():
            if isinstance(name, bytes):
                name = name.decode("latin1")
            if name not in wanted:
                continue
            off, ln, prefix = value[0]
            f.seek(off ^ key)
            data = f.read(ln ^ key)
            if prefix:
                data = (prefix.encode("latin1") if isinstance(prefix, str) else prefix) + data
            dst = os.path.join(outdir, os.path.basename(name))
            open(dst, "wb").write(data)
            print(f"  extracted {name} -> {dst} ({len(data)} bytes)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], set(sys.argv[3:]))
