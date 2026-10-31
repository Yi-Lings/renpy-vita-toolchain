# PSV 帧内解剖探针 v8 —— 回答「10 秒到底花在哪」
#
# v6 结论：RENDER(10.16s) ≈ DRAW+FLIP(10.36s)，即 10 秒全在 render_screen()。
# 但 v6 只在「单张解码 >= 0.15s」时打印，所以看不到「很多张各花 0.1s」的情况。
#
# v8 在一帧的范围内累计：
#   - cache.get 调用次数 / 未命中次数 / 总耗时
#   - Text.render 调用次数 / 总耗时
#   - load_texture 调用次数 / 总耗时
# 然后在帧结束时打一行汇总。这样 10 秒的构成一目了然。

init -9 python:

    import time as _psv_t

    _psv = {
        "installed": False,
        "dumped": False,
        "last": _psv_t.time(),
        "win": {},
        "slow": 0.20,
        "sum": 1.5,
        "report": 20.0,
        # 帧内累加器
        "in_render": False,
        "n_get": 0,
        "n_miss": 0,
        "t_get": 0.0,
        "n_text": 0,
        "t_text": 0.0,
        "n_tex": 0,
        "t_tex": 0.0,
    }

    def _psv_note(label, d):
        if d < 0.05:
            return
        v = _psv["win"].get(label)
        if v is None:
            v = _psv["win"][label] = [0.0, 0]
        v[0] += d
        v[1] += 1
        if d >= _psv["slow"]:
            renpy.write_log("PSV SLOW %7.2fs  %s", d, label)

    def _psv_install():
        if _psv["installed"]:
            return
        _psv["installed"] = True

        import renpy.display.core as _core
        from renpy.display import im as _im

        # ---------- render_screen：整帧 + 帧内汇总 ----------
        _rend = renpy.display.render.render_screen

        def _psv_rend(root, width, height):
            _psv["in_render"] = True
            _psv["n_get"] = 0
            _psv["n_miss"] = 0
            _psv["t_get"] = 0.0
            _psv["n_text"] = 0
            _psv["t_text"] = 0.0
            _psv["n_tex"] = 0
            _psv["t_tex"] = 0.0
            t0 = _psv_t.time()
            try:
                return _rend(root, width, height)
            finally:
                d = _psv_t.time() - t0
                _psv["in_render"] = False
                if d >= 0.5:
                    renpy.write_log(
                        "PSV FRAME %6.2fs | get=%d(miss=%d) %.2fs | text=%d %.2fs | tex=%d %.2fs",
                        d, _psv["n_get"], _psv["n_miss"], _psv["t_get"],
                        _psv["n_text"], _psv["t_text"],
                        _psv["n_tex"], _psv["t_tex"])
                _psv_note("RENDER", d)

        renpy.display.render.render_screen = _psv_rend

        # ---------- 图片缓存 ----------
        _cget = _im.cache.get

        def _psv_cget(image, *a, **kw):
            hit = False
            try:
                hit = image in _im.cache.cache
            except Exception:
                pass
            t0 = _psv_t.time()
            try:
                return _cget(image, *a, **kw)
            finally:
                d = _psv_t.time() - t0
                if _psv["in_render"]:
                    _psv["n_get"] += 1
                    _psv["t_get"] += d
                    if not hit:
                        _psv["n_miss"] += 1
                _psv_note("IMG", d)

        _im.cache.get = _psv_cget

        # ---------- 文字排版 ----------
        try:
            from renpy.text.text import Text as _Text
            _trender = _Text.render

            def _psv_trender(self, *a, **kw):
                t0 = _psv_t.time()
                try:
                    return _trender(self, *a, **kw)
                finally:
                    d = _psv_t.time() - t0
                    if _psv["in_render"]:
                        _psv["n_text"] += 1
                        _psv["t_text"] += d
                    # 慢文本：把内容和字号打出来，定位到底是哪个控件
                    if d >= 0.35:
                        try:
                            raw = self.text
                            if isinstance(raw, (list, tuple)):
                                raw = u"".join(
                                    x if isinstance(x, type(u"")) else u"?"
                                    for x in raw)
                            s = raw if isinstance(raw, type(u"")) else unicode(raw)
                            s = s.replace(u"\n", u" ")[:36]
                        except Exception:
                            s = u"?"
                        try:
                            sz = self.style.size
                        except Exception:
                            sz = "?"
                        try:
                            nm = self.style.name
                        except Exception:
                            nm = "?"
                        renpy.write_log("PSV TEXT %6.2fs size=%r style=%r  %r",
                                        d, sz, nm, s)
                    _psv_note("TEXT", d)

            _Text.render = _psv_trender
        except Exception as e:
            renpy.write_log("PSV TEXT probe failed: %r", e)

        # ---------- 纹理上传（draw 在 init 时还没建，延迟安装） ----------
        def _psv_tex_install():
            try:
                dr = renpy.display.draw
                if dr is None or getattr(dr, "_psv_v8", False):
                    return
                _lt = dr.load_texture

                def _psv_lt(surf, *a, **kw):
                    t0 = _psv_t.time()
                    try:
                        return _lt(surf, *a, **kw)
                    finally:
                        d = _psv_t.time() - t0
                        if _psv["in_render"]:
                            _psv["n_tex"] += 1
                            _psv["t_tex"] += d
                        _psv_note("TEX_UPLOAD", d)

                dr.load_texture = _psv_lt
                dr._psv_v8 = True
            except Exception:
                pass

        _psv["tex_install"] = _psv_tex_install

    def _psv_dump_cfg():
        _psv_install()
        try:
            _psv["tex_install"]()
        except Exception:
            pass
        if _psv["dumped"]:
            return
        _psv["dumped"] = True
        try:
            c = renpy.display.im.cache
            renpy.write_log(
                "PSV CFG: limit=%.1fMpx less_mem=%r cache_mb=%r predict=%r "
                "cache_surfaces=%r optimize_bounds=%r",
                c.cache_limit / 1048576.0, renpy.game.less_memory,
                config.image_cache_size_mb, config.predict_statements,
                config.cache_surfaces, config.optimize_texture_bounds)
        except Exception as e:
            renpy.write_log("PSV CFG failed: %r", e)

    def _psv_probe():
        now = _psv_t.time()
        if now - _psv["last"] < _psv["report"]:
            return
        _psv["last"] = now
        # 文字排版缓存尺寸（看有没有撞上 LAYOUT_CACHE_SIZE 被整表清空）
        try:
            import renpy.text.text as _tt
            renpy.write_log(
                "PSV TEXTCACHE size=%r new=%d old=%d vnew=%d",
                _tt.LAYOUT_CACHE_SIZE,
                len(_tt.layout_cache_new), len(_tt.layout_cache_old),
                len(_tt.virtual_layout_cache_new))
        except Exception as e:
            renpy.write_log("PSV TEXTCACHE failed: %r", e)
        items = sorted(_psv["win"].items(), key=lambda kv: -kv[1][0])
        total = 0.0
        for at, v in items:
            total += v[0]
            if v[0] >= _psv["sum"]:
                renpy.write_log("PSV SUM %6.1fs (%3d calls avg %5.0fms)  %s",
                                v[0], v[1], v[0] / v[1] * 1000.0, at)
        if total >= _psv["sum"]:
            renpy.write_log("PSV SUM TOTAL %6.1fs per %.0fs", total, _psv["report"])
        _psv["win"].clear()

    config.start_interact_callbacks.append(_psv_dump_cfg)
    config.periodic_callbacks.append(_psv_probe)


init 999 python:
    try:
        _psv_install()
    except Exception:
        pass
