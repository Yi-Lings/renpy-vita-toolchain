# Ren'Py → PS Vita 移植工具链

把 Ren'Py 游戏移植到 PS Vita 的一套脚本，配套踩坑文档、铁律和可复用 skill。

适用于 **Ren'Py 7.x（Python 2.7）** → [renpy-vita](https://github.com/SonicMastr/renpy-vita) 运行时。

---

## 先读这三个

| 文件 | 用途 |
|---|---|
| **[RULES.md](RULES.md)** | **15 条铁律**。每条对应一次真实踩坑，违反任意一条包就起不来 |
| **[skills/renpy-vita-port/SKILL.md](skills/renpy-vita-port/SKILL.md)** | 可复用的移植 skill，给 AI agent 或自己按步骤执行 |
| [docs/移植踩坑总结.md](docs/移植踩坑总结.md) | 完整过程记录，含成功日志与数据 |

---

## 这套工具解决什么问题

Ren'Py 游戏直接丢给 Distribution Tool 打包，大概率卡在启动图然后崩。
实测下来，能跑通的包要同时满足：

| 条件 | 为什么 |
|---|---|
| `renpy/common` 里有 54 个预编译 `.rpyc` | `app0:` 只读，否则每次启动现场编译 |
| `script_version.txt` 干净（9~11 字节） | 汉化组水印会让 `ast.literal_eval` 抛异常，兼容层静默失效 |
| 没有 init 阶段的联网代码 | Vita 没有 SSL，requests 必炸（17 个游戏里 11 个有） |
| `libshacccg.suprx` 在 `ur0:/data/` | 所有 GL 程序的硬前置 |
| 素材尺寸/格式接近屏幕 | 1920×1440 PNG 解码 139ms，JPEG 只要 5.2ms |

---

## 工具

### `rpa_tool.py` — 读写 `.rpa` 归档

```bash
python rpa_tool.py list    game/archive.rpa
python rpa_tool.py extract game/archive.rpa out/
python rpa_tool.py pack    out/ new.rpa
python rpa_tool.py filter  game/archive.rpa opt.rpa --drop 'tl/en/,tl/es/'
```

**三个必须知道的坑**（这也是之前所有实现都失败的原因）：

1. **index 里 `prefix` 必须用 `bytes b''`，不能用 `str ''`**

   Ren'Py 的 `loader.SubFile.read()` 会做 `self.start[0:n] + 文件字节`。
   Python 3 的 `str ''` pickle 后在 Py2 里是 `u''`，`u'' + 二进制`
   会走 unicode 解码 → **数据被破坏**。
   报错是 `Exception: Could not load from archive xxx.rpyc.`，
   完全看不出跟 prefix 有关。

2. **offset 和 length 都要 XOR key**

   标准 RPA-3.0 只 XOR offset，但这个合集（Cherry Kiss / Miel）的包
   把 length 也 XOR 了。Ren'Py 的 `read_index` 两个都 XOR，照做即可。

3. **index 用 pickle protocol 2**

   Py2 能直接读，不需要手写 pickle opcode。

### `optimize_images.py` — 降采样素材

```bash
python optimize_images.py game/img_resource.rpa game/img_opt.rpa --max-w 1366 --max-h 768
python optimize_images.py game/img_resource.rpa game/img_opt.rpa --dry-run   # 只统计
```

超过框的等比缩到框内；alpha 全 255 的 RGBA 转 RGB；PNG 重压。
实测：144.5 MB → 42.3 MB，单张解码 83.6 ms → 19.4 ms。

### `jpeg_recompress.py` — 不透明图转 JPEG（收益最大）

```bash
python jpeg_recompress.py <src.rpa> <dst.rpa> --quality 85
python jpeg_recompress.py <src.rpa> <dst.rpa> --dry-run
```

实测同一张 1024×768：

| 格式 | 体积 | 解码 |
|---|---|---|
| PNG | 862 KB | **139.5 ms** |
| JPEG q85 | 131 KB | **5.2 ms** |

**体积 15%，解码快 27 倍。** 保留 `.png` 文件名即可 ——
SDL_image 按内容嗅探，不看扩展名（已实测验证）。

### `subset_font.py` — CJK 字体子集化

```bash
python subset_font.py 原字体.otf 输出.otf --charset charset.txt
```

字符集必须三层齐全：脚本用字 ∪ GB2312 全字库 ∪ ASCII/Latin-1/假名。
实测 17.3 MB → 4.1 MB（省 76%）。

### `fix_script_version.py` — 清 `script_version.txt` 水印

```bash
python fix_script_version.py <游戏目录>            # 只报告
python fix_script_version.py <游戏目录> --write    # 就地修正
```

### `fix_telemetry.py` — 检测首发联网上报

```bash
python fix_telemetry.py <游戏目录>                          # 只检测
python fix_telemetry.py <游戏目录> --write --sdk <SDK路径>   # 生成补丁
```

### `build_package.py` — 打成可安装的包

```bash
python build_package.py --build <运行时目录> --game <game目录> \
    --out dist --title-id ANGE00001
```

产出 `X_Runtime.vpk`（14 MB，可公开）、`X_Full.vpk`（含数据，勿公开）、
`X_NoNpDrm.zip`。

### `make_scesys_generic.py` — 生成合规的 LiveArea 素材

```bash
python make_scesys_generic.py <sce_sys目录> <logo.png> [alt.png] "标题"
```

### 其它

| 脚本 | 用途 |
|---|---|
| `fix_scesys_png.py` | 把已有 PNG 转成 8-bit 索引色 |
| `pack_vpk2.py` | 按规范打包 VPK（param.sfo 优先、全 DEFLATE、ASCII 文件名） |
| `rpa_inspect.py` | 统计 rpa 里的文件数/格式/分辨率/视频 |
| `rpa_extract.py` | 从 rpa 提取指定文件 |

---

## 标准流程

```
游戏原始数据
   │
   ├─ fix_script_version.py --write     清 script_version.txt 水印
   ├─ fix_telemetry.py --write --sdk    生成跳过上报的补丁
   ├─ optimize_images.py                降采样素材（性能）
   ├─ jpeg_recompress.py                不透明图转 JPEG（性能，收益最大）
   ├─ subset_font.py                    CJK 字体子集化（内存）
   ├─ rpa_tool.py filter                删无用翻译（启动速度）
   │
   ▼
game/
   ├─ *.rpa（优化后）
   ├─ psv_skip_telemetry.rpyc
   ├─ psv_perf.rpyc
   └─ script_version.txt
   │
   ▼  配上运行时（eboot/renpy.py/lib/module/renpy-common）+ sce_sys
VPK（只含运行时，约 14 MB）
   │
   ▼  VitaShell 安装 → 气泡出现
USB 拷 game/*.rpa → ux0:/app/TITLEID/game/
   │
   ▼
启动，读 ux0:/app/TITLEID/log.txt 验证
```

---

## 诊断：怎么定位崩溃点

1. **读 `log.txt`** — 最后一行是最后被 flush 的内容，**不是崩溃点**。

2. **解 `psp2core-*.psp2dmp`** — gzip 压缩的 ELF core：

   ```python
   import gzip, re
   d = gzip.decompress(open('psp2core-xxxx.psp2dmp','rb').read())
   for s in re.findall(rb'[\x20-\x7e]{6,}', d):
       if b'http' in s or b'requests' in s:
           print(s)
   ```

3. **反编译 `.rpyc`** — 用 [unrpyc](https://github.com/CensoredUsername/unrpyc)。

4. **PC 上用同版本 SDK 复现** — `renpy.exe <project> lint`，会执行 init 代码。

---

## 关键事实（实测）

* 运行时是 **Ren'Py 7.4.9**，Python 2.7.18
* **7.3.5 和 7.4.8 的游戏都能跑** —— 版本跨度不是问题
* `param.sfo` 用 mksfoex 的 **912 字节**就够注册气泡
* `renpy/common` 必须是 **336 文件 / 54 个 `.rpyc`**
* `renpy.py`（6,722 字节）和 `lib/python27.zip`（3,919,486 字节）保持 DistTool 原版

---

## 已知限制

* 视频播放不支持（renpy-vita 的 C 层限制）
* WebP 是否支持未确认
* 退出游戏会崩（不影响存档）
* 稳态帧率约 20 FPS（PowerVR SGX 543MP + 444MHz CPU 的渲染上限）
* 冷启动 50-70 秒（存储卡慢 + 300 MB rpa 索引解析）

---

## 许可

MIT
