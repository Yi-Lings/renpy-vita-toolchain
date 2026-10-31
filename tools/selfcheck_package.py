# -*- coding: utf-8 -*-
"""PSV 包体自查工具 —— 按《PSV移植踩坑总结》/RULES.md 逐条校验

用法:
    python selfcheck_package.py --vpk <Full.vpk> [--runtime <Runtime.vpk>]
                                [--ref-common <已知能跑的 renpy/common 目录>]

退出码 0 = 全部通过（警告不算失败），1 = 有硬性失败项。

为什么需要它:
    踩过的每一个坑都对应一条硬性规格（LiveArea 必须 8-bit 索引色、
    param.sfo 必须首条、rpyc 必须预编译……）。靠肉眼看不出来，
    装到 99% 才报 0x8010113D，或者启动卡在 pic0。这个脚本把
    这些规格全部变成可执行的断言。
"""
import argparse
import io
import os
import struct
import sys
import zipfile

try:
    from PIL import Image
except ImportError:
    Image = None

RESULTS = []


def chk(name, ok, detail='', warn_only=False):
    RESULTS.append((bool(ok), name, detail, warn_only))
    tag = 'PASS' if ok else ('WARN' if warn_only else 'FAIL')
    print('%s  %-54s %s' % (tag, name, detail))


def section(title):
    print()
    print('=' * 100)
    print(title)
    print('=' * 100)


# ---------------------------------------------------------------- PNG 头解析
def png_header(data):
    """直接读 IHDR，不依赖 PIL。返回 (w, h, bitdepth, colortype, interlace)"""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    w, h, bd, ct, _, _, il = struct.unpack('>IIBBBBB', data[16:29])
    return w, h, bd, ct, il


# ---------------------------------------------------------------- SFO 解析
def sfo_get(data, key):
    if data[:4] != b'\x00PSF':
        return None
    keyoff, dataoff, count = struct.unpack('<III', data[8:20])
    pos = 20
    for _ in range(count):
        koff, fmt, dlen, dmax, doff = struct.unpack('<HHIII', data[pos:pos + 16])
        pos += 16
        kend = data.index(b'\x00', keyoff + koff)
        k = data[keyoff + koff:kend].decode('ascii', 'replace')
        if k == key:
            raw = data[dataoff + doff:dataoff + doff + dlen]
            return raw.rstrip(b'\x00').decode('ascii', 'replace')
    return None


def check_vpk(vpk, label, is_runtime):
    z = zipfile.ZipFile(vpk)
    infos = z.infolist()
    names = [i.filename for i in infos]
    nameset = set(names)

    # ---------------- 铁律 6：VPK 打包三条 ----------------
    section('铁律 6｜VPK 打包  [%s]' % label)
    chk('6.1 路径全部正斜杠', not any('\\' in n for n in names),
        '反斜杠条目: %d' % sum(1 for n in names if '\\' in n))
    chk('6.2 sce_sys/param.sfo 是第一个条目', names[0] == 'sce_sys/param.sfo',
        '实际首条: %s' % names[0])
    chk('6.3 文件名纯 ASCII', not any(any(ord(c) > 127 for c in n) for n in names),
        '非 ASCII: %d' % sum(1 for n in names if any(ord(c) > 127 for c in n)))
    chk('6.4 全部 DEFLATE 压缩',
        set(i.compress_type for i in infos) == {zipfile.ZIP_DEFLATED},
        '压缩方式: %s' % sorted(set(i.compress_type for i in infos)))
    chk('6.5 无目录条目', not [n for n in names if n.endswith('/')],
        '目录条目: %d' % len([n for n in names if n.endswith('/')]))

    # ---------------- 铁律 5：LiveArea ----------------
    section('铁律 5｜LiveArea 图片必须是 8-bit 索引色  [%s]' % label)
    la = [n for n in names if n.startswith('sce_sys/livearea/contents/')]
    la_png = [n for n in la if n.lower().endswith('.png')]
    chk('5.0 livearea 有图', bool(la_png), [os.path.basename(x) for x in la])
    for n in la_png:
        hdr = png_header(z.read(n))
        base = os.path.basename(n)
        if hdr is None:
            chk('5.x %s 是合法 PNG' % base, False, 'magic 不对')
            continue
        w, h, bd, ct, il = hdr
        chk('5.1 %s 8-bit 索引色 (bitdepth=8 colortype=3)' % base,
            (bd == 8 and ct == 3), 'bd=%d ct=%d %dx%d' % (bd, ct, w, h))
        chk('5.2 %s 非隔行' % base, il == 0, 'interlace=%d' % il)
    chk('5.4 背景图名为 bg.png（不是 bg0.png）',
        'sce_sys/livearea/contents/bg.png' in nameset,
        [os.path.basename(x) for x in la if os.path.basename(x).startswith('bg')])

    # ---------------- 铁律 7：pic0 ----------------
    section('铁律 7｜pic0.png 不是游戏画面  [%s]' % label)
    if 'sce_sys/pic0.png' in nameset:
        data = z.read('sce_sys/pic0.png')
        hdr = png_header(data)
        if hdr:
            w, h, bd, ct, il = hdr
            chk('7.1 pic0.png 尺寸 960x544', (w, h) == (960, 544), '%dx%d' % (w, h))
            chk('7.2 pic0.png 8-bit 索引色', (bd == 8 and ct == 3), 'bd=%d ct=%d' % (bd, ct))
            chk('7.3 pic0.png 非隔行', il == 0, 'interlace=%d' % il)
        chk('7.4 pic0.png 体积合理', len(data) > 20000, '%d B' % len(data))
    else:
        chk('7.1 pic0.png 存在', False, '缺失')

    if 'sce_sys/icon0.png' in nameset:
        hdr = png_header(z.read('sce_sys/icon0.png'))
        if hdr:
            chk('7.5 icon0.png 128x128', (hdr[0], hdr[1]) == (128, 128), '%dx%d' % (hdr[0], hdr[1]))

    # ---------------- 铁律 1：renpy/common 预编译 ----------------
    section('铁律 1｜renpy/common 必须含预编译 .rpyc  [%s]' % label)
    rpy = [n for n in names if n.startswith('renpy/common/') and n.endswith('.rpy')]
    miss = [n for n in rpy if n[:-4] + '.rpyc' not in nameset]
    chk('1.1 每个 .rpy 都有 .rpyc', not miss,
        '缺失 %d: %s' % (len(miss), miss[:4]) if miss else '.rpy=%d' % len(rpy))

    rpym = [n for n in names if n.endswith('.rpym')]
    rpym_miss = [n for n in rpym if n[:-5] + '.rpymc' not in nameset]
    # _compat/ 和 _layout/ 是 Ren'Py 6.x 兼容模块，7.x 游戏不会加载，
    # 已知能跑的参考包里同样没有编译 —— 只警告，不算失败。
    chk('1.2 非兼容类 .rpym 都有 .rpymc',
        not [n for n in rpym_miss if '_compat/' not in n and '_layout/' not in n],
        '兼容类未编译 %d 个（正常）' % len(rpym_miss))

    total = sum(1 for n in names if n.startswith('renpy/common/'))
    chk('1.3 renpy/common 文件数 >= 330', total >= 330, '实际 %d' % total)

    # ---------------- 铁律 2：script_version ----------------
    # Runtime 包本来就不含 game/，跳过
    if not is_runtime:
        section('铁律 2｜script_version.txt 必须干净  [%s]' % label)
        if 'game/script_version.txt' in nameset:
            sv = z.read('game/script_version.txt')
            chk('2.1 体积正常（<=32 B）', len(sv) <= 32, '%d B: %r' % (len(sv), sv))
            try:
                val = eval(sv.decode('ascii').strip())
                chk('2.2 是合法版本元组', isinstance(val, tuple) and len(val) >= 2, repr(val))
            except Exception as e:
                chk('2.2 是合法版本元组', False, repr(e))
        else:
            chk('2.1 script_version.txt 存在', False, '缺失')

    # ---------------- 铁律 8：RPA ----------------
    if not is_runtime:
        section('铁律 8｜RPA 索引可读（prefix 必须是 bytes）  [%s]' % label)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            import rpa_tool
            import tempfile
            for rn in [n for n in names if n.startswith('game/') and n.endswith('.rpa')]:
                tmp = os.path.join(tempfile.gettempdir(), '_sc_check.rpa')
                with open(tmp, 'wb') as f:
                    f.write(z.read(rn))
                try:
                    idx, key = rpa_tool.read_index(tmp)
                    chk('8.1 %s 可读 (%d 条)' % (os.path.basename(rn), len(idx)), True)
                except Exception as e:
                    chk('8.1 %s 可读' % os.path.basename(rn), False, repr(e))
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
        except ImportError:
            chk('8.x rpa_tool 可用', False, '跳过 RPA 检查', warn_only=True)

    # ---------------- 铁律 16：renpy.input ----------------
    if not is_runtime:
        section('铁律 16｜renpy.input() 已替换  [%s]' % label)
        chk('16.1 psv_input.rpyc 在包内', 'game/psv_input.rpyc' in nameset)

    # ---------------- 其他硬性 ----------------
    section('其他硬性检查  [%s]' % label)
    for n in ['eboot.bin', 'renpy.py', 'lib/python27.zip',
              'module/libGLESv2.suprx', 'module/libIMGEGL.suprx',
              'module/libgpu_es4_ext.suprx']:
        chk('* %s 存在' % n, n in nameset)

    # 踩坑总结里记录的原版尺寸（换了会出问题）
    ref_sizes = {'renpy.py': 6722, 'lib/python27.zip': 3919486, 'eboot.bin': 7732057}
    for n, sz in ref_sizes.items():
        if n in nameset:
            actual = z.getinfo(n).file_size
            chk('* %s 是原版尺寸 %d' % (n, sz), actual == sz, '实际 %d' % actual,
                warn_only=True)

    chk('* game/ 里没有 .rpy 源码',
        not [n for n in names if n.startswith('game/') and n.endswith('.rpy')])
    for bad in ['game/psv_diag.rpyc', 'game/cache/', 'game/saves/',
                'traceback.txt', 'log.txt']:
        chk('* 无调试残留 %s' % bad, not [n for n in names if n.startswith(bad)])

    if 'sce_sys/param.sfo' in nameset:
        sfo = z.read('sce_sys/param.sfo')
        tid = sfo_get(sfo, 'TITLE_ID')
        title = sfo_get(sfo, 'TITLE')
        chk('* param.sfo TITLE_ID 可读', bool(tid), 'TITLE_ID=%r' % tid)
        chk('* param.sfo TITLE 可读', bool(title), 'TITLE=%r' % title)

    if is_runtime:
        chk('* Runtime 包不含游戏数据',
            not [n for n in names if n.startswith('game/') and n.endswith('.rpa')],
            'game/ 条目: %d' % len([n for n in names if n.startswith('game/')]))

    return z


def check_common_against_ref(vpk, ref_dir):
    """把包内 renpy/common 与已知能跑的参考目录逐字节比对"""
    section('铁律 21｜renpy/common 必须与运行时一致（逐字节）')
    if not ref_dir or not os.path.isdir(ref_dir):
        chk('21.0 参考目录可用', False, '未提供 --ref-common', warn_only=True)
        return

    z = zipfile.ZipFile(vpk)
    ref = {}
    for root, _, files in os.walk(ref_dir):
        for f in files:
            p = os.path.join(root, f)
            ref[os.path.relpath(p, ref_dir).replace('\\', '/')] = open(p, 'rb').read()

    pkg = {}
    for n in z.namelist():
        if n.startswith('renpy/common/'):
            pkg[n[len('renpy/common/'):]] = z.read(n)

    only_ref = sorted(set(ref) - set(pkg))
    only_pkg = sorted(set(pkg) - set(ref))
    differ = sorted(k for k in set(ref) & set(pkg) if ref[k] != pkg[k])

    chk('21.1 文件集一致', not only_ref and not only_pkg,
        '仅参考 %d / 仅包内 %d' % (len(only_ref), len(only_pkg)))
    chk('21.2 全部文件逐字节一致', not differ,
        '不同 %d 个%s' % (len(differ), (': ' + ', '.join(differ[:5])) if differ else ''))
    chk('21.3 文件数 >= 330', len(pkg) >= 330, '实际 %d' % len(pkg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vpk', required=True, help='Full 包')
    ap.add_argument('--runtime', default=None, help='Runtime 包（可选）')
    ap.add_argument('--ref-common', default=None,
                    help='已知能跑的 renpy/common 目录（可选，强烈建议）')
    a = ap.parse_args()

    if not os.path.exists(a.vpk):
        print('找不到 %s' % a.vpk)
        return 1

    check_vpk(a.vpk, os.path.basename(a.vpk), is_runtime=False)
    if a.runtime and os.path.exists(a.runtime):
        check_vpk(a.runtime, os.path.basename(a.runtime), is_runtime=True)
    if a.ref_common:
        check_common_against_ref(a.vpk, a.ref_common)

    section('汇总')
    fails = [r for r in RESULTS if not r[0] and not r[3]]
    warns = [r for r in RESULTS if not r[0] and r[3]]
    print('总计 %d 项：通过 %d，警告 %d，失败 %d'
          % (len(RESULTS), len(RESULTS) - len(fails) - len(warns), len(warns), len(fails)))
    if fails:
        print('\n失败项：')
        for _, name, detail, _ in fails:
            print('  - %s   %s' % (name, detail))
    if warns:
        print('\n警告项（不阻塞）：')
        for _, name, detail, _ in warns:
            print('  - %s   %s' % (name, detail))
    print()
    print('RESULT: %s' % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
