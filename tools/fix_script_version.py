#!/usr/bin/env python3
"""清掉汉化组塞进 script_version.txt 的水印。

背景（2026-10-31 实测）：
  miel 社这一批"SEEACG"汉化版，把版权水印直接追加到了
  game/script_version.txt 里：

      (7, 3, 5)\r\n
      \r\n
      更多资源:SEEACG.COM      <- GBK 字节

  Ren'Py 的 00compat.rpy 用 ast.literal_eval() 读这个文件：

      script_version = ast.literal_eval(script_version)
      config.script_version = script_version
      renpy.write_log("Set script version to: %r", ...)

  多出来的中文行让 literal_eval 直接抛异常，而外面是 `except: pass`，
  于是：

    1. 日志里 **不会** 出现 "Set script version to:" ——
       很多人（包括我们）会误以为崩在那一行之前，其实只是这行没打出来；
    2. `config.script_version` 保持 None，
       整个 renpy 兼容层 (config.script_version and ...) 全部被跳过，
       老脚本用新引擎跑就会走到未打补丁的代码路径上。

用法：
    python fix_script_version.py <game目录>            # 只报告
    python fix_script_version.py <game目录> --write    # 就地修正
"""
import ast
import io
import os
import sys


def clean(path):
    raw = open(path, "rb").read()
    text = raw.decode("utf-8", "replace")
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    try:
        value = ast.literal_eval(first)
    except Exception:
        return None, raw, "首行不是合法的 tuple"

    if not isinstance(value, tuple):
        return None, raw, "首行不是 tuple"

    return value, raw, None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    root = sys.argv[1]
    write = "--write" in sys.argv[2:]

    targets = []
    direct = os.path.join(root, "script_version.txt")
    nested = os.path.join(root, "game", "script_version.txt")
    if os.path.isfile(direct):
        targets.append(direct)
    if os.path.isfile(nested):
        targets.append(nested)

    if not targets:
        print("没找到 script_version.txt:", root)
        return 2

    rc = 0
    for path in targets:
        value, raw, err = clean(path)
        print("==", path)
        print("   原始 %d 字节: %r" % (len(raw), raw))
        if err:
            print("   !!", err)
            rc = 1
            continue

        want = "(%d, %d, %d)\n" % value[:3]
        # 干净 = 整个文件能被 literal_eval 解析成三元组。
        # （Ren'Py 是拿整个文件内容去 literal_eval 的，不是只读第一行，
        #   所以水印追加在第二行照样会炸）
        try:
            whole = ast.literal_eval(raw.decode("utf-8"))
            clean = isinstance(whole, tuple) and len(whole) >= 3
        except Exception:
            clean = False
        print("   解析结果: %r   干净=%s" % (value, clean))
        dirty = not clean

        if dirty and write:
            with io.open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(want)
            print("   已改写 ->", repr(want))

    if not write:
        print("\n（只报告；加 --write 才会改）")
    return rc


if __name__ == "__main__":
    sys.exit(main())
