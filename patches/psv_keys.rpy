# PS Vita 按键映射：○ = 确认，× = 退出 / 返回
#
# 为什么要改：
#   Ren'Py 默认按 Xbox 习惯绑：
#       pad_a_press  → dismiss / button_select   （确认）
#       pad_b_press  → button_alternate          （取消）
#   而 SDL 的「A 位」在 PlayStation 布局上是 ×（下方），「B 位」是 ○（右方）。
#   于是 Vita 上变成 × 确认、○ 取消，和 PS 系习惯相反。
#
# 改法：把两个位置对调。
#   pad_b_press（○）→ dismiss / button_select  = 确认、推进台词
#   pad_a_press（×）→ game_menu                = 打开菜单 / 菜单内返回
#
# 为什么「退出」用 game_menu 而不是 button_alternate：
#   game_menu 绑的是 K_ESCAPE / 右键（00keymap.rpy:32），处理器是
#   _invoke_game_menu —— 对话中打开菜单、菜单内 Return()，正是「返回」。
#   button_alternate 只是右键的别名，在按钮上没有统一的「返回」语义。
#
# config.pad_bindings 在 00keymap.rpy 里以 init -1600 建立，
# 本文件用 init -9，一定在它之后，能覆盖。

init -9 python:

    _psv_confirm = [ "dismiss", "button_select", "bar_activate", "bar_deactivate" ]
    _psv_back = [ "game_menu" ]

    config.pad_bindings["pad_b_press"] = list(_psv_confirm)   # ○ 确认
    config.pad_bindings["pad_a_press"] = list(_psv_back)      # × 退出/返回

    # 诊断：把第一次见到的每个手柄按键名写进 log，
    # 用来核对「○」到底报成 pad_b 还是 pad_a。
    # 只在第一次出现时记一行，不会刷屏。
    _psv_pad_seen = set()

    try:
        import renpy.display.controller as _psv_ctrl
        _psv_post = _psv_ctrl.post_event

        def _psv_post_event(control, state, repeat):
            try:
                key = "%s_%s" % (control, state)
                if key not in _psv_pad_seen:
                    _psv_pad_seen.add(key)
                    renpy.write_log("PSV PAD: %s", key)
            except Exception:
                pass
            return _psv_post(control, state, repeat)

        _psv_ctrl.post_event = _psv_post_event
    except Exception:
        pass
