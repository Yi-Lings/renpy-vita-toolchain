# Cherry Kiss / Miel 系 Ren'Py 游戏 → PS Vita 移植总结

> 基于 **Angel Sex Pet**（Cherry Kiss Games 发行 / cybele 开发，Ren'Py 7.3.5）实机移植经验整理。
> 目标：同类作品（Ren'Py 7.x、Cherry Kiss 发行、日系 ADV）可**按本文照做**，不必重新踩坑。
> 配套：`RULES.md`（21 条铁律，每条对应一次真实事故）、`docs/性能分析-文字渲染.md`（性能专题）。

---

## 一、这类游戏的共同特征（先判断能不能套用本文）

在动手前先确认，命中越多越省事：

| 特征 | 怎么查 | 命中含义 |
|---|---|---|
| Ren'Py 7.x | `game/script_version.txt` 内容形如 `(7, 3, 5)` | 本文流程直接适用 |
| 有 `*.rpa` 归档 | `game/` 下有 `archive.rpa` 等 | 需要 `rpa_tool.py` 解包 |
| 有 `gui_resource.rpa` | 同上 | 素材优化收益最大的目标 |
| 有 `dlc_*.rpa` | 同上 | ⚠ 注意里面常有**未子集化的完整字体** |
| 中日英三语 | `splashscreen.rpy` 里有语言选择菜单 | 需要处理 CJK 字体 |
| 自带联网上报 | 反编译后搜 `requests` / `urllib` / `telemetry` | **必崩**，必须跳过（铁律 3） |
| 汉化组改过 `script_version.txt` | 文件里出现水印文字 | 启动卡死（铁律 2） |

**Angel Sex Pet 的实测版本组合**（已验证可跑）：

```
Ren'Py 脚本版本  (7, 3, 5)
运行时          renpy-vita 7.4.9.0u（SonicMastr）
Python          2.7.18
渲染器          gles（Vita 无 FBO，只能走 copy RTT，不能用 gl2）
```

---

## 二、环境准备（一次性，做完所有 7.x 游戏通用）

### 2.1 必须的组件

| 组件 | 版本/来源 | 用途 | 校验 |
|---|---|---|---|
| **Ren'Py SDK** | 7.4.9（`renpy-7.4.9-sdk`） | 反编译、编译 `.rpyc`、lint | `renpy.exe` 可运行 |
| **renpy-vita 运行时** | SonicMastr/renpy-vita | Vita 上的引擎本体 | `eboot.bin` = 7,732,057 B |
| **Python** | 3.11+（工具用）+ 运行时内置 2.7.18 | 跑 `tools/*.py` | `import PIL, fontTools` |
| **Pillow** | ≥ 10 | 图片降采样/转码 | `PIL.__version__` |
| **fontTools** | ≥ 4.4x（自带 cu2qu） | 字体子集化 | `fontTools.version` |
| **unrpyc** | CensoredUsername/unrpyc | 反编译 `.rpyc` → `.rpy` | 能处理 7.4.9 |
| **libshacccg.suprx** | 自制系统 | GL 程序硬前置 | 必须在 `ur0:/data/` |

### 2.2 运行时目录的**原版尺寸**（换了必出问题）

踩坑总结里反复验证过的三个数字，**不要替换成别的移植版本的**：

```
eboot.bin            7,732,057 B
renpy.py                 6,722 B
lib/python27.zip     3,919,486 B
renpy/common/        336 个文件，含 54 个 .rpyc + 15 个 .rpymc
```

> `selfcheck_package.py` 会自动核对这三个尺寸和 `renpy/common` 的文件数。

### 2.3 工具清单（`tools/`）

| 工具 | 作用 | 关键点 |
|---|---|---|
| `rpa_tool.py` | RPA-3.0 读写 | **prefix 必须是 `bytes b''`**，offset 和 length 都要 XOR key（铁律 8） |
| `jpeg_recompress.py` | 降采样 + 转 JPEG **一次完成** | 必须带 `--max-w/--max-h`，分两步做会漏（铁律 17） |
| `subset_font.py` | CJK 字体子集化 | 字符集要扫**所有 rpa**，含 `dlc_*`（铁律 20） |
| `fix_script_version.py` | 清理被汉化组污染的版本文件 | 只留 `(7, 3, 5)` |
| `fix_telemetry.py` | 生成跳过上报补丁 | 输出 `psv_skip_telemetry.rpyc` |
| `build_package.py` | 打 VPK / NoNpDrm.zip | 自动保证三条打包规则 |
| `make_scesys_generic.py` | 生成 LiveArea 图 | 输出 8-bit 索引色 PNG |
| **`selfcheck_package.py`** | **打包后全面自查** | **84 项断言，发版前必跑** |

### 2.4 运行时补丁（`patches/`，全部预编译好）

| 补丁 | 作用 | 不加会怎样 |
|---|---|---|
| `psv_skip_telemetry.rpyc` | 跳过首发联网上报 | 启动即崩（铁律 3） |
| `psv_input.rpyc` | 用引擎内屏幕键盘替换 `renpy.input()` | 改名时**永久卡死**（铁律 16） |
| `psv_perf.rpyc` | 性能配置（预测/回滚/自动存档/排版缓存） | 卡顿加重 |
| `psv_fontmem.rpyc` | **字体整块读入内存** | 操作卡顿 3.7 倍（铁律 18） |
| `psv_keys.rpyc` | ○ 确认 / × 返回 | 按键与 PS 习惯相反 |
| `psv_diag.rpyc` | 性能探针（**不进发布包**） | — |

---

## 三、移植流程（八步，每步都有验证）

### 步骤 1｜解包并判断结构

```bash
python tools/rpa_tool.py list game/archive.rpa
```

确认：`script_version.txt` 内容、`gui_resource.rpa` 里的字体、有无 `dlc_*.rpa`。

**验证**：能列出条目即为正常；报 `Could not load from archive` 说明 prefix 类型错了。

### 步骤 2｜反编译脚本（用于检查，不用于发布）

```bash
python unrpyc.py game/*.rpyc
```

**只用来读**，不要回编译 —— 反编译再编译容易丢信息。

**重点搜**：
- `config.developer`
- `requests` / `urllib` / `telemetry` / `report`（联网上报）
- `{font=` 内联字体标签
- `outlines`（描边层数）
- `config.keymap`

### 步骤 3｜清理游戏数据

```bash
# 版本文件
python tools/fix_script_version.py game/script_version.txt

# 删掉用不到的翻译（能省 20 秒启动）
# 只保留 tl/zhcn（或你要的语言），删 tl/japanese / tl/english 等
```

**验证**：`script_version.txt` 只剩 11 字节 `(7, 3, 5)`。

### 步骤 4｜素材优化（收益最大的一步）

**关键：降采样和转 JPEG 必须一条命令做完。**

```bash
python tools/jpeg_recompress.py game/img_resource.rpa game/img_resource.rpa \
    --quality 88 --max-w 1366 --max-h 768
```

**实测效果（Angel Sex Pet）**：

| 文件 | 优化前 | 优化后 |
|---|---|---|
| `img_resource.rpa` | 137.8 MB | **9.6 MB** |
| `gui_resource.rpa` | 54.5 MB | **14.2 MB** |

**验证方法（必须做）**：看**解码后的像素数**，不是文件大小：

```python
for name, data in iter_rpa('gui_resource.rpa'):
    im = Image.open(io.BytesIO(data))
    if im.width > 1400 or im.height > 800:
        print('漏了!', name, im.size)
```

> 血泪教训：只转了 JPEG 没降采样，文件从 2 MB 变 300 KB，
> 但解码仍是 1920×1440，菜单照样卡 10 秒（铁律 17）。

### 步骤 5｜字体子集化

```bash
python tools/subset_font.py --rpa game/*.rpa --font gui/font/SourceHanSansSC-Regular.otf
```

**实测**：3 × 17 MB → 3 × 4.1 MB（15,687 字形）。

**⚠ 必须扫 `dlc_*.rpa`** —— Angel Sex Pet 的 `dlc_japanese` 里有一个
**16.18 MB 的完整字体**，只用在一个「日本語」按钮上，却占了全部字体内存的 56%（铁律 20）。

### 步骤 6｜组装 game 目录

```
game/
├─ archive.rpa                 ← 优化后
├─ dlc_japanese.rpa
├─ gui_resource.rpa            ← 优化后
├─ img_resource.rpa            ← 优化后
├─ sfx_resource.rpa
├─ script_version.txt          ← 清理后
├─ psv_skip_telemetry.rpyc
├─ psv_input.rpyc
├─ psv_perf.rpyc
├─ psv_fontmem.rpyc
└─ psv_keys.rpyc
```

**不要放**：`psv_diag.rpyc`（探针有开销）、`cache/`、`saves/`、`.rpy` 源码。

### 步骤 7｜组装运行时 + 打包

运行时目录必须是 `renpy/common` 与运行时**逐字节一致**的那一份（铁律 21）。

```bash
python tools/build_package.py \
    --build build/<项目名> --game build/<项目名>/game \
    --out dist/<项目名> --title-id <TITLE_ID>
```

产出三个文件：`_Runtime.vpk`（可公开）、`_Full.vpk`（含游戏本体）、`_NoNpDrm.zip`。

### 步骤 8｜发版前自查（**不要跳过**）

```bash
python tools/selfcheck_package.py \
    --vpk dist/<项目名>/<项目名>_Full.vpk \
    --runtime dist/<项目名>/<项目名>_Runtime.vpk \
    --ref-common G:/app/<TITLE_ID>/renpy/common
```

**必须看到 `RESULT: PASS`（84 项全过）。**

它会拦下这些致命问题：

| 检查 | 不通过会怎样 |
|---|---|
| LiveArea PNG 不是 8-bit 索引色 | 装到 99% 报 `0x8010113D` |
| `param.sfo` 不是第一个条目 | 安装失败 |
| 路径含反斜杠 / 非 ASCII 名 | 安装失败 |
| `pic0.png` 不是 960×544 | 卡在静态图 |
| `renpy/common` 缺 `.rpyc` | 启动卡几分钟（现场编译 54 个脚本） |
| `renpy/common` 与运行时不一致 | 启动变慢（`.rpyc` 被判定失效重编译） |
| `script_version.txt` 被污染 | 启动即崩 |
| `psv_input.rpyc` 缺失 | 改名永久卡死 |

---

## 四、实测数据（Angel Sex Pet，供后续作品对比基准）

### 4.1 启动阶段

```
Bootstrap to the start of init.init    2.41s
Early init                             0.07s
Loader init                            1.64s
Loading error handling                 2.84s
Loading script                        52.01s   ← 最大项
Running init code                      2.90s
Initial gc.                            1.10s
Init translation                       1.53s
Save bytecode.                         0.92s
```

**启动总计约 70 秒**，`Loading script` 占 74%。这是存储卡 I/O 的物理下限，
优化方向只有「减少要加载的条目数」（删无用翻译已验证能省 20 秒）。

### 4.2 运行性能（字体修复前后）

| 场景 | 修复前 | 修复后 |
|---|---|---|
| 进设置（整帧） | 10.23s | **2.76s** |
| 进设置（文字部分） | 9.12s | **1.64s** |
| 再进菜单（整帧） | 8.12s | **2.79s** |
| 单个「开始游戏」 | 2.39s | **0.50s** |

### 4.3 内存占用

| 项 | 大小 |
|---|---|
| 图片缓存上限（**Vita 写死，改不动**） | 25.0 Mpx ≈ 100 MB |
| 字体常驻（6 个） | 28.77 MB |
| 游戏数据 | 124.9 MB |

---

## 五、坑位速查

| 现象 | 原因 | 处理 |
|---|---|---|
| 装到 99% 报 `0x8010113D` | LiveArea PNG 不是 8-bit 索引色 | 铁律 5 |
| 启动即崩 `C2-12828-1` | 缺 `ur0:/data/libshacccg.suprx` | 铁律 4 |
| 停在静态图不动 | 那是 `pic0.png`，引擎没起来 | 看 `log.txt` 有没有 `Set script version to:` |
| 日志缺 `Running init code` | init 里有联网/危险调用 | 铁律 3 |
| `Could not load from archive` | RPA 的 prefix 用了 `str ''` | 铁律 8 |
| 启动卡几分钟 | `renpy/common` 缺 `.rpyc`，现场编译 | 铁律 1 |
| 启动变慢（52s vs 37s） | `renpy/common` 与运行时不一致 | 铁律 21 |
| 改名永久卡死 | `renpy.input()` 在 Vita 上不可用 | 铁律 16 |
| 按键反了 | SDL 的 A/B 位与 PS 布局相反 | `psv_keys.rpy` |
| 菜单卡 10 秒 | 图片没真正降采样 | 铁律 17 |
| 文字卡、且耗时与字数**不成比例** | 字体在 `.rpa` 里被逐字形流式读取 | 铁律 18 |
| 内存吃紧 | `dlc_*.rpa` 里有未子集化的完整字体 | 铁律 20 |

---

## 六、后续优化待办（按性价比排序）

| 优先级 | 项目 | 预期收益 | 状态 |
|---|---|---|---|
| 1 | 子集化 `dlc_japanese` 的 16 MB 字体 | 省 15 MB 内存 + 消掉首次 1.74s | 待做 |
| 2 | GUI 图再降一档（1024×768 → 960×544） | 图片解码 1.01s 可再降 | 待评估 |
| 3 | 减少同屏文本控件（设置页 35 个） | 线性下降 | 需改 screens.rpy |
| 4 | 把 FontAwesome 图标改成图片 | 去掉 `fa.ttf`，省 0.36 MB | 低优先 |
| 5 | 菜单标题描边 4 层 → 1 层 | 5–15%（仅标题） | 视觉有变化，慎用 |

---

## 七、可复用的数字基准

下次移植同类作品时，拿这些数字对照，偏差大就说明有问题：

| 指标 | 健康值 | 危险值 |
|---|---|---|
| `Loading script` | 35–55s | > 90s（可能在现场编译） |
| 进菜单整帧 | < 3s | > 5s |
| 单句台词 | < 0.6s | > 1s |
| `renpy/common` 文件数 | 336 | < 330 |
| 字体总常驻内存 | < 30 MB | > 40 MB |
| `img_resource.rpa` | < 15 MB | > 50 MB（没降采样） |
