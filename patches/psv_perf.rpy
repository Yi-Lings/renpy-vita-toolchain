init -9 python:
    # PS Vita 性能调优 v2（2026-10-31）
    #
    # v1 的教训：把 image_cache_size_mb 从 300 压到 64 是错的。
    # 缓存装不下游戏的工作集，每次交互都在淘汰→重读→重解码，
    # 单次按钮响应反而从几秒恶化到 15 秒。
    #
    # 结论：缓存宁大勿小，只要不超过机器实际可用内存。

    # 192 MB ≈ 60 张 1024x768 RGBA 贴图。
    # Vita 可用约 330 MB，扣掉 Python 运行时和字体后还能放下。
    config.image_cache_size_mb = 192

    # 预测保持默认 32。预测是在后台线程预读下一批图片，
    # 调小只会让交互时同步读盘，越调越卡。
    config.predict_statements = 32

    # 回滚层数从 100 降到 20：每层都要保存 store 快照，
    # 弱 CPU 上省下的是实打实的内存和拷贝时间。
    config.hard_rollback_limit = 20

    # 自动存档 = 一次完整序列化 + 写存储卡，Vita 上顿挫很明显。
    # 关掉，玩家手动存档照常可用。
    config.autosave_frequency = None
