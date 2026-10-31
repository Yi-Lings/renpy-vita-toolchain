init -100 python:
    # 修 Vita 上 renpy.input() 卡死的问题。
    #
    # 症状：设置里点「Change Name」后整个游戏冻结。
    # 原因：renpy.input() 会调 SDL 的文本输入（Vita 上是系统输入法 / IME），
    #       renpy-vita 的 SDL 移植没有实现这条路，于是事件循环永远等不到输入。
    #
    # 方案：把 renpy.input 换成一个纯引擎内的屏幕键盘，不碰系统输入法。

    _psv_kb = {
        "text": u"",
        "prompt": u"",
        "max": 20,
        "default": u"",
    }

    _psv_kb_presets = [
        u"Takeshi", u"Rei", u"Haruto", u"Yohei",
        u"隆司", u"隆志", u"河原隆司", u"主人公",
    ]

    def _psv_kb_reset(prompt, default, maxlen):
        _psv_kb["prompt"] = prompt if prompt else u""
        _psv_kb["text"] = default if default else u""
        _psv_kb["default"] = default if default else u""
        _psv_kb["max"] = maxlen if maxlen else 20

    def _psv_kb_add(ch):
        t = _psv_kb["text"]
        if len(t) < _psv_kb["max"]:
            _psv_kb["text"] = t + ch
            renpy.restart_interaction()

    def _psv_kb_del():
        _psv_kb["text"] = _psv_kb["text"][:-1]
        renpy.restart_interaction()

    def _psv_kb_clear():
        _psv_kb["text"] = u""
        renpy.restart_interaction()

    def psv_input(prompt, default='', allow=None, exclude='{}', length=None,
                  with_none=None, pixel_width=None, screen="input", mask=None,
                  **kwargs):
        """renpy.input 的替代品：用引擎内屏幕键盘。"""
        try:
            _psv_kb_reset(prompt, default, length)
            ok = renpy.call_screen("psv_keyboard")
            if ok:
                rv = _psv_kb["text"]
                if allow is not None:
                    rv = u"".join(c for c in rv if c in allow)
                return rv
            return default if default else u""
        except Exception:
            # 任何意外都不要把游戏卡死
            return default if default else u""


screen psv_keyboard():
    modal True
    zorder 200

    add Solid("#000000cc")

    frame:
        align (0.5, 0.5)
        padding (32, 28)
        background Frame(Solid("#1b1b1b"), 8, 8)

        vbox:
            spacing 14

            text _psv_kb["prompt"] size 30 color "#ffffff"

            frame:
                xsize 720
                ysize 60
                padding (12, 8)
                background Solid("#000000")

                text (_psv_kb["text"] if _psv_kb["text"] else u" ") size 34 color "#7ccdf1"

            # 字母 + 数字键盘
            vbox:
                spacing 6
                for row in (u"ABCDEFGHIJ", u"KLMNOPQRST", u"UVWXYZ0123", u"456789 -_"):
                    hbox:
                        spacing 6
                        for ch in row:
                            textbutton ch:
                                xsize 64
                                ysize 48
                                action Function(_psv_kb_add, ch)

            # 常用名字快捷键
            hbox:
                spacing 6
                for nm in _psv_kb_presets:
                    textbutton nm:
                        ysize 44
                        action [Function(_psv_kb_reset, _psv_kb["prompt"], nm, _psv_kb["max"]),
                                Function(renpy.restart_interaction)]

            hbox:
                spacing 10
                textbutton u"空格" xsize 140 ysize 52 action Function(_psv_kb_add, u" ")
                textbutton u"删除" xsize 140 ysize 52 action Function(_psv_kb_del)
                textbutton u"清空" xsize 140 ysize 52 action Function(_psv_kb_clear)
                textbutton u"确定" xsize 200 ysize 52 action Return(True)
                textbutton u"取消" xsize 140 ysize 52 action Return(False)


init 999 python:
    # 只替换一次，避免重复包装
    if not getattr(renpy, "_psv_input_patched", False):
        renpy.input = psv_input
        renpy._psv_input_patched = True
