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

### 12.2 第二层坑（更隐蔽）：`periodic_callbacks` 也测不准

换成 `config.periodic_callbacks` 之后看着对了，但**仍然是假的**。

**原理**：`periodic_callback` 由 50ms 的 `PERIODIC` 定时器驱动。可是
interact 循环在等待输入时会**阻塞在 `event_wait()`**：

```python
# renpy/display/core.py:3959-3966
if needs_redraw or (not can_block) or ...:
    ev = self.event_poll()
else:
    ev = self.event_wait()        # ← 阻塞在这里，定时器事件要等玩家按键才处理
```

于是「玩家读一行台词读 36 秒」被记成「卡顿 36 秒」。
更隐蔽的是：**稳态 FPS 会恒等于 20.0**，因为 `1 / 0.05s = 20`——
那是定时器周期，不是渲染帧率。看到 `PSV FPS 19.98 (avg 50 ms)`
就以为「稳定 20 帧没问题」，其实是探针在自欺。

**真机日志里的铁证**：

```
PSV FPS: 0.80 (avg 1244 ms, worst 35921 ms @ tl/zhcn/script.rpyc:102)
PSV STALL 35.92s at tl/zhcn/script.rpyc:102
```

那行台词是 `"《好色的脸》、《恶心的脸》——这是通过问卷调查送给隆司的同班同学的话。"`——
普通对话，不可能卡 36 秒。真相是玩家在那句话上停了 36 秒。

**铁律**：测卡顿只能测**函数实际执行耗时**，不能测「两次回调的间隔」。
包住 `Interface.draw_screen()` / `render.render_screen()`：

```python
init -9 python:
    import time as _t

    def _wrap(mod, attr, label):
        orig = getattr(mod, attr)
        def f(*a, **kw):
            t0 = _t.time()
            try:
                return orig(*a, **kw)
            finally:
                d = _t.time() - t0
                if d >= 0.35:
                    renpy.write_log("PSV SLOW %.2fs %s", d, label)
        setattr(mod, attr, f)

    _wrap(renpy.display.core.Interface, "draw_screen", "FRAME")
    _wrap(renpy.display.render, "render_screen", "RENDER")
```

`draw_screen` 在 idle 时**根本不会被调用**，所以计时是干净的。
真要测帧率，读引擎自己的 `renpy.display.interface.frame_times`
（5 秒滚动窗口，和 Shift+D 的 Performance 屏同一份数据），
不要自己用定时器算。

---

## 铁律 12b｜`config.periodic_callbacks` 只在「有帧」时跑

补一条上面没写透的：

```python
# renpy/display/core.py:4013   PERIODIC 事件处理
if ev.type == PERIODIC:
    for i in renpy.config.periodic_callbacks:
        i()
```

而 `PERIODIC` 事件是 `pygame.time.set_timer(PERIODIC, 50)` 发出来的。
它进的是事件队列，**只有 interact 循环转到 `event_poll()` 才会被消费**。
在 `event_wait()` 阻塞期间，队列里积压的 PERIODIC 事件不会执行回调。
所以 periodic callback 的调用间隔 = `max(50ms, 玩家停顿时间)`。

这条同样适用于**任何**依赖 periodic 的「后台任务」（包括官方
`renpy.audio.audio.periodic()`）——在 Vita 上音频卡顿也可能与此有关。

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
