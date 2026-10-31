---
name: renpy-vita-port
description: Port a Ren'Py game to PS Vita (renpy-vita runtime). Use when packaging a Ren'Py 7.x game for PS Vita, debugging a port stuck on the splash image, a C2-12828-1 crash at startup, an 0x8010113D install failure, or optimizing a working Vita port that stutters.
---

# Ren'Py → PS Vita 移植

把 Ren'Py 游戏移植到 PS Vita。覆盖打包、启动失败排查、性能优化。

**先读 `RULES.md`** —— 那是 15 条铁律，每条都对应一次真实踩坑。

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
# 4a 降采样（1920x1440 -> 1024x768）
python tools/optimize_images.py game/img_resource.rpa game/img_opt.rpa --max-w 1366 --max-h 768

# 4b 不透明图转 JPEG（保留 .png 文件名）
python tools/jpeg_recompress.py game/img_opt.rpa game/img_opt2.rpa --quality 85

# 4c 字体子集化
python tools/subset_font.py 原字体.otf 输出.otf --charset charset.txt

# 4d 删无用翻译
python tools/rpa_tool.py filter game/archive.rpa game/archive_opt.rpa --drop 'tl/en/,tl/es/'
```

顺序不能乱：**先降采样 → 再转 JPEG**。

### 阶段 5｜性能配置

```python
init -9 python:
    config.image_cache_size_mb = 192     # 别低于 128，见铁律 9
    config.predict_statements  = 32      # 别调小
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

**先测，再改。** 用 `periodic_callbacks` 测真实 FPS（铁律 12）。

**读法**：

| 现象 | 结论 | 动作 |
|---|---|---|
| 稳态 FPS 低（< 25） | 渲染瓶颈 | 降素材尺寸、减图层 |
| 稳态正常但 `worst` 几千 ms | 一次性加载 | 转 JPEG、加缓存、预载 |
| 两者都差 | 先解决加载 | 再做渲染 |

**优化优先级**（按收益排序）：

1. **转 JPEG** —— 解码快 27 倍，收益最大（铁律 10）
2. **降采样** —— 像素少 3.5 倍
3. **字体子集化** —— 省 40 MB 常驻内存（铁律 11）
4. **删无用翻译** —— 启动快 30%
5. **缓存调到 192 MB** —— 别调小（铁律 9）

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
