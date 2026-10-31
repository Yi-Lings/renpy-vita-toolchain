#!/usr/bin/env python3
"""把一个 Ren'Py Vita 移植项目打成可安装的包。

三种产物：

  runtime.vpk   只含运行时（约 14 MB）。安装后气泡出现，但还没有游戏数据。
                可以公开分发 —— 里面没有游戏内容。

  full.vpk      运行时 + 游戏数据（约 125 MB）。真正「一键安装」。
                **只在本地生成，不要公开上传** —— 含受版权保护的游戏素材。

  nonpdrm.zip   NoNpDrm 风格的文件夹包。解压后整个目录拷到 ux0:/app/，
                配合 NoNpDrm 插件使用。同样是本地生成。

用法：
    python build_package.py --build <构建目录> --game <game目录> \
        --out <输出目录> --title-id ANGE00001 --title "Angel Sex Pet" [--runtime-only]
"""
import os
import shutil
import subprocess
import sys
import zipfile


def order_key(rel):
    """VPK 条目顺序：param.sfo 必须第一个。"""
    if rel == "sce_sys/param.sfo":
        return (0, rel)
    if rel.startswith("sce_sys/"):
        return (1, rel)
    if rel == "eboot.bin":
        return (2, rel)
    return (3, rel)


def pack_vpk(src, dst, label=""):
    files = []
    for root, _dirs, names in os.walk(src):
        for n in names:
            p = os.path.join(root, n)
            rel = os.path.relpath(p, src).replace("\\", "/")
            files.append((p, rel))
    files.sort(key=lambda t: order_key(t[1]))

    total = sum(os.path.getsize(p) for p, _ in files)
    print("  打包 %d 个条目, %.1f MB -> %s" % (len(files), total / 1e6, os.path.basename(dst)))

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p, rel in files:
            z.write(p, rel, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)

    with zipfile.ZipFile(dst) as z:
        infos = z.infolist()
        bad_ascii = sum(1 for i in infos if any(ord(c) > 127 for c in i.filename))
        print("    完成 %.2f MB | 首条 %s | 非 ASCII %d | 压缩方式 %s" % (
            os.path.getsize(dst) / 1e6, infos[0].filename, bad_ascii,
            sorted(set(i.compress_type for i in infos))))


def pack_zip_dir(src, dst, root_name):
    """打成带顶层目录的 zip（NoNpDrm 风格）。"""
    files = []
    for d, _dirs, names in os.walk(src):
        for n in names:
            p = os.path.join(d, n)
            rel = os.path.relpath(p, src).replace("\\", "/")
            files.append((p, root_name + "/" + rel))
    total = sum(os.path.getsize(p) for p, _ in files)
    print("  打包 %d 个条目, %.1f MB -> %s" % (len(files), total / 1e6, os.path.basename(dst)))
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p, rel in files:
            z.write(p, rel, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    print("    完成 %.2f MB" % (os.path.getsize(dst) / 1e6))


def main():
    args = sys.argv[1:]

    def arg(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    build = arg("--build")
    game = arg("--game")
    out = arg("--out", os.path.join(os.getcwd(), "dist"))
    title_id = arg("--title-id", "ANGE00001")
    runtime_only = "--runtime-only" in args

    if not build:
        print(__doc__)
        return 1

    os.makedirs(out, exist_ok=True)
    base = os.path.basename(out.rstrip("\\/")) or "package"

    # ---------- 1) 干净运行时 staging ----------
    stage = os.path.join(out, "_stage_" + title_id)
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    shutil.copytree(build, stage)

    gdst = os.path.join(stage, "game")
    os.makedirs(gdst, exist_ok=True)
    # build 目录里可能残留旧 game 数据，清掉
    for n in os.listdir(gdst):
        p = os.path.join(gdst, n)
        if os.path.isfile(p):
            os.remove(p)

    if runtime_only or not game:
        with open(os.path.join(gdst, "PUT_GAME_FILES_HERE.txt"), "w") as f:
            f.write("把 .rpa、script_version.txt、psv_*.rpyc 放在这个目录\n")

    # ---------- 2) runtime VPK（必须在放游戏数据之前打） ----------
    rt = os.path.join(out, "%s_Runtime.vpk" % base)
    pack_vpk(stage, rt)

    # ---------- 3) 放入游戏数据 ----------
    if not runtime_only and game and os.path.isdir(game):
        n_game = 0
        for n in os.listdir(game):
            s = os.path.join(game, n)
            if os.path.isfile(s):
                shutil.copy2(s, os.path.join(gdst, n))
                n_game += 1
        print("  已放入游戏数据: %d 个文件, %.1f MB" % (
            n_game, sum(os.path.getsize(os.path.join(game, n))
                        for n in os.listdir(game)
                        if os.path.isfile(os.path.join(game, n))) / 1e6))

        # ---------- 4) full VPK ----------
        full = os.path.join(out, "%s_Full.vpk" % base)
        pack_vpk(stage, full)

        # ---------- 5) NoNpDrm zip ----------
        npd = os.path.join(out, "%s_NoNpDrm.zip" % base)
        pack_zip_dir(stage, npd, title_id)

    shutil.rmtree(stage, ignore_errors=True)
    print("\n产物在: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
