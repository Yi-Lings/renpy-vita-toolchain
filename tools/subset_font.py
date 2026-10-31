#!/usr/bin/env python3
"""把 CJK 字体裁剪成只用得到的字符，给 Vita 省内存和加载时间。

背景（2026-10-31）：
  Angel Sex Pet 的 gui_resource.rpa 一共 53 MB，其中 51 MB 是三个
  SourceHanSansSC 全量字体（每个 ~17 MB，含 4 万多个字形）。
  PS Vita 只有约 330 MB 可用内存，三个字体就吃掉 1/6。

做法：
  保留字符 = 游戏脚本实际用到的字符 ∪ GB2312 全字库 ∪ ASCII ∪ Latin-1
  用 pyftsubset 裁掉其余字形。

  GB2312 那一层是为了玩家名输入之类的动态文本——只按脚本提取太冒险，
  少一个字就是一个方框。

用法：
    python subset_font.py <输入字体> <输出字体> [--charset charset.txt]
"""
import os
import sys


def gb2312_chars():
    """GB2312 全部可编码字符（6763 个汉字 + 符号）。"""
    out = set()
    for hi in range(0xA1, 0xFF):
        for lo in range(0xA1, 0xFF):
            try:
                out.add(bytes([hi, lo]).decode("gb2312"))
            except Exception:
                pass
    return out


def base_chars():
    """ASCII + Latin-1 + 常用标点。"""
    out = set(chr(c) for c in range(0x20, 0x7F))
    out |= set(chr(c) for c in range(0xA0, 0x180))
    out |= set("‘’“”–—…·　、。！？；：（）《》【】")
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    src, dst = sys.argv[1], sys.argv[2]
    chars = base_chars()
    chars |= gb2312_chars()

    if "--charset" in sys.argv:
        p = sys.argv[sys.argv.index("--charset") + 1]
        if os.path.exists(p):
            chars |= set(open(p, encoding="utf-8").read())
            print("额外字符集: %s" % p)

    chars = {c for c in chars if c.strip() or c == " "}
    text = "".join(sorted(chars))
    print("目标字符数: %d" % len(chars))

    from fontTools import subset

    args = [
        src,
        "--output-file=" + dst,
        "--text=" + text,
        "--layout-features=*",
        "--drop-tables+=DSIG",
        "--no-hinting" if "--no-hinting" in sys.argv else "--hinting",
    ]
    args = [a for a in args if a not in ("--hinting",)]
    subset.main(args)

    before = os.path.getsize(src)
    after = os.path.getsize(dst)
    print("%-40s %7.1f MB -> %6.1f MB  (省 %.0f%%)" % (
        os.path.basename(src), before / 1e6, after / 1e6,
        100.0 * (before - after) / before))
    return 0


if __name__ == "__main__":
    sys.exit(main())
