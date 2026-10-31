---
name: renpy-vita-port
description: Port a Ren'Py game to PS Vita (renpy-vita runtime). Use when packaging a Ren'Py 7.x game for PS Vita, debugging a port stuck on the splash image, a C2-12828-1 crash at startup, an 0x8010113D install failure, or optimizing a working Vita port that stutters.
---

# Ren'Py → PS Vita 移植

把 Ren'Py 游戏移植到 PS Vita。覆盖打包、启动失败排查、性能优化。

**先读 `RULES.md`** —— 那是 22 条铁律，每条都对应一次真实踩坑。

---

## 何时用这个 skill

- 要把某款 Ren'Py 7.x 游戏打成 Vita 能装的包
- 移植包卡在启动图 / 启动即崩 / 安装失败
- 已经能跑但卡顿，要优化
- 要判断某款游戏能不能移植

## 快速判断可行性

| 引擎 | Vita 运行时 | 状态 |
|---|---|---|
| Ren'Py 7.x（Python 2.7） | [renpy-vita](https://github.com/SonicMastr/renpy-vita) | ✅ 可用（本文） |
| Ren'Py 8.x（Python 3） | [RenPy-Vita-8](https://github.com/Grimiku/RenPy-Vita-8) | ✅ 可用 |
| RPG Maker XP/VX/VX Ace/2000/2003 | [mkxp-z-vita](https://github.com/Asukate/mkxp-z-vita) | ✅ 可用 |
| Unity / RPG Maker MV/MZ / NW.js / KiriKiri / System4 | 无 | ❌ |

**先扫素材再决定**：`WebP` 是否支持未确认；`Live2D` 需要原生模块（运行时没有）；
视频不支持。有这些要提前告知不可行。

---

## 移植流程

### 阶段 0｜环境准备

```
设备：PS Vita 3.60/3.65（Enso）
必需：ur0:/data/libshacccg.suprx      ← 装 VitaDB-Downloader 一键装，装完重启
PC  ：Ren'Py 7.4.9 SDK                 ← 用来编译 .rpyc
```

### 阶段 1｜先体检，别急着打包

```bash
# 1) script_version.txt 水印（命中率极高）
python tools/fix_script_version.py <游戏目录>

# 2) init 阶段联网上报（17 个游戏里 11 个有）
python tools/fix_telemetry.py <游戏目录>
```

两项都命中就必须先修。**这两个是静默杀手**，不修的话打包出来只是白等。

### 阶段 2｜组装运行时

```
ux0:/app/<TITLE_ID>/
├─ eboot.bin            7,732,057     DistTool 原版
├─ renpy.py             6,722         DistTool 原版（别改）
├─ lib/python27.zip     3,919,486     DistTool 原版（别改）
├─ module/*.suprx ×4                  DistTool 原版
├─ renpy/common/        336 文件 / 54 个 .rpyc   ← 从能跑的包整目录复制
└─ game/                游戏数据
```

**`renpy/common` 是整个流程里最容易翻车的一步**，见铁律 1。

### 阶段 3｜生成补丁

```bash
python tools/fix_telemetry.py <游戏目录> --write --sdk <SDK路径>
# 产出 game/psv_skip_telemetry.rpyc
```

补丁 `.rpyc` 必须 SDK 编译，版本常量 5003000。

### 阶段 4｜素材优化（如果有性能要求）

```bash
# 4a 降采样 + 转 JPEG —— 必须一条命令做完（见铁律 17）
python tools/jpeg_recompress.py game/gui_resource.rpa game/gui_opt.rpa \
    --quality 88 --max-w 1366 --max-h 768
python tools/jpeg_recompress.py game/img_resource.rpa game/img_opt.rpa \
    --quality 88 --max-w 1366 --max-h 768

# 4b 字体子集化
python tools/subset_font.py 原字体.otf 输出.otf --charset charset.txt

# 4c 删无用翻译
python tools/rpa_tool.py filter game/archive.rpa game/archive_opt.rpa --drop 'tl/en/,tl/es/'
```

**不要在两步之间重新打包**——`optimize_images.py` 之后再跑
`jpeg_recompress.py` 时，务必确认输入是**原始 rpa**，不是上一步的产物。

**验收标准：逐张检查解码像素数，不是文件大小。**

```python
for name, data in iter_rpa('gui_resource.rpa'):
    im = Image.open(io.BytesIO(data))
    if im.width > 1400 or im.height > 800:
        print('漏了!', name, im.size)      # 必须为空
```

`gui/main_menu.png`、`gui/game_menu.png`、`gui/disclaimer.png` 这三张
最容易漏——游戏里写死了 `size=(1024, 768)`，原图却是 1920×1440。

### 阶段 5｜性能配置

```python
init -9 python:
    # ⚠ Vita 的 Cache.init() 写死 cache_limit = 26214400（25.0 Mpx），
    #   image_cache_size_mb 无论写多少都不生效（铁律 9.1）。
    #   这里写的值只在 PC 上有效，留着保持一致。
    config.image_cache_size_mb = 192

    # ⚠ 不要开 cache_surfaces：会把 Surface 和纹理都计入同一个 25Mpx 上限，
    #   能装的图少一半。
    config.predict_statements  = 24       # 缓存小，预测别开太大
    config.hard_rollback_limit = 20
    config.autosave_frequency  = None
```

编译成 `psv_perf.rpyc` 放进 `game/`。

### 阶段 6｜打包

```bash
python tools/build_package.py \
    --build <运行时目录> --game <game目录> \
    --out dist --title-id ANGE00001
# 产出：X_Runtime.vpk（14MB，可公开）
#       X_Full.vpk（含游戏数据，勿公开）
#       X_NoNpDrm.zip
```

### 阶段 7｜验证

读 `ux0:/app/TITLEID/log.txt`：

| log 行 | 含义 |
|---|---|
| `Set script version to: (x,y,z)` | 水印已清 |
| `Running init code took ...` | init 没崩（联网块已跳过） |
| `Initializing gles renderer:` | 引擎起来了 |
| `Screen sizes: virtual=...` | 渲染器正常 |

---

## 启动失败排查

**严格按顺序，不要跳步：**

1. **`pic0.png` 鉴别** —— 把 `game/` 改名再启动。
   图还在 = 运行时问题；图没了 = 游戏数据问题。
2. **读 `log.txt`** —— 最后一行只是最后 flush 的内容，**不是崩溃点**。
3. **解崩溃 dump** —— `ux0:/data/psp2core-*.psp2dmp` 是 gzip 的 ELF core，
   在内存里搜字符串（我们靠这个搜到 `ipinfo.io` 定位到遥测块）。
4. **反编译 rpyc** —— `unrpyc` 还原成 `.rpy`，看 init 块。
5. **PC 上 SDK 复现** —— `renpy.exe <project> lint`，异常信息最详细。

**常见误判**：日志停在 `Importing _renpysteam` 后面没有
`Set script version to:`，看起来像崩在那行 —— 其实那行只是没打出来（铁律 2）。

---

## 性能优化

**先测，再改。** 而且要用**正确的**测法 —— 见铁律 12：
`periodic_callbacks` 在等待输入时不跑，测出来的「卡顿」是玩家思考时间，
「FPS」恒等于定时器周期的倒数（20.0），全是假的。

正确做法：包 `Interface.draw_screen()` / `render.render_screen()` 测真实耗时。
现成实现见 `patches/psv_diag.rpy`。

**读法**：

| 现象 | 结论 | 动作 |
|---|---|---|
| `FRAME` 单次几千 ms，且位置在菜单/界面 | 界面首次构建 | 查该界面的背景图尺寸 |
| `RENDER` 持续几十~几百 ms | 布局/文字排版 | 查字体子集、描边层数 |
| `LOAD` 单次 > 0.5s | 从 rpa 读大文件 | 查语音/图片是否过大 |

**优化优先级**（按收益排序）：

1. **降采样 + 转 JPEG（一条命令）** —— 解码快 27 倍，收益最大（铁律 10、17）
2. **检查菜单背景图** —— `gui_*/main_menu/game_menu/disclaimer` 常被漏掉
3. **字体子集化** —— 省 40 MB 常驻内存（铁律 11）
4. **删无用翻译** —— 启动快 30%
5. **`config.predict_statements = 24`** —— 缓存只有 25Mpx，预测别开太大

⚠ **不要再试图调 `config.image_cache_size_mb`** —— Vita 的
`Cache.init()` 第一行就 `if renpy.vita: cache_limit = 26214400`，
你写的值根本走不到。日志里永远是 `limit=25.0Mpx`。

⚠ **也不要开 `config.cache_surfaces`** —— Surface 和纹理都会计入同一个
25Mpx 上限，能装的图少一半。

---

## 红线

- **不要**把含游戏数据的包公开上传 —— 版权问题，用私有仓库
- **不要**手动写 `.rpyc` —— 版本常量对不上会被拒绝加载
- **不要**替换 `renpy.py` / `python27.zip` 成别的移植版本 —— 会变更糟
- **不要**用文件夹直拷注册气泡 —— 3.65 上验证过两次都失败
- **不要**只抽查看字符集覆盖 —— 少一个字就是一个方框

---

## 参考

- [SonicMastr/renpy-vita](https://github.com/SonicMastr/renpy-vita)
- [Grimiku/RenPy-Vita-8](https://github.com/Grimiku/RenPy-Vita-8)
- [SilverCrow2323/Renpy-Vita-Portings](https://github.com/SilverCrow2323/Renpy-Vita-Portings) — 兼容性列表
- [CensoredUsername/unrpyc](https://github.com/CensoredUsername/unrpyc) — rpyc 反编译
- [Hammerill/livearea-specs](https://github.com/Hammerill/livearea-specs) — LiveArea 规格
