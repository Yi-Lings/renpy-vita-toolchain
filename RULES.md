# Ren'Py → PS Vita 移植铁律

> 从 2026-10-30/31 两天、17 个游戏、几十次真机崩溃里提炼出来的。
> 每条都对应一次真实的踩坑。**违反任意一条，包就起不来。**

---

## 零、先记住这个判断顺序

遇到"卡在启动图 / 启动崩溃"，**按这个顺序查，不要跳步**：

```
1. pic0 改名测试        → 分清「引擎没起来」还是「游戏数据有问题」
2. log.txt 最后一行      → 只是最后 flush 的内容，不是崩溃点
3. 崩溃 dump 里搜字符串  → 真正的线索在这里
4. 反编译 rpyc          → 看 init 块干了什么
5. PC 上 SDK 复现        → 异常信息最详细
```

---

## 铁律 1｜`renpy/common` 必须含预编译 `.rpyc`

**症状**：卡在启动图几分钟然后崩。

**原理**：`app0:` 只读，Ren'Py 写不回编译产物。DistTool 自带的
`renpy/common` 只有 54 个 `.rpy`、**0 个 `.rpyc`**，于是每次启动都要在
Vita 上现场编译 54 个脚本。

**铁律**：`renpy/common` 必须是 **336 个文件 / 54 个 `.rpyc`** 那一份。

**验证**：

```bash
find renpy/common -name '*.rpyc' | wc -l    # 必须是 54
```

---

## 铁律 2｜`script_version.txt` 必须干净

**症状**：日志里**永远不出现** `Set script version to:`，但没有报错。

**原理**：Ren'Py 用 `ast.literal_eval` 读**整个文件**：

```python
with renpy.file("script_version.txt") as f:
    script_version = f.read()
config.script_version = ast.literal_eval(script_version)
```

汉化组在末尾追加了一行 GBK 中文（`更多资源:SEEACG.COM`），
整个文件变成 32 字节，`literal_eval` 直接 `SyntaxError`，
而外面包着 `except: pass` —— **静默失败**。

**铁律**：`script_version.txt` 只能是 `(7, 3, 5)\n` 这种 9~11 字节。

**验证**：

```bash
wc -c game/script_version.txt      # 必须 <= 12
cat  game/script_version.txt       # 必须只有一行元组
```

**附带教训**：不要因为「日志停在 X 之后」就断定「崩在 X」。
那行可能根本没打出来。

---

## 铁律 3｜`init` 里不能有联网代码

**症状**：日志停在 `Running init code` 之前，`traceback.txt` 不存在，
生成 `psx2core-*.psp2dmp` 但看不出原因。

**原理**：发行商在 `splashscreen.rpy` 里塞了遥测：

```python
init -3 python:
    if not persistent.data_checked:
        import requests
        userdata = requests.get('http://ipinfo.io/json').json()
        requests.post('http://<厂商端点>', data=userdata)
```

Vita 的 `python27.zip` 里没有 `_ssl`、没有 certifi，`app0:` 又只读 ——
未捕获异常直接把 init 打死。

**铁律**：**任何 `init` 阶段的网络/文件/子进程调用都是致命伤。**

**检测**：扫描 `splashscreen.rpyc`，找 `ipinfo.io` / `pipedream` /
`stickyrice.work` / `users.cherrykiss.club` / `requests.get(`。

**修法**：加更高优先级的 init 抢先置位：

```python
init -10 python:
    persistent.data_checked = True
```

**注意**：补丁 `.rpyc` **必须用 Ren'Py SDK 编译**，版本常量必须是
`5003000`，手写的会被拒绝加载。

**这个坑命中率极高**：实测 17 个 Cherry Kiss / Miel / norn 游戏里
**11 个**有同样代码，只是端点不同。

---

## 铁律 4｜`libshacccg.suprx` 必须在 `ur0:/data/`

**症状**：任何 GL 程序启动即崩 `C2-12828-1`。

**铁律**：装 `VitaDB-Downloader.vpk` 一键装，**装完必须重启**。

这是 HardRPG 和 renpy-vita **共同**的前置，排查时最容易漏。

---

## 铁律 5｜LiveArea 图片必须是 8-bit 索引色

**症状**：安装走到 **99%** 失败，错误码 `0x8010113D`。

**硬性规格**：

| 文件 | 尺寸 | colortype | bit | alpha |
|---|---|---|---|---|
| `icon0.png` | 128×128 | 3 | 8 | 不可有 |
| `pic0.png` | **960×544** | 3 | 8 | 不可有 |
| `livearea/contents/bg.png` | 840×500 | 3 | 8 | 不可有 |
| `livearea/contents/startup.png` | 280×158 | 3 | 8 | 可有 |

- 必须非交错（interlace=0）
- 文件名是 `bg.png`，**不是** `bg0.png`
- `pic0.png` 尺寸错一点就失败

```python
img.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT).save(p, "PNG", optimize=True)
```

---

## 铁律 6｜VPK 打包三条

1. **路径必须正斜杠** —— .NET 的 `CreateFromDirectory` 会写成 `game\demo.rpa`，VitaShell 不认。用 Python `zipfile`。
2. **`sce_sys/param.sfo` 必须是第一个条目**。
3. **文件名纯 ASCII** —— 带中文的 VPK 名字装不上。

---

## 铁律 7｜`pic0.png` 不是游戏画面

停在某张静态图 = **引擎根本没启动**，不是游戏卡住。

**10 秒鉴别法**：把 `game/` 改名再启动。
- 图还在 → 是 `pic0.png`，问题在运行时
- 图没了 → 是引擎画的，问题在游戏数据

这个测试能一刀切开两类问题，比猜快得多。

---

## 铁律 8｜RPA 重打包：`prefix` 必须用 `bytes`，不是 `str`

**症状**：`Exception: Could not load from archive xxx.rpyc.`
完全看不出跟 prefix 有关。

**原理**：Ren'Py 的 `loader.SubFile.read()` 会做
`self.start[0:n] + 文件字节`。Python 3 的 `str ''` pickle 后在 Py2 里是
`u''`，`u'' + 二进制` 走 unicode 解码 → **数据被破坏**。

**铁律**：

```python
idx[name] = [(off ^ key, len(data) ^ key, b"")]   # b'' 不是 ''
```

另外两个必须遵守：

- **offset 和 length 都要 XOR key**（标准 RPA-3.0 只 XOR offset，
  但这个合集两个都 XOR）
- **pickle 用 protocol 2**（Py2 能直接读，不用手写 opcode）

---

## 铁律 9｜图片缓存宁大勿小

**症状**：按钮响应从几秒恶化到 15 秒。

**原理**：`config.image_cache_size_mb` 是**上限不是预留**。
调小 → 装不下工作集 → 每次交互都「淘汰 → 重读 → 重解 → 重传」。

**铁律**：

```python
config.image_cache_size_mb = 192    # 不要低于 128
config.predict_statements  = 32     # 不要调小
```

「内存小所以要设小缓存」是**反直觉的错误**。

### 9.1 ⚠ 但在 Vita 上这个配置**根本不生效**（2026-10-31 反汇编确认）

反汇编 `lib/python27.zip` 里的 `renpy/display/im.pyo`，`Cache.init()` 是：

```python
def init(self):
    if renpy.vita:
        self.cache_limit = int(26214400)          # ← 写死 25.0 Mpx = 100 MB
    elif renpy.config.image_cache_size is not None:
        self.cache_limit = 2 * config.image_cache_size * sw * sh
    else:
        self.cache_limit = int(config.image_cache_size_mb * 1024 * 1024 // 4)
```

**Vita 分支排在最前面**，所以无论你写 64、192 还是 300，日志里永远是

```
PSV CFG: cache_mb=192 cache_size=None limit=25.0Mpx ...
```

`limit=25.0Mpx` = `26214400 / 1024 / 1024 = 25.0`，正是那个常量。

**怎么验证**：日志里 `limit` 永远是 25.0Mpx 就说明你命中的是这个分支。
想确认自己的补丁有没有生效，只能看 `cache_mb=` 后面的值变了没有——
但那个值对缓存上限**没有任何影响**。

**结论**：在 Vita 上优化缓存只有两条路——
1. **减小每张图的像素数**（降采样）→ 同样的 25Mpx 能装更多张
2. **减小每张图的解码开销**（PNG → JPEG）→ 淘汰后重解的代价低 27 倍

⚠ **不要开 `config.cache_surfaces = True`。** 默认 `False` 时，纹理上传到
GPU 后 Ren'Py 会丢掉解码出来的 Surface（`im.py:332-337`）；改成 `True`
会同时保留 Surface 和解码纹理，两者都计入 `CacheEntry.size()`
（`width*height + bounds`）—— 同一个 25Mpx 上限下能装的图**少一半**。
PC 内存充足时这是个好开关，Vita 上不是。

---

## 铁律 10｜图片格式比分辨率重要得多

实测同一张 1024×768：

| 格式 | 体积 | 解码 |
|---|---|---|
| PNG（optimize + level 9） | 862 KB | **139.5 ms** |
| JPEG q85 | 131 KB | **5.2 ms** |

**体积 15%，解码快 27 倍。**

**铁律**：不透明的图一律转 JPEG。可以保留 `.png` 文件名 ——
**SDL_image 按内容嗅探格式，不看扩展名**（已实测验证）。

顺序不能反：**先降采样，再转 JPEG**。

---

## 铁律 11｜CJK 字体必须子集化

**症状**：包体积虚高、内存吃紧、文字渲染慢。

**原理**：SourceHanSansSC 三个字重各 17 MB（4 万多个字形），
游戏实际只用 8000 多个。

**铁律**：字符集必须三层齐全，少一层就出方框：

1. **脚本实际用字**（含 `tl/` 下所有语言 + **DLC 的 rpa**）
2. **GB2312 全字库**（玩家名输入等动态文本）
3. **ASCII + Latin-1 + 中日标点 + 假名**

**教训**：第一次只扫了 `archive.rpa`，漏掉 `dlc_japanese.rpa` 里的日文，
结果「隷」字变成方框 —— 而那是游戏标题里的字。

**验证**：遍历整个字符集，确认 `cmap` 全覆盖，不能只抽查。

---

## 铁律 12｜诊断要测「帧」，不是「交互间隔」

### 12.1 第一层坑：`interact_callbacks` 测的是玩家思考时间

**踩过的坑**：用 `config.interact_callbacks` 测卡顿 —— 它在交互
**开始**时调用，测出来的是「两次交互之间的时间」，**包含玩家看屏幕的时间**。
数据完全没意义。

### 12.2 ⚠ 一次被实验推翻的错误结论（写在这里防止再犯）

**我一度认为**：`periodic_callbacks` 在等待输入时不跑，因为 interact 循环
阻塞在 `event_wait()`（`core.py:3965`），所以测出来的「1.7 秒卡顿」
其实是玩家读台词的时间。

**这个结论是错的。** 用一个最小工程实测（显示静态界面，完全不操作）：

```
PTEST calls=198 in 10.0s maxgap=0.052s
```

**10 秒内回调 198 次，最大间隔 52 ms。** pygame 的 timer 事件会正常唤醒
`event_wait()`，回调照跑。

**教训**：

> 涉及「引擎某段代码到底跑不跑」的判断，必须写最小工程实测，
> 不能靠读代码推理。我读了 `event_wait()` 就下结论，结果推翻了自己，
> 而且用这个错误结论把用户真实的卡顿说成"假的"。

**正确的态度**：探针读数可疑时，应该说"这个数可能不准，我换个测法确认"，
而不是"你的卡顿不存在"。

**真正该怀疑的是**：`periodic_callback` 的间隔确实是主线程是否被占住的
可靠指标。间隔 1.7 秒 = 主线程真的被占了 1.7 秒。
问题只在于**不知道占在哪一段**——解决办法是分包住各个函数（见 12.3）。

### 12.3 分包各阶段，直接测「操作延迟」

用户说的卡顿几乎都是**操作卡顿**（按键 → 响应）。对应引擎里这条链：

```
事件入队 → interact 返回 → 新屏幕构建 → render → draw+flip
```

每一段单独计时，才能知道卡在哪。`patches/psv_diag.rpy` (v6) 的实现：

| 标签 | 包住谁 |
|---|---|
| `LATENCY` | 按键时刻 → 下一帧画完（**用户感知的响应时间**） |
| `SCREEN` | `ScreenDisplayable.update`（界面重建） |
| `IMG` | `im.cache.get`（图片解码） |
| `RENDER` | `render.render_screen`（文字排版+布局） |
| `DRAW+FLIP` | `draw.draw_screen`（GL 提交+flip） |
| `IDLE` | `Interface.idle_frame`（空闲期预加载/GC） |
| `GC` | `gc.collect` |

⚠ 注意 `renpy.display.draw` 在 `init` 阶段还是 `None`，纹理上传的探针
必须延迟到第一次交互时再装，否则会报
`AttributeError: 'NoneType' object has no attribute 'ready_one_texture'`。

---

## 铁律 12b｜`config.periodic_callbacks` 的间隔 ≈ 主线程忙闲晴雨表

补一条上面没写透的：

```python
# renpy/display/core.py:4013   PERIODIC 事件处理
if ev.type == PERIODIC:
    for i in renpy.config.periodic_callbacks:
        i()
```

`PERIODIC` 由 `pygame.time.set_timer(PERIODIC, 50)` 产生，50ms 一次。
**实测 idle 时它照常执行**（10 秒 198 次，最大间隔 52ms）。

所以：**回调间隔超过 50ms 的部分，就是主线程被别的东西占住的时间。**
这是个免费的「主线程阻塞探测器」——间隔 1.7 秒 = 真的卡了 1.7 秒。

但它只能告诉你「什么时候卡了」，不能告诉你「卡在哪」。
要定位得再分包各函数（见 12.3）。

---

## 铁律 13｜崩溃 dump 是第一手证据

`ux0:/data/psp2core-*.psp2dmp` 是 **gzip 压缩的 ELF core**。

```python
import gzip, re
d = gzip.decompress(open('psp2core-xxxx.psp2dmp','rb').read())
for s in re.findall(rb'[\x20-\x7e]{6,}', d):
    if b'http' in s or b'requests' in s:
        print(s)
```

我们就是靠这个在内存里搜到 `ipinfo.io`，才定位到遥测块的。

其他可看的 note 段：`MODULE_INFO`（加载了哪些模块）、
`THREAD_REG_INFO`（寄存器）、`TTY_INFO2`（stdout/stderr）。

---

## 铁律 14｜PC 上用同版本 SDK 复现

```bash
renpy.exe <project> lint
```

`lint` 会**执行 init 代码**，异常信息比 Vita 上详细得多。
这是最快的验证手段 —— 改一行配置，几秒就能知道对不对。

**必须用同版本 SDK**（7.4.9），否则行为不一致。

---

## 铁律 15｜不要试图文件夹直拷注册气泡

在 3.65 变革上验证过**两次**都失败。

**正确做法：拆开装**

1. 打一个只含运行时的 VPK（约 14 MB），VitaShell 安装 → 气泡和 `app.db` 记录都有了
2. 用 USB 把 `game/*.rpa` 直接拷到 `ux0:/app/TITLEID/game/`

---

## 铁律 16｜`renpy.input()` 在 Vita 上必卡死

**症状**：设置里点「改名 / Change Name」后整个游戏冻结，按键无反应，只能强退。

**原理**：`renpy.input()` 会走 SDL 的文本输入（Vita 上是系统输入法 / IME）。
renpy-vita 的 SDL 移植没有实现这条路，事件循环永远等不到 `TEXTINPUT` 事件，
于是永久阻塞。

**铁律**：**任何 `renpy.input()` 调用都必须替换成引擎内的屏幕键盘。**

`patches/psv_input.rpy` 提供了一个可直接用的实现：

```python
init 999 python:
    if not getattr(renpy, "_psv_input_patched", False):
        renpy.input = psv_input      # psv_input 用 renpy.call_screen("psv_keyboard")
        renpy._psv_input_patched = True
```

配套的 `screen psv_keyboard` 提供 A–Z / 0–9 / 空格 / 删除 / 清空 / 确定 /
取消，外加常用名字快捷按钮，完全不碰系统输入法。

外层要包 `try/except` 并返回 `default`，保证任何意外都不会把游戏锁死。

---

## 铁律 17｜降采样和转 JPEG 必须同一个工具一次做完

**症状**：明明跑过「图片优化」，日志里还是动辄 10 秒的菜单卡顿。

**实际案例（2026-10-31）**：上一轮优化分两步做——

```
1. optimize_images.py   → 降采样 1920x1440 → 1024x768
2. jpeg_recompress.py   → PNG → JPEG
```

但第二步是从**已经被重新打包过的 rpa** 上再跑的，而 `gui_resource.rpa`
里的

```
gui/main_menu.png    1920x1440 RGB   2.0 MB
gui/game_menu.png    1920x1440 RGB   412 KB
gui/disclaimer.png   1920x1440 RGBA  308 KB
```

只走了 JPEG、**没走降采样**（`optimize_images` 的 `max-w/max-h` 忘了传，
或者跑的是另一个目录）。结果这三张图仍然是 1920×1440，只是换成了 JPEG。
而游戏里写死了 `size=(1024, 768)`：

```python
image main_menu = Transform("gui/main_menu.png", size=(1024, 768))
image game_menu = Transform("gui/game_menu.png", size=(1024, 768))
image disclaim_idle = Transform("gui/disclaimer.png", size=(1024, 768))
```

**解码一张 1920×1440 RGBA = 11 MB**，缩到 1024×768 之后只剩 3 MB。
每次进主菜单都要重解这三张 → 10 秒卡顿。

**铁律**：

> **降采样和转 JPEG 必须在同一个命令里一次完成。**
> 分成两步跑，第二步很容易建立在第一步的产物上，而漏掉真正的原图。

`jpeg_recompress.py` 已经加了 `--max-w/--max-h`：

```bash
python jpeg_recompress.py <src.rpa> <dst.rpa> \
    --quality 88 --max-w 1366 --max-h 768
```

**验证方法（必须做）**：打开产物 rpa，逐张检查**解码后的像素数**，
不是看文件大小：

```python
for name, data in iter_rpa('gui_resource.rpa'):
    im = Image.open(io.BytesIO(data))
    if im.width > 1400 or im.height > 800:
        print('漏了!', name, im.size)
```

文件大小会骗人（JPEG 小但像素多），**像素数不会**。

---

## 铁律 18｜文字渲染慢，先怀疑「字体在 .rpa 里被流式读取」

**症状**：文字渲染占 90%+ 的卡顿时间，而且**耗时与文字长度不成比例**——
`1.3.2` 五个 ASCII 字符要 0.56 秒，一句 32 字台词要 1.5 秒。

**实测（Angel Sex Pet，2026-11-01）**：

```
PSV FRAME 10.23s | get=8(miss=5) 1.01s | text=10 9.12s | tex=0 0.00s
PSV TEXT   0.56s size=16  '1.3.2'
PSV TEXT   2.39s size=24  '开始游戏'
PSV TEXT   3.45s size=22  '圣天使夏洛…'
```

在 PC 上用同一个 FreeType 实测同款字体：**0.039 ms/字**。
按 Vita CPU 慢 50 倍折算也只有 2 ms/字，实测是 112–598 ms/字 —— **差 50–300 倍**。

**任何「光栅化慢」的解释都填不平这个差距。差距来自 I/O。**

### 原理

`renpy/text/ftfont.pyx` 里 FreeType 用 `FT_OPEN_STREAM`，
所有字体数据都走一个 **Python 回调**：

```cython
cdef unsigned long io_func(FT_Stream stream, unsigned long offset, ...):
    f = face.f                    # 字体文件对象
    if face.offset != offset:
        f.seek(offset)            # ← 每次 seek
    buf = f.read(count)           # ← 每次 read
```

而 `face.f` 是 `renpy.loader.load(fn)` 返回的 **`.rpa` 里的 SubFile**
（`renpy/loader.py:475`，`read()` 内部会 `open(文件名)` + `f.read()`）。

**于是每读一个字形轮廓 = Python 回调 + seek + 读一次几 MB 的 .rpa 文件。**
CFF 字体读一个字形通常要读多处，一句 32 字台词 = 100–160 次磁盘 I/O。
Vita 存储卡单次 seek+read 5–10 ms → **0.5–1.6 秒**，与实测吻合。

### 修法（纯 Python，不动引擎二进制）

让字体类文件整块读进内存，`SubFile` 换成 `BytesIO`：

```python
init -9 python:
    import io
    import renpy.loader as _ld

    _orig_load = _ld.load
    _FONT_EXT = (".ttf", ".otf", ".ttc", ".otc")

    def _psv_load(name, *a, **kw):
        f = _orig_load(name, *a, **kw)
        try:
            if name.lower().endswith(_FONT_EXT):
                data = f.read()
                f.close()
                return io.BytesIO(data)
        except Exception:
            pass
        return f

    _ld.load = _psv_load
```

`load_face` 只对文件做 `seek(0,2)` / `tell()` / `seek(0,0)`，`BytesIO` 全支持。

**代价**：字体常驻内存。3 个 CJK 字体各 4.1 MB ≈ 12.9 MB。Vita 约 330 MB 可用，可接受。

### 怎么确认是这个问题

在 `renpy.loader.load` 里计数，看字体文件的 `read()` 被调用多少次：

```python
count = [0]
orig_read = ...   # 包装 SubFile.read
```

一句话台词若触发上百次读，基本就锁定了。

---

## 铁律 19｜别把「字体格式」当成文字慢的原因

**踩过的坑**：怀疑 CFF（OTF）比 TrueType 光栅化慢，准备把 4.1 MB 的
SourceHanSansSC 从 CFF 转成 glyf。

**实测否掉了**：PC 上 CFF 光栅化 **0.039 ms/字**，转换后收益上限约 4%，
而且 cu2qu 的二次贝塞尔近似 + 不同 hinting 引擎会带来亚像素级的视觉差异。

**结论**：字体格式只在「CPU 光栅化确实是瓶颈」时才有意义。
若耗时与字数**不成比例**（例如 5 个字符要 0.5 秒），问题一定在别处（见铁律 18）。

---

## 附：一句话备忘

| 现象 | 先查 |
|---|---|
| 装到 99% 失败 `0x8010113D` | LiveArea PNG 不是 8-bit 索引色 |
| 启动即崩 `C2-12828-1` | 缺 `libshacccg.suprx` |
| 停在静态图 | 那是 `pic0.png`，引擎没起来 |
| 日志缺 `Set script version to:` | `script_version.txt` 被污染 |
| 日志缺 `Running init code` | init 里有联网/危险调用 |
| 黑屏有声音 | 渲染/素材有问题 |
| 机器自动重启 | 内核级故障（模块 panic） |
| `Could not load from archive` | rpa 的 prefix 用了 `str ''` |
| 日志 `limit=25.0Mpx` 改不动 | Vita 的 `Cache.init()` 写死了，`image_cache_size_mb` 无效 |
| `PSV FPS` 恒为 19.98 | periodic 定时器周期（50ms），不是渲染帧率 |
| 菜单卡 10 秒 | 先查 `gui/main_menu.png` 的解码尺寸，别只看文件大小 |
| 文字慢且耗时与字数不成比例 | 字体在 .rpa 里被流式读取，见铁律 18 |
| 文字慢但耗时与字数成正比 | 才轮到字形复杂度 / 描边层数 / 字体格式 |
