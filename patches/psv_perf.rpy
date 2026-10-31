# -*- coding: utf-8 -*-
"""PSV 性能补丁 v3（2026-10-31，基于真机日志 + 运行时反汇编）

## 一个必须先纠正的结论

`config.image_cache_size_mb` 在 Vita 上**完全无效**。

反汇编 `lib/python27.zip` 里的 `renpy/display/im.pyo`，`Cache.init()` 是：

    def init(self):
        if renpy.vita:
            self.cache_limit = int(26214400)          # ← 写死 25.0 Mpx = 100 MB
        elif config.image_cache_size is not None:
            self.cache_limit = 2 * config.image_cache_size * sw * sh
        else:
            self.cache_limit = image_cache_size_mb * 1024 * 1024 // 4

Vita 分支排第一，直接 return。所以日志里永远 `limit=25.0Mpx`，
从 64 改成 192 或其它值都没有意义——分支根本走不到。

**这意味着「调缓存」这条路在 Vita 上是死的**，只能靠
「降低每张图的像素数」和「降低解码成本」来适配这 25Mpx。

## 关于 config.cache_surfaces（重要）

Ren'Py 默认 `cache_surfaces = False`：纹理上传到 GPU 后就把
解码出来的 Surface 丢掉（`im.py:332-337`），只留纹理。

改成 `True` 会**同时**保留 Surface 和纹理，两者都计入
`CacheEntry.size()`（`width*height + bounds`）——也就是
同一个 25Mpx 上限下能装的图片**少了一半**。

所以 Vita 上**不要**开 `cache_surfaces`。（PC 内存充足时开着能
避免纹理被淘汰后重新解码，但 Vita 没有这个余量。）

## 这个补丁保留的项

* `config.predict_statements = 24`
  预测稍保守。缓存只有 25Mpx，预测太多会把刚用过的图挤掉。

* `config.hard_rollback_limit = 20` —— 每层回滚都要保存 store 快照。

* `config.autosave_frequency = None` —— 自动存档 = 完整序列化 + 写卡。
"""

init -9 python:

    # 预测别开太大：缓存只有 25Mpx（Vita 写死），预测多了会互相挤掉
    config.predict_statements = 24

    # 回滚层数：每层都要保存 store 快照
    config.hard_rollback_limit = 20

    # 自动存档 = 一次完整序列化 + 写存储卡，顿挫明显
    config.autosave_frequency = None
