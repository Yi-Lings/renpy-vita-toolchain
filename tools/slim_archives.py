# -*- coding: utf-8 -*-
"""归档瘦身：删掉 rpa 里运行时永远不会读的死重

删除项及依据（全部有源码/实测支撑，不是猜）：

1. `.rpy` 源码
   `renpy/script.py:238-262` 的 `scan_script_files()`：
       if fn.endswith(".rpy"):
           if dir is None:          # 来自归档
               continue             # ← 直接跳过
   归档里的 `.rpy` 从不参与加载、不做 digest 校验、不会被解析。
   而 `script.py:699-710` 也写明「从归档加载时只可能是 .rpyc」。
   → 纯占体积。

2. `python-packages/`（requests / urllib3 / chardet / idna / certifi）
   游戏里唯一的用途是 `splashscreen.rpy:5-8` 的联网上报：
       import requests
       userdata = requests.get('http://ipinfo.io/json').json()
       requests.post('http://ent943y5tpj9hth.m.pipedream.net', ...)
   这段被 `psv_skip_telemetry.rpy`（init -10 设 persistent.data_checked = True）
   挡住 —— 它在 `init -3` 之前执行，条件永远为假，`import requests` 永不执行。
   → 纯占体积。

3. `python-packages/bin/chardetect.exe` —— Windows 二进制，Vita 上无意义。

用法:
    python slim_archives.py --rpa game/archive.rpa --rpa game/dlc_japanese.rpa
    python slim_archives.py --rpa X.rpa --dry-run      # 只看会删什么
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpa_tool

# 默认删除规则
DROP_EXTS = ('.rpy',)                      # 归档内永不加载
DROP_PREFIXES = ('python-packages/',)      # 上报库，已被补丁挡住


def should_drop(name):
    low = name.lower()
    if low.endswith(DROP_EXTS):
        return 'rpy-source'
    for p in DROP_PREFIXES:
        if name.startswith(p):
            return 'python-packages'
    if low.endswith('.exe'):
        return 'windows-binary'
    return None


def slim(path, dry_run=False):
    # 先流式读出全部数据（iter_rpa 的生成器会在耗尽时关闭文件句柄），
    # 再原地重写 —— write_rpa 内部用 path+'.tmp' + os.replace 保证原子性。
    keep = []
    drop = []
    for name, data in rpa_tool.iter_rpa(path):
        why = should_drop(name)
        if why:
            drop.append((name, len(data), why))
        else:
            keep.append((name, data))

    total = len(keep) + len(drop)
    saved = sum(s for _, s, _ in drop)
    print('%s' % os.path.basename(path))
    print('  原 %d 条 → 保留 %d 条，删除 %d 条，省 %.2f MB'
          % (total, len(keep), len(drop), saved / 1048576.0))

    from collections import Counter
    c = Counter(w for _, _, w in drop)
    for why, n in c.most_common():
        sz = sum(s for _, s, w in drop if w == why)
        print('    %-18s %4d 条  %8.2f MB' % (why, n, sz / 1048576.0))

    if dry_run:
        print('  (dry-run，未写盘)')
        return saved

    if not drop:
        print('  无需处理')
        return 0

    _idx, key = rpa_tool.read_index(path)
    before = os.path.getsize(path)
    rpa_tool.write_rpa(path, keep, key)
    after = os.path.getsize(path)
    print('  %.2f MB → %.2f MB（省 %.2f MB）'
          % (before / 1048576.0, after / 1048576.0, (before - after) / 1048576.0))
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rpa', action='append', required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    total = 0
    for p in a.rpa:
        if not os.path.exists(p):
            print('跳过（不存在）: %s' % p)
            continue
        total += slim(p, a.dry_run)
        print()
    print('合计省 %.2f MB' % (total / 1048576.0))


if __name__ == '__main__':
    main()
