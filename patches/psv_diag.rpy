# -*- coding: utf-8 -*-
"""PSV 优化探针 v5 —— 只测「真实渲染 / 真实 I/O」，不测空闲

## v4 为什么错（重要）

`PSV STALL` 是两次 `periodic_callback` 的间隔。periodic 由 50ms 的
PERIODIC 定时器驱动，但 interact 循环在等待输入时会阻塞在
`event_wait()`，定时器事件要等玩家按键才被处理。
于是「玩家读了 36 秒台词」会记成「卡顿 36 秒」。

同一份日志里的 `PSV FPS 19.98 (avg 50 ms)` 也是假的：
它只是 periodic 定时器本身的 50ms 周期，不是渲染帧率。

## v5 测什么

| 探针 | 包住谁 | 说明 |
|---|---|---|
| FRAME  | `Interface.draw_screen` | 每帧真正画图的总耗时（布局+GL） |
| RENDER | `render.render_screen` | 布局层：文字排版 / 图片 decode |
| SCREEN | `ScreenDisplayable.update` | 界面重建（菜单第一次出现） |
| LOAD   | `loader.load` | 从 .rpa 读文件（语音 / 图片 / 脚本） |

这些函数 **idle 时都不会被调用**，所以计时干净。

## 输出行

    PSV CFG    ...                   配置 dump（一次）
    PSV FPS    <fps> (<n>/<s>)       引擎窗口内真实帧率（frame_times）
    PSV SLOW   <s> @ <位置>           单次超过 0.35s
    PSV SUM    <s> (<n> calls avg)    20 秒内同一位置累计超过 2s
"""

init -9 python:

    import time as _psv_t

    _psv = {
        "dumped": False,
        "installed": False,
        "last": _psv_t.time(),
        "win": {},
        "tot": {},
        "slow": 0.35,
        "sum": 2.0,
        "report": 20.0,
    }

    def _psv_where():
        try:
            fn, ln = renpy.get_filename_line()
            return "%s:%s" % (fn, ln)
        except Exception:
            return "?"

    def _psv_note(label, d):
        # 先判时间再取位置：get_filename_line() 不便宜，不能每帧调
        if d < 0.02:
            return
        at = label + " @ " + _psv_where()
        for tbl in (_psv["win"], _psv["tot"]):
            v = tbl.get(at)
            if v is None:
                v = tbl[at] = [0.0, 0]
            v[0] += d
            v[1] += 1
        if d >= _psv["slow"]:
            renpy.write_log("PSV SLOW %.2fs  %s", d, at)

    def _psv_install():
        if _psv["installed"]:
            return
        _psv["installed"] = True

        # --- 1) 整帧 ---
        import renpy.display.core as _core
        _o = _core.Interface.draw_screen

        def _f(self, root_widget, fullscreen_video, draw):
            t0 = _psv_t.time()
            try:
                return _o(self, root_widget, fullscreen_video, draw)
            finally:
                _psv_note("FRAME", _psv_t.time() - t0)

        _core.Interface.draw_screen = _f

        # --- 2) 布局（文字排版、图片解码） ---
        _r = renpy.display.render.render_screen

        def _rr(root, width, height):
            t0 = _psv_t.time()
            try:
                return _r(root, width, height)
            finally:
                _psv_note("RENDER", _psv_t.time() - t0)

        renpy.display.render.render_screen = _rr

        # --- 3) 界面重建 ---
        try:
            import renpy.display.screen as _screen
            _u = _screen.ScreenDisplayable.update

            def _uu(self, *a, **kw):
                t0 = _psv_t.time()
                try:
                    return _u(self, *a, **kw)
                finally:
                    d = _psv_t.time() - t0
                    if d >= 0.10:
                        _psv_note("SCREEN %r" % (getattr(self, "screen_name", "?"),), d)

            _screen.ScreenDisplayable.update = _uu
        except Exception as e:
            renpy.write_log("PSV SCREEN probe failed: %r", e)

        # --- 4) 文件读取（.rpa 里的语音/图片/脚本） ---
        try:
            _l = renpy.loader.load

            def _ll(name, *a, **kw):
                t0 = _psv_t.time()
                try:
                    return _l(name, *a, **kw)
                finally:
                    d = _psv_t.time() - t0
                    if d >= 0.10:
                        renpy.write_log("PSV LOAD %.2fs  %s", d, name)

            renpy.loader.load = _ll
        except Exception as e:
            renpy.write_log("PSV LOAD probe failed: %r", e)

    def _psv_dump_cfg():
        _psv_install()
        if _psv["dumped"]:
            return
        _psv["dumped"] = True
        try:
            c = renpy.display.im.cache
            renpy.write_log(
                "PSV CFG: cache_mb=%r cache_size=%r limit=%rMpx sw=%r sh=%r "
                "less_mem=%r drawable_text=%r",
                config.image_cache_size_mb, config.image_cache_size,
                c.cache_limit / 1048576.0, config.screen_width,
                config.screen_height, renpy.game.less_memory,
                config.drawable_resolution_text)
        except Exception as e:
            renpy.write_log("PSV CFG failed: %r", e)

    def _psv_probe():
        now = _psv_t.time()
        if now - _psv["last"] < _psv["report"]:
            return
        _psv["last"] = now

        try:
            ft = renpy.display.interface.frame_times
            if len(ft) >= 5:
                span = ft[-1] - ft[0]
                if span > 0:
                    renpy.write_log("PSV FPS %.1f (%d frames / %.1fs)",
                                    (len(ft) - 1) / span, len(ft), span)
        except Exception as e:
            renpy.write_log("PSV FPS failed: %r", e)

        items = sorted(_psv["win"].items(), key=lambda kv: -kv[1][0])
        total = 0.0
        for at, v in items:
            total += v[0]
            if v[0] >= _psv["sum"]:
                renpy.write_log("PSV SUM %.1fs (%d calls avg %.0fms)  %s",
                                v[0], v[1], v[0] / v[1] * 1000.0, at)
        if total >= _psv["sum"]:
            renpy.write_log("PSV SUM TOTAL %.1fs per %.0fs", total, _psv["report"])
        _psv["win"].clear()

    config.start_interact_callbacks.append(_psv_dump_cfg)
    config.periodic_callbacks.append(_psv_probe)


init 999 python:
    try:
        _psv_install()
    except Exception:
        pass
