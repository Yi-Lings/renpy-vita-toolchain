init -9 python:
    # 诊断 v4
    #  - 用 renpy.get_filename_line() 取真正的语句位置（v3 用的 API 拿不到）
    #  - 第一次调用时 dump 相关配置，确认 image_cache 到底是多少

    import time as _psv_t

    _psv_s = {
        "last": _psv_t.time(),
        "n": 0,
        "acc": 0.0,
        "worst": 0.0,
        "worst_at": "",
        "dumped": False,
    }

    def _psv_where():
        try:
            fn, ln = renpy.get_filename_line()
            return "%s:%s" % (fn, ln)
        except Exception:
            return "?"

    def _psv_dump_cfg():
        if _psv_s["dumped"]:
            return
        _psv_s["dumped"] = True
        try:
            c = renpy.display.im.cache
            renpy.write_log(
                "PSV CFG: cache_mb=%r cache_size=%r limit=%rMpx sw=%r sh=%r less_mem=%r",
                config.image_cache_size_mb,
                config.image_cache_size,
                c.cache_limit / 1048576.0,
                config.screen_width,
                config.screen_height,
                renpy.game.less_memory)
        except Exception as e:
            renpy.write_log("PSV CFG dump failed: %r", e)

    def _psv_probe():
        now = _psv_t.time()
        d = now - _psv_s["last"]
        _psv_s["last"] = now
        _psv_s["n"] += 1
        _psv_s["acc"] += d

        if d > _psv_s["worst"]:
            _psv_s["worst"] = d
            _psv_s["worst_at"] = _psv_where()

        if d > 1.0:
            try:
                c = renpy.display.im.cache
                extra = "cache=%.1f/%.1fMpx img=%d" % (
                    c.get_total_size() / 1048576.0,
                    c.cache_limit / 1048576.0,
                    len(c.cache))
            except Exception:
                extra = "cache=?"
            renpy.write_log("PSV STALL %.2fs at %s %s", d, _psv_where(), extra)

        if _psv_s["n"] >= 30:
            avg = _psv_s["acc"] / _psv_s["n"]
            renpy.write_log(
                "PSV FPS: %.2f (avg %.0f ms, worst %.0f ms @ %s)",
                1.0 / max(avg, 0.0001), avg * 1000.0,
                _psv_s["worst"] * 1000.0, _psv_s["worst_at"])
            _psv_s["n"] = 0
            _psv_s["acc"] = 0.0
            _psv_s["worst"] = 0.0
            _psv_s["worst_at"] = ""

    config.periodic_callbacks.append(_psv_probe)
    config.start_interact_callbacks.append(_psv_dump_cfg)
