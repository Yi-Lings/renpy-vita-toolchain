---
name: renpy-vita-port
description: Port a Ren'Py 7.x game to PS Vita (renpy-vita runtime) end-to-end — package, fix startup failures, and optimise to a playable state in one pass. Use when packaging a Ren'Py game for PS Vita, debugging a port stuck on the splash image, a C2-12828-1 crash, an 0x8010113D install failure, or when a working port stutters on input.
---

# Ren'Py → PS Vita 移植（一次到位版）

目标：**同一类游戏第二次移植时，照本文线性走完就能达到已验证的水平**，不必重新试错。

**先读 `RULES.md`**（24 条铁律，每条对应一次真实事故），再回到本文按阶段执行。

已验证基线：**Angel Sex Pet**（Cherry Kiss / cybele，Ren'Py 7.3.5）
— 启动 ~70s、进菜单 2.76s、单句台词 <0.6s、包 124.6 MB。

---

## 何时用

- 要把某款 Ren'Py 7.x 游戏打成 Vita 能装的包
- 包卡在启动图 / 启动即崩 / 安装失败
- 已经能跑但**按按钮反应慢**
- 要判断某款游戏能不能移植

## 可行性判断

| 引擎 | 运行时 | 状态 |
|---|---|---|
| Ren'Py 7.x（Py2.7） | [renpy-vita](https://github.com/SonicMastr/renpy-vita) | ✅ 本文 |
| Ren'Py 8.x（Py3） | [RenPy-Vita-8](https://github.com/Grimiku/RenPy-Vita-8) | ✅ |
| RPG Maker XP/VX/VX Ace/2000/2003 | [mkxp-z-vita](https://github.com/Asukate/mkxp-z-vita) | ✅ |
| Unity / RM MV·MZ / NW.js / KiriKiri / System4 | 无 | ❌ |

先扫素材再决定：**视频不支持**；Live2D 需原生模块（运行时没有）；
WebP 支持未确认。命中就提前说明不可行。

---

## 一次性移植清单

按顺序做，每步都有验收。**跳过任何一步都会在真机上翻车。**

| # | 步骤 | 命令 / 动作 | 验收 |
|---|---|---|---|
| 1 | 体检 | `fix_script_version.py`、`fix_telemetry.py` | `script_version.txt` 只剩 `(7, 3, 5)` |
| 2 | 组装运行时 | 从**能跑的设备**整目录复制 `renpy/common` | 336 文件 / 54 `.rpyc`，逐字节一致 |
| 3 | 补丁 | `psv_skip_telemetry` `psv_input` `psv_perf` `psv_fontmem` `psv_keys` | 5 个 `.rpyc` 在 `game/` |
| 4 | 图片优化 | `jpeg_recompress.py --max-w 1366 --max-h 768` | **解码像素数** ≤1366×768 |
| 5 | 字体子集化 | `subset_font.py`，字符集扫**所有 rpa** | 每个字体 ≈1–4 MB |
| 6 | 归档瘦身 | `slim_archives.py` | 无 `.rpy`、无 `python-packages/` |
| 7 | 打包 | `build_package.py` | 首条 `sce_sys/param.sfo` |
| 8 | **自查** | `selfcheck_package.py --ref-common <设备common>` | **`RESULT: PASS`（84 项）** |

> 第 8 步是硬性要求。它会拦下 `0x8010113D`、卡 `pic0`、启动现场编译等
> 所有「装到机器上才发现」的问题。

---

## 阶段详解

### 阶段 0｜环境

```
设备：PS Vita 3.60/3.65（Enso）
必需：ur0:/data/libshacccg.suprx     ← VitaDB-Downloader 一键装，装完重启
PC  ：Ren'Py 7.4.9 SDK（编译 .rpyc）
      Python 3.11+ / Pillow / fontTools / unrpyc
```

### 阶段 1｜先体检，别急着打包

```bash
python tools/fix_script_version.py <游戏目录>   # 水印，命中率极高
python tools/fix_telemetry.py <游戏目录>        # init 联网上报，17 个里 11 个有
```

这两个是**静默杀手**：不修，包打出来只是白等（铁律 2、3）。

### 阶段 2｜组装运行时

```
ux0:/app/<TITLE_ID>/
├─ eboot.bin            7,732,057    原版，别换
├─ renpy.py             6,722        原版，别换
├─ lib/python27.zip     3,919,486    原版，别换
├─ module/*.suprx ×4                 原版
├─ renpy/common/        336 文件 / 54 .rpyc / 15 .rpymc
└─ game/                游戏数据
```

**`renpy/common` 必须从能跑的设备整目录复制**（铁律 1、21）。
PC SDK 编出来的 `.rpyc` 与运行时 `7.4.9.0u` 不兼容，会导致每次启动重编译。

### 阶段 3｜运行时补丁（5 个）

| 补丁 | 不加会怎样 |
|---|---|
| `psv_skip_telemetry.rpyc` | 启动即崩 |
| `psv_input.rpyc` | 改名**永久卡死** |
| `psv_perf.rpyc` | 卡顿加重 |
| `psv_fontmem.rpyc` | **操作卡顿 3.7 倍** |
| `psv_keys.rpy` | 按键与 PS 习惯相反（○确认/×返回） |

发布包**不要**放 `psv_diag.rpyc`（探针，每帧计时本身有开销）。

### 阶段 4｜图片优化

```bash
python tools/jpeg_recompress.py game/gui_resource.rpa game/gui_opt.rpa \
    --quality 88 --max-w 1366 --max-h 768
```

**降采样和转 JPEG 必须一条命令做完**（铁律 17）。分两步做、或对已重打包的产物做，
会漏掉降采样——文件从 2 MB 变 300 KB 但解码仍是 1920×1440，菜单照样卡 10 秒。

**验收看解码像素数，不看文件大小：**

```python
for name, data in iter_rpa('gui_resource.rpa'):
    im = Image.open(io.BytesIO(data))
    if im.width > 1400 or im.height > 800:
        print('漏了!', name, im.size)      # 必须为空
```

实测收益：`img` 137.8→9.6 MB，`gui` 54.5→14.2 MB。

### 阶段 5｜字体子集化

```bash
python tools/subset_font.py --rpa game/*.rpa --font gui/font/SourceHanSansSC-Regular.otf
```

实测：3 × 17 MB → 3 × 4.1 MB。

⚠ **字符集必须扫所有 rpa，包括 `dlc_*.rpa`**（铁律 20）。
Angel Sex Pet 的 `dlc_japanese` 里藏着一个 **16 MB 未子集化**的完整字体，
只用来画一个「日本語」按钮，却占了全部字体内存的 56%。

### 阶段 6｜归档瘦身

```bash
python tools/slim_archives.py --rpa game/archive.rpa --rpa game/dlc_japanese.rpa
```

删两类**运行时永不读取**的东西（都有源码依据）：

- `.rpy` 源码 —— `script.py:238-242`：归档来的 `.rpy` 直接 `continue`
- `python-packages/`（requests/urllib3/chardet）—— 只被上报用，而上报已被补丁挡住

实测：`archive.rpa` 4.98 → 1.78 MB。

### 阶段 7｜打包

```bash
python tools/build_package.py --build <运行时> --game <game目录> \
    --out dist --title-id <TITLE_ID>
# X_Runtime.vpk  可公开
# X_Full.vpk     含游戏本体，勿公开
# X_NoNpDrm.zip
```

### 阶段 8｜自查（**不许跳**）

```bash
python tools/selfcheck_package.py \
    --vpk dist/<项目>_Full.vpk \
    --runtime dist/<项目>_Runtime.vpk \
    --ref-common G:/app/<TITLE_ID>/renpy/common
```

必须 `RESULT: PASS`。84 项覆盖：LiveArea 8-bit 索引色、VPK 三条、`pic0` 尺寸、
`.rpyc` 预编译、`script_version` 干净、RPA 可读、原版尺寸、`renpy/common` 逐字节一致。

---

## 启动失败排查

**严格按顺序，别跳步：**

1. **`pic0.png` 鉴别** —— 把 `game/` 改名再启动。
   图还在 = 运行时问题；图没了 = 游戏数据问题。
2. **读 `log.txt`** —— 最后一行只是最后 flush 的内容，**不是崩溃点**。
3. **解崩溃 dump** —— `ux0:/data/psp2core-*.psp2dmp` 是 gzip 的 ELF core，
   在内存里搜字符串（靠这个搜到 `ipinfo.io` 定位遥测块）。
4. **反编译 rpyc** —— `unrpyc` 还原 `.rpy`，看 init 块。
5. **PC 上 SDK 复现** —— `renpy.exe <project> lint`，异常最详细。

**常见误判**：日志停在 `Importing _renpysteam` 之后没有 `Set script version to:`，
看起来像崩在那行——其实只是那行没打出来（铁律 2）。

---

## 性能优化

### 先纠正一个曾把我们带偏的错误结论

**`config.periodic_callbacks` 在等待输入时是会跑的。**
实测 10 秒内触发 198 次、最大间隔 52ms。早期「回调不跑，所以测到的卡顿是
玩家思考时间」的判断**是错的，已撤回**。

所以 `periodic_callbacks` 里测到的耗时可采信；但仍建议用
`Interface.draw_screen()` / `render.render_screen()` 直接测帧，粒度更细。

### 用探针，别靠感觉

现成实现：`patches/psv_diag.rpy`（v8）。输出：

```
PSV FRAME 10.23s | get=8(miss=5) 1.01s | text=10 9.12s | tex=0 0.00s
PSV TEXT   2.39s size=24 style=None  u'开始游戏'
PSV FONT MEM gui/font/xxx.otf  4.07 MB -> BytesIO
PSV TEXTCACHE size=120 new=35 old=10 vnew=35
```

### 判读表（按实测修正）

| 现象 | 结论 | 动作 |
|---|---|---|
| `text=` 占整帧 85%+ | **文字渲染是瓶颈** | 见下方优先级 1 |
| `text=` 耗时与字数**不成比例**（5 个字符要 0.5s） | 字体在 rpa 里被**逐字形流式读取** | 优先级 1（铁律 18） |
| `get=` 占 30%+ | 图片解码 | 优先级 2 |
| `tex=` 不为 0 且很大 | 纹理上传 | 查是否 `copy RTT` |
| `RENDER` 单次几秒，位置固定在进菜单 | 界面首次构建 | 查该界面背景图尺寸 |
| 稳定 50ms/帧（20fps） | 上限就在这 | 正常，Vita 上没有 vsync 撕裂 |

### 优化优先级（按实测收益排序）

1. **字体整块读入内存** —— 实测整帧 **10.23s → 2.76s（3.7×）**
   `patches/psv_fontmem.rpy`：包 `renpy.loader.load`，字体类文件返回 `io.BytesIO`。
   原理：FreeType 走 Python 回调逐字形 `seek`/`read` 一个几 MB 的 `.rpa`。
   代价：字体常驻 ~29 MB。

2. **降采样 + 转 JPEG（一条命令）** —— 解码快 27 倍（铁律 10、17）
   注意 `gui_*/main_menu`、`game_menu`、`disclaimer` 这三张最容易被漏掉。

3. **检查 `dlc_*.rpa` 里的未子集化字体**（铁律 20）

4. **字体子集化** —— 省 40 MB 常驻内存（铁律 11）

5. **归档瘦身** —— 只减包体积，对启动几乎无影响

6. **`config.predict_statements = 24`** —— 缓存只有 25 Mpx，预测别开太大

⚠ **不要再调 `config.image_cache_size_mb`** —— Vita 的 `Cache.init()`
第一行就 `if renpy.vita: cache_limit = 26214400`，你写的值根本走不到。
日志里永远是 `limit=25.0Mpx`。

⚠ **不要开 `config.cache_surfaces`** —— Surface 和纹理都计入同一个 25Mpx 上限，
能装的图少一半。

⚠ **不要动音频**。语音/音效保持原始 OGG，**任何降采样或重编码都是错的**。
实测确认 `sfx_resource.rpa` 从未被修改（988 个原始 `.ogg`，哈希与发行版一致）。

### 启动慢怎么办

先量，别猜。实测构成（Angel Sex Pet，71.5s）：

| 阶段 | 耗时 | 占比 |
|---|---|---|
| **Loading script** | **52.01s** | **73%** |
| Running init code | 2.90s | 4% |
| 其余 27 项 | 各 <3s | 23% |

**`Loading script` 是纯 CPU 的 AST 反序列化，不是 I/O**——
同一份数据 PC 上只要 1.38s（比值 38×，正好是 CPU 差距），而归档里只有 2.17 MB `.rpyc`。

能做的有限（详见 `docs/启动优化计划.md`）：
删无用翻译约 -11%、归档瘦身对启动几乎无影响。
**现实下限 55–60s**，参考包（体量更小）也要 37s。不要承诺「秒开」。

---

## 已知无法解决的问题

| 现象 | 说明 |
|---|---|
| **退出时卡死/崩溃** | renpy-vita 运行时在 SDL/GL 拆卸阶段的老问题，不影响存档。**不要在这上面花时间**——真要绕开只能硬退出（跳过拆卸），但会丢日志、且无法确认卡点 |
| 视频播放 | 运行时无视频支持 |
| 启动 70 秒 | 物理下限，见上 |

---

## 红线

- **不要**把含游戏数据的包公开上传 —— 版权问题，用私有仓库
- **不要**手动写 `.rpyc` —— 版本常量对不上会被拒绝加载
- **不要**替换 `renpy.py` / `python27.zip` / `eboot.bin` 成别的移植版本
- **不要**用文件夹直拷注册气泡 —— 3.65 上验证过两次都失败
- **不要**只抽查看字符集覆盖 —— 少一个字就是一个方框
- **不要**动音频
- **不要**在没跑 `selfcheck_package.py` 的情况下装机

---

## 参考

- [SonicMastr/renpy-vita](https://github.com/SonicMastr/renpy-vita)
- [Grimiku/RenPy-Vita-8](https://github.com/Grimiku/RenPy-Vita-8)
- [SilverCrow2323/Renpy-Vita-Portings](https://github.com/SilverCrow2323/Renpy-Vita-Portings) — 兼容性列表
- [CensoredUsername/unrpyc](https://github.com/CensoredUsername/unrpyc)
- [Hammerill/livearea-specs](https://github.com/Hammerill/livearea-specs)

## 本仓库内的配套文档

| 文件 | 内容 |
|---|---|
| `RULES.md` | 24 条铁律 |
| `docs/移植总结-CherryKiss系.md` | 同类作品可复用手册（含实测基准数字） |
| `docs/性能分析-文字渲染.md` | 卡顿根因：字体流式 I/O |
| `docs/启动优化计划.md` | 70 秒启动的构成与结论 |
| `docs/移植踩坑总结.md` | 完整踩坑过程 |
