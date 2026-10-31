# 方向 1：把字体整块读进内存，不再逐字形流式读 .rpa
#
# ## 问题
#
# Ren'Py 用 FT_OPEN_STREAM 把字体交给 FreeType，所有字体数据都走一个
# Python 回调（renpy/text/ftfont.pyx:123）：
#
#     cdef unsigned long io_func(FT_Stream stream, unsigned long offset, ...):
#         f = face.f                    # 字体文件对象
#         if face.offset != offset:
#             f.seek(offset)            # ← 每次 seek
#         buf = f.read(count)           # ← 每次 read
#
# 而 face.f 是 renpy.loader.load() 返回的、**.rpa 里的 SubFile**
# （loader.py:475，read() 内部会 open(文件名) + f.read()）。
#
# 于是每读一个字形轮廓 = Python 回调 + seek + 读一次 14.9 MB 的 RPA。
# CFF 字体读一个字形要读多处，一句 32 字台词 = 100~160 次磁盘 I/O。
# Vita 存储卡单次 seek+read 5~10 ms → 0.5~1.6 秒，与实测吻合。
#
# 实测证据（Angel Sex Pet）：
#     PSV TEXT 0.56s size=16 '1.3.2'          ← 5 个 ASCII 字符
#     PSV TEXT 2.39s size=24 '开始游戏'        ← 4 个汉字
# 同一字体在 PC 上光栅化只要 0.039 ms/字，差 50~300 倍 —— 只能是 I/O。
#
# ## 做法
#
# 包装 renpy.loader.load：字体类文件（.ttf/.otf/.ttc/.otc）整块读成
# bytes，返回 io.BytesIO。这样 io_func 里的 f.seek()/f.read() 变成
# 内存拷贝，不再碰存储卡。
#
# load_face 对文件只做 seek(0,2) / tell() / seek(0,0)，BytesIO 全支持。
#
# ## 代价
#
# 字体常驻内存：3 个 CJK 字体各 4.1 MB + fa.ttf 0.38 MB
# + DejaVu 两档 1.4 MB ≈ 15 MB。Vita 约 330 MB 可用，可接受。
# 每个字体只读一次（load_face 有 face_cache）。

init -9 python:

    import io
    import renpy.loader as _psv_ld

    _psv_orig_load = _psv_ld.load
    _PSV_FONT_EXT = (".ttf", ".otf", ".ttc", ".otc")

    _psv_font_stats = { "n": 0, "bytes": 0, "fail": 0 }

    def _psv_load(name, *args, **kwargs):
        rv = _psv_orig_load(name, *args, **kwargs)

        # 只处理字体；其它文件保持原样（SubFile 的语义别动）
        try:
            low = name.lower()
        except Exception:
            return rv

        if not low.endswith(_PSV_FONT_EXT):
            return rv

        try:
            data = rv.read()
        except Exception as e:
            # 读失败就把原对象还回去，别把字体搞坏
            _psv_font_stats["fail"] += 1
            renpy.write_log("PSV FONT MEM failed %r: %r", name, e)
            try:
                rv.close()
            except Exception:
                pass
            return _psv_orig_load(name, *args, **kwargs)

        try:
            rv.close()
        except Exception:
            pass

        _psv_font_stats["n"] += 1
        _psv_font_stats["bytes"] += len(data)
        renpy.write_log("PSV FONT MEM %s  %.2f MB -> BytesIO",
                        name, len(data) / 1048576.0)
        return io.BytesIO(data)

    _psv_ld.load = _psv_load

    def _psv_font_report():
        try:
            renpy.write_log("PSV FONT MEM total: %d fonts, %.2f MB",
                            _psv_font_stats["n"],
                            _psv_font_stats["bytes"] / 1048576.0)
        except Exception:
            pass

    config.start_interact_callbacks.append(_psv_font_report)
