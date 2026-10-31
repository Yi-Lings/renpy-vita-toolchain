#!/usr/bin/env python3
"""给带「首发联网上报」的 Ren'Py 游戏打跳过补丁。

背景（2026-10-31 实测）：
  相当一部分 Steam 版 Ren'Py 游戏在 splashscreen.rpyc 里塞了一段

      init -3 python:
          persistent.jp_installed = False
          if not persistent.data_checked:
              import requests
              userdata = requests.get('http://ipinfo.io/json').json()
              useranalytics = requests.post('http://<厂商服务器>/...', data=userdata)
              persistent.jp_ipcountry = userdata['country']
              persistent.data_checked = True

  这是发行商的内嵌遥测：首次启动同步发 HTTP 请求。

  在 PS Vita 上必然失败：
    * 宿主 python27.zip 里没有 _ssl / certifi，requests 用不了 TLS；
    * app0: 只读，写不了缓存；
    * 抛的是未捕获异常，直接把 init 阶段打死。

  日志表现：停在 `Importing _renpysteam` 之后，没有
  `Set script version to:`（如果 script_version 也被污染）或
  有 `Set script version to:` 但紧接着没有 `Running init code`。

修复：
  init -10 的优先级低于所有已知的上报块（都是 -3），先把
  persistent.data_checked 置 True，让上报块里的 if 直接跳过。
  不需要改动游戏原始 .rpa。

用法：
    python fix_telemetry.py <游戏目录>            # 只检测
    python fix_telemetry.py <游戏目录> --write    # 生成 psv_skip_telemetry.rpyc
"""
import os
import struct
import subprocess
import sys
import zlib

# 只认真正的联网上报特征。别用 'cherrykiss' —— 那家公司的
# screens.rpyc 里有 OpenURL("https://cherrykissgames.com")，会误报。
PROBES = (
    b"ipinfo.io",
    b"pipedream",
    b"stickyrice.work",
    b"users.cherrykiss.club",
    b"requests.get(",
    b"requests.post(",
)

GUARD_SOURCE = """init -10 python:
    persistent.data_checked = True
"""


# ------------------------------------------------------------------ rpa
def read_index(path):
    with open(path, "rb") as f:
        header = f.readline().split()
        if not header or not header[0].startswith(b"RPA-"):
            return None
        key = int(header[2], 16)
        f.seek(int(header[1], 16))
        raw = zlib.decompress(f.read())
    return key, parse_pickle_index(raw)


def parse_pickle_index(raw):
    """极简 protocol-0/2 pickle 解析：只取 {name: [(off, len, prefix)]}。"""
    import pickle

    try:
        obj = pickle.loads(raw, encoding="latin1")
    except TypeError:
        obj = pickle.loads(raw)
    out = {}
    for name, v in obj.items():
        if isinstance(name, bytes):
            name = name.decode("latin-1")
        out[name] = v
    return out


def iter_rpa(path):
    key, index = read_index(path)
    with open(path, "rb") as f:
        for name, chunks in index.items():
            off, ln, _prefix = chunks[0]
            f.seek(off ^ key)
            yield name, f.read(ln ^ key)


def rpyc_payload(blob):
    """RENPY RPC2 -> 第一个 slot 的 pickle bytes；不是 rpyc 就返回 b''。"""
    if not blob.startswith(b"RENPY RPC2"):
        return b""
    pos = 10
    slots = []
    try:
        while True:
            slot, start, length = struct.unpack("<III", blob[pos:pos + 12])
            if slot == 0:
                break
            slots.append((slot, start, length))
            pos += 12
    except Exception:
        return b""
    if not slots:
        return b""
    try:
        return zlib.decompress(blob[slots[0][1]:slots[0][1] + slots[0][2]])
    except Exception:
        return b""


def scan_game(game_dir):
    hits = []
    for fn in sorted(os.listdir(game_dir)):
        if not fn.endswith(".rpa"):
            continue
        path = os.path.join(game_dir, fn)
        try:
            for name, blob in iter_rpa(path):
                if not name.endswith(".rpyc"):
                    continue
                data = rpyc_payload(blob)
                if any(p in data for p in PROBES):
                    hits.append((fn, name))
        except Exception as exc:
            print("    !! 读不了 %s: %s" % (fn, exc))
    return hits


# ------------------------------------------------------------------ rpyc
def build_rpyc(rpy_file, out_rpyc, sdk):
    """用 Ren'Py SDK 把 .rpy 编译成 .rpyc（版本常量才和运行时一致）。"""
    renpy_exe = os.path.join(sdk, "renpy.exe")
    if not os.path.exists(renpy_exe):
        raise SystemExit("找不到 %s，请先下载 Ren'Py SDK" % renpy_exe)

    project = os.path.join(os.path.dirname(out_rpyc), "_compile_tmp")
    game = os.path.join(project, "game")
    os.makedirs(game, exist_ok=True)

    name = os.path.basename(rpy_file)
    with open(rpy_file, "r", encoding="utf-8") as f:
        text = f.read()
    with open(os.path.join(game, name), "w", encoding="utf-8") as f:
        f.write(text)

    subprocess.run([renpy_exe, project, "lint"], capture_output=True, timeout=600)

    built = os.path.join(game, name[:-4] + ".rpyc" if name.endswith(".rpy") else name + "c")
    if not os.path.exists(built):
        raise SystemExit("编译失败，没有产出 %s" % built)
    with open(built, "rb") as f:
        data = f.read()
    with open(out_rpyc, "wb") as f:
        f.write(data)
    return out_rpyc


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    root = sys.argv[1]
    write = "--write" in sys.argv[2:]
    sdk = None
    for i, a in enumerate(sys.argv):
        if a == "--sdk" and i + 1 < len(sys.argv):
            sdk = sys.argv[i + 1]

    game_dir = os.path.join(root, "game") if os.path.isdir(os.path.join(root, "game")) else root
    print("扫描:", game_dir)

    hits = scan_game(game_dir)
    if not hits:
        print("  没有发现联网上报代码")
        return 0

    print("  命中 %d 处：" % len(hits))
    for fn, name in hits:
        print("     %-16s %s" % (fn, name))

    guard = os.path.join(game_dir, "psv_skip_telemetry.rpyc")
    if not write:
        print("\n（只检测；加 --write 才会生成 %s）" % os.path.basename(guard))
        return 0

    if os.path.exists(guard):
        print("\n  已存在:", guard)
        return 0

    if not sdk:
        print("\n  需要 --sdk <Ren'Py SDK 目录> 才能编译 .rpyc")
        return 2

    tmp_rpy = os.path.join(game_dir, "_psv_skip_telemetry.rpy")
    with open(tmp_rpy, "w", encoding="utf-8") as f:
        f.write(GUARD_SOURCE)
    try:
        build_rpyc(tmp_rpy, guard, sdk)
    finally:
        os.remove(tmp_rpy)
        tmp_project = os.path.join(game_dir, "_compile_tmp")
        if os.path.isdir(tmp_project):
            import shutil

            shutil.rmtree(tmp_project, ignore_errors=True)

    print("\n  已生成:", guard, os.path.getsize(guard), "字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
