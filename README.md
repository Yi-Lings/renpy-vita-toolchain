# Ren'Py → PS Vita 移植工具链

把 Ren'Py 游戏移植到 PS Vita 的一套脚本，配套踩坑文档、24 条铁律和可复用 skill。

适用于 **Ren'Py 7.x（Python 2.7）** → [renpy-vita](https://github.com/SonicMastr/renpy-vita) 运行时。

**已验证基线**：Angel Sex Pet（Cherry Kiss / cybele，Ren'Py 7.3.5）
— 启动 ~70s、进菜单 **2.76s**、单句台词 **<0.6s**、包 **124.6 MB**、自查 **84/84 PASS**。

---

## 先读这几个

| 文件 | 用途 |
|---|---|
| **[RULES.md](RULES.md)** | **24 条铁律**。每条对应一次真实踩坑，违反任意一条包就起不来 |
| **[skills/renpy-vita-port/SKILL.md](skills/renpy-vita-port/SKILL.md)** | **一次性移植清单**（8 步 + 每步验收），照做即可到位 |
| [docs/移植总结-CherryKiss系.md](docs/移植总结-CherryKiss系.md) | 同类作品手册，含实测基准数字 |
| [docs/性能分析-文字渲染.md](docs/性能分析-文字渲染.md) | 卡顿根因：字体流式 I/O（3.7× 修复） |
| [docs/启动优化计划.md](docs/启动优化计划.md) | 70 秒启动的构成与结论 |
| [docs/移植踩坑总结.md](docs/移植踩坑总结.md) | 完整过程记录，含成功日志 |

---

## 这套工具解决什么问题

Ren'Py 游戏直接丢给 Distribution Tool 打包，大概率卡在启动图然后崩。
实测下来，能跑通的包要同时满足：

| 条件 | 为什么 |
|---|---|
| `renpy/common` 有 54 个预编译 `.rpyc`，且**与运行时逐字节一致** | 否则每次启动现场编译 / 重编译（铁律 1、21） |
| `script_version.txt` 干净（9~11 字节） | 汉化组水印会让 `ast.literal_eval` 抛异常（铁律 2） |
| 没有 init 阶段的联网代码 | Vita 没有 SSL，requests 必炸（17 个游戏里 11 个有，铁律 3） |
| `libshacccg.suprx` 在 `ur0:/data/` | 所有 GL 程序的硬前置（铁律 4） |
| LiveArea PNG 是 **8-bit 索引色** | 否则装到 99% 报 `0x8010113D`（铁律 5） |
| 素材接近屏幕分辨率且用 JPEG | 1920×1440 PNG 解码 139ms，1024×768 JPEG 只要 5.2ms（铁律 10、17） |
| **字体整块读入内存** | 否则文字渲染慢 3.7 倍（铁律 18） |

---

## 工具

### 打包与校验

#### `build_package.py` — 打成可安装的包

```bash
python build_package.py --build <运行时目录> --game <game目录> \
    --out dist --title-id ANGE00001
```

产出 `X_Runtime.vpk`（14 MB，可公开）、`X_Full.vpk`（含数据，勿公开）、`X_NoNpDrm.zip`。

#### `selfcheck_package.py` — **发版前 84 项自查**（铁律 22）

```bash
python selfcheck_package.py \
    --vpk dist/X_Full.vpk --runtime dist/X_Runtime.vpk \
    --ref-common G:/app/<TITLE_ID>/renpy/common
```

必须看到 `RESULT: PASS`。覆盖 LiveArea 格式、VPK 三条规则、`pic0` 尺寸、
`.rpyc` 预编译、`script_version` 干净、RPA 可读、原版尺寸、`renpy/common` 逐字节一致。

**跑一次 10 秒，远比装一次机器便宜。**

#### `make_scesys_generic.py` / `fix_scesys_png.py` / `pack_vpk2.py`

```bash
python make_scesys_generic.py <sce_sys目录> <logo.png> [alt.png] "标题"
```

`fix_scesys_png.py` 把已有 PNG 转 8-bit 索引色；`pack_vpk2.py` 按规范打包
（param.sfo 优先、全 DEFLATE、ASCII 文件名）。

### 归档

#### `rpa_tool.py` — 读写 `.rpa`

```bash
python rpa_tool.py list    game/archive.rpa
python rpa_tool.py extract game/archive.rpa out/
python rpa_tool.py pack    out/ new.rpa
python rpa_tool.py filter  game/archive.rpa opt.rpa --drop 'tl/en/,tl/es/'
```

**三个必须知道的坑**（之前所有实现都失败的原因）：

1. **index 里 `prefix` 必须用 `bytes b''`，不能用 `str ''`**
   Ren'Py 的 `loader.SubFile.read()` 做 `self.start[0:n] + 文件字节`；
   Py3 的 `str ''` pickle 后在 Py2 里是 `u''`，`u'' + 二进制` 会走 unicode 解码 →
   **数据被破坏**。报错是 `Could not load from archive xxx.rpyc.`，完全看不出原因。
2. **offset 和 length 都要 XOR key** —— 标准只 XOR offset，这个合集两个都 XOR。
3. **index 用 pickle protocol 2**。

#### `slim_archives.py` — 删运行时永不读取的死重

```bash
python slim_archives.py --rpa game/archive.rpa --rpa game/dlc_japanese.rpa
python slim_archives.py --rpa game/archive.rpa --dry-run
```

删两类东西，都有源码依据：

- `.rpy` 源码 —— `script.py:238-242`：归档来的 `.rpy` 直接 `continue`
- `python-packages/`（requests/urllib3/chardet）—— 只被上报用，而上报已被补丁挡住

实测：`archive.rpa` 4.98 → **1.78 MB**。

#### `rpa_inspect.py` / `rpa_extract.py`

统计 rpa 里的文件数/格式/分辨率/视频；或提取指定文件。

### 素材

#### `jpeg_recompress.py` — 降采样 + 转 JPEG（**必须一条命令**，铁律 17）

```bash
python jpeg_recompress.py <src.rpa> <dst.rpa> --quality 88 --max-w 1366 --max-h 768
```

实测同一张 1024×768：

| 格式 | 体积 | 解码 |
|---|---|---|
| PNG | 862 KB | **139.5 ms** |
| JPEG q85 | 131 KB | **5.2 ms** |

**体积 15%，解码快 27 倍。** 保留 `.png` 文件名即可 ——
SDL_image 按内容嗅探，不看扩展名（已实测验证）。

#### `optimize_images.py` — 只降采样（不转格式）

```bash
python optimize_images.py game/img_resource.rpa game/img_opt.rpa --max-w 1366 --max-h 768
```

> ⚠ 和 `jpeg_recompress.py` 分两步做容易漏掉降采样。**优先用后者一次做完。**

#### `subset_font.py` — CJK 字体子集化

```bash
python subset_font.py 原字体.otf 输出.otf --charset charset.txt
```

字符集三层齐全：脚本用字 ∪ GB2312 全字库 ∪ ASCII/Latin-1/假名。
实测 17.3 MB → 4.1 MB。

⚠ **必须扫所有 rpa，包括 `dlc_*.rpa`**（铁律 20）。

### 体检

#### `fix_script_version.py` — 清 `script_version.txt` 水印

```bash
python fix_script_version.py <游戏目录>            # 只报告
python fix_script_version.py <游戏目录> --write    # 就地修正
```

#### `fix_telemetry.py` — 检测并跳过首发联网上报

```bash
python fix_telemetry.py <游戏目录>                          # 只检测
python fix_telemetry.py <游戏目录> --write --sdk <SDK路径>   # 生成补丁
```

---

## 运行时补丁（`patches/`，全部预编译）

| 补丁 | 作用 | 不加会怎样 |
|---|---|---|
| `psv_skip_telemetry.rpyc` | 跳过首发联网上报 | 启动即崩 |
| `psv_input.rpyc` | 引擎内屏幕键盘替换 `renpy.input()` | 改名**永久卡死** |
| `psv_perf.rpyc` | 性能配置 | 卡顿加重 |
| `psv_fontmem.rpyc` | **字体整块读入内存** | 文字渲染慢 **3.7 倍** |
| `psv_keys.rpyc` | ○ 确认 / × 返回 | 按键与 PS 习惯相反 |
| `psv_diag.rpyc` | 性能探针（**不进发布包**） | — |

---

## 标准流程

```
游戏原始数据
   │
   ├─ fix_script_version.py --write     清 script_version.txt 水印
   ├─ fix_telemetry.py --write --sdk    生成跳过上报的补丁
   ├─ jpeg_recompress.py                降采样 + 转 JPEG（一条命令，收益最大）
   ├─ subset_font.py                    CJK 字体子集化（扫所有 rpa）
   ├─ slim_archives.py                  删 .rpy / python-packages
   │
   ▼
game/
   ├─ *.rpa（优化后）
   ├─ psv_skip_telemetry.rpyc / psv_input.rpyc
   ├─ psv_perf.rpyc / psv_fontmem.rpyc / psv_keys.rpyc
   └─ script_version.txt
   │
   ▼  配上运行时（eboot/renpy.py/lib/module/renpy-common）+ sce_sys
   │  ⚠ renpy/common 必须从能跑的设备整目录复制
   ▼
build_package.py  →  X_Runtime.vpk / X_Full.vpk / X_NoNpDrm.zip
   │
   ▼
selfcheck_package.py  →  必须 RESULT: PASS（84 项）
   │
   ▼
VitaShell 安装 → 气泡出现 → 启动 → 读 log.txt 验证
```

---

## 诊断：怎么定位崩溃点

1. **`pic0.png` 鉴别** —— 把 `game/` 改名再启动。图还在 = 运行时问题；图没了 = 数据问题。
2. **读 `log.txt`** —— 最后一行是最后被 flush 的内容，**不是崩溃点**。
3. **解 `psp2core-*.psp2dmp`** —— gzip 压缩的 ELF core：

   ```python
   import gzip, re
   d = gzip.decompress(open('psp2core-xxxx.psp2dmp','rb').read())
   for s in re.findall(rb'[\x20-\x7e]{6,}', d):
       if b'http' in s or b'requests' in s:
           print(s)
   ```

4. **反编译 `.rpyc`** —— [unrpyc](https://github.com/CensoredUsername/unrpyc)。
5. **PC 上用同版本 SDK 复现** —— `renpy.exe <project> lint`，会执行 init 代码。

**常见误判**：日志停在 `Importing _renpysteam` 之后没有 `Set script version to:`，
看起来像崩在那行 —— 其实那行只是没打出来（铁律 2）。

---

## 性能：先测，再改

探针见 `patches/psv_diag.rpy`。**不要靠感觉，也不要靠读代码推理**（铁律 12）。

| 现象 | 结论 | 动作 |
|---|---|---|
| `text=` 占整帧 85%+ | **文字渲染是瓶颈** | `psv_fontmem`（铁律 18） |
| `text=` 耗时与字数**不成比例** | 字体被逐字形流式读取 | 同上 |
| `get=` 占 30%+ | 图片解码 | `jpeg_recompress`（铁律 10、17） |
| `RENDER` 单次几秒，固定在进菜单 | 界面首次构建 | 查该界面背景图尺寸 |

⚠ **不要调 `config.image_cache_size_mb`** —— Vita 的 `Cache.init()`
第一行就写死 `26214400`（25.0 Mpx），你写的值走不到（铁律 9）。

⚠ **不要开 `config.cache_surfaces`** —— Surface 和纹理计入同一上限，能装的图少一半。

⚠ **不要动音频**（铁律 23）。

---

## 关键事实（实测）

* 运行时是 **Ren'Py 7.4.9.0u**，Python 2.7.18
* **7.3.5 和 7.4.8 的游戏都能跑** —— 版本跨度不是问题
* `param.sfo` 用 mksfoex 的 **912 字节**就够注册气泡
* `renpy/common` 必须是 **336 文件 / 54 `.rpyc` / 15 `.rpymc`**，且与运行时**逐字节一致**
* `renpy.py`（6,722 B）、`lib/python27.zip`（3,919,486 B）、
  `eboot.bin`（7,732,057 B）保持 DistTool 原版
* 稳态帧率约 20 FPS（PowerVR SGX 543MP + 444MHz CPU 的上限）
* 冷启动 **50–70 秒**，其中 `Loading script` 占 73%，是纯 CPU 的 AST 反序列化

---

## 已知限制（都是运行时层面的，不要试图在脚本层修）

| 限制 | 说明 |
|---|---|
| 视频播放不支持 | renpy-vita 的 C 层限制 |
| WebP 是否支持未确认 | 移植前先扫素材 |
| **退出时卡死** | SDL/GL 拆卸阶段的老问题，不影响存档。**不要深究**（铁律 24） |
| 稳态 20 FPS | PowerVR SGX 543MP + 444MHz 的渲染上限 |
| 冷启动 50–70 秒 | AST 反序列化的物理下限（见 `docs/启动优化计划.md`） |

---

## 许可

MIT
