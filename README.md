# Ren'Py → PS Vita 移植工具链

把 Ren'Py 游戏移植到 PS Vita 的一套脚本，配套踩坑文档。

适用于 **Ren'Py 7.x（Python 2.7）** → [renpy-vita](https://github.com/SonicMastr/renpy-vita) 运行时。

---

## 这套工具解决什么问题

Ren'Py 游戏直接丢给 Distribution Tool 打包，大概率卡在启动图然后崩。
实测下来，能跑通的包要同时满足：

| 条件 | 为什么 |
|---|---|
| `renpy/common` 里有预编译 `.rpyc` | `app0:` 只读，否则每次启动现场编译 54 个脚本 |
| `script_version.txt` 干净 | 汉化组的水印会让 `ast.literal_eval` 抛异常，兼容层静默失效 |
| 没有 init 阶段的联网代码 | Vita 没有 SSL，requests 必炸 |
| `libshacccg.suprx` 在 `ur0:/data/` | 所有 GL 程序的硬前置 |
| 素材尺寸接近屏幕 | 1920×1440 的 CG 在 330 MB 内存的机器上解码非常慢 |

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

做三件事：
1. 超过框的等比缩到框内
2. alpha 全 255 的 RGBA 转 RGB（省 25% 内存）
3. PNG 用 `optimize` + `compress_level=9` 重存（重存后变大的保留原样）

实测某游戏：144.5 MB → 42.3 MB，单张解码 83.6 ms → 19.4 ms。

> 关键认识：Ren'Py 的 virtual 分辨率决定了像素需求上限。超过的部分
> 只增加解码时间和显存占用，画面上一点都看不出来。

### `fix_script_version.py` — 清 `script_version.txt` 水印

```bash
python fix_script_version.py <游戏目录>            # 只报告
python fix_script_version.py <游戏目录> --write    # 就地修正
```

正常文件 9~11 字节：`(7, 4, 8)\n`。
被污染的会是 32 字节，末尾多一行 GBK 中文。

### `fix_telemetry.py` — 检测首发联网上报

```bash
python fix_telemetry.py <游戏目录>                          # 只检测
python fix_telemetry.py <游戏目录> --write --sdk <SDK路径>   # 生成补丁
```

扫描 `splashscreen.rpyc` 里的 `init -3` 块，命中特征：
`ipinfo.io` / `pipedream` / `stickyrice.work` / `users.cherrykiss.club` /
`requests.get(` / `requests.post(`。

生成 `psv_skip_telemetry.rpyc`，内容是：

```python
init -10 python:
    persistent.data_checked = True
```

`-10` 早于 `-3`，`if not persistent.data_checked` 直接跳过。

**必须用 Ren'Py SDK 编译** —— 手写的 rpyc 版本常量对不上会被拒绝加载。
当前运行时的要求是 `5003000`（`0x4C56F8`）。

### `make_scesys_generic.py` — 生成合规的 LiveArea 素材

```bash
python make_scesys_generic.py <sce_sys目录> <logo.png> [alt.png] "标题"
```

Vita 安装器**只接受 8-bit 索引色 PNG**，否则 `0x8010113D`：

| 文件 | 尺寸 | 要求 |
|---|---|---|
| `icon0.png` | 128×128 | colortype=3, bit=8, 无 alpha |
| `pic0.png` | 960×544 | 同上 |
| `livearea/contents/bg.png` | 840×500 | 同上 |
| `livearea/contents/startup.png` | 280×158 | 可有 alpha |

### 其它

| 脚本 | 用途 |
|---|---|
| `fix_scesys_png.py` | 把已有 PNG 转成 8-bit 索引色 |
| `pack_vpk2.py` | 按规范打包 VPK（param.sfo 优先、全 DEFLATE、ASCII 文件名） |
| `rpa_inspect.py` | 统计 rpa 里的文件数/格式/分辨率/视频 |

---

## 标准流程

```
游戏原始数据
   │
   ├─ fix_script_version.py --write     清 script_version.txt 水印
   ├─ fix_telemetry.py --write --sdk    生成跳过上报的补丁
   ├─ optimize_images.py                降采样素材（性能）
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
   Ren'Py 的日志是行缓冲，真正的崩溃往往发生在最后一行之后几百毫秒。

2. **解 `psp2core-*.psp2dmp`** — gzip 压缩的 ELF core。
   解压后可以直接在内存里搜字符串找线索：

   ```python
   import gzip, re
   d = gzip.decompress(open('psp2core-xxxx.psp2dmp','rb').read())
   for s in re.findall(rb'[\x20-\x7e]{6,}', d):
       if b'http' in s or b'requests' in s:
           print(s)
   ```

   我们就是靠这个在内存里搜到 `ipinfo.io` 才定位到上报块的。

3. **反编译 `.rpyc`** — 用 [unrpyc](https://github.com/CensoredUsername/unrpyc)：

   ```bash
   python unrpyc.py game/*.rpyc
   ```

   直接看 `init` 块里干了什么。

4. **PC 上用同版本 SDK 复现** —

   ```bash
   renpy.exe <project> lint
   ```

   `lint` 会执行 init 代码，异常信息比 Vita 上详细得多。

---

## 关键事实（实测）

* 运行时是 **Ren'Py 7.4.9**，Python 2.7.18
* **7.3.5 和 7.4.8 的游戏都能跑** —— 版本跨度不是问题
* `param.sfo` 用 mksfoex 生成的 **912 字节**就够注册气泡，不必用 1328 字节零售布局
* `renpy/common` 必须是 **336 文件 / 54 个 `.rpyc`** 的那份
* `renpy.py`（6,722 字节）和 `lib/python27.zip`（3,919,486 字节）
  要保持 DistTool 原版，换成别的移植里的版本反而更糟

---

## 已知限制

* 视频播放不支持（renpy-vita 的 C 层限制）
* WebP 是否支持未确认
* 退出游戏会崩（不影响存档）
* 冷启动仍需 40-70 秒（存储卡慢 + rpa 索引解析）

---

## 许可

MIT
