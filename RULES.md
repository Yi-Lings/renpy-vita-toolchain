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

**踩过的坑**：用 `config.interact_callbacks` 测卡顿 —— 它在交互
**开始**时调用，测出来的是「两次交互之间的时间」，**包含玩家看屏幕的时间**。
数据完全没意义。

**铁律**：测卡顿用 `config.periodic_callbacks`（每帧调用）算真实 FPS：

```python
init -9 python:
    import time as _t
    _s = [_t.time(), 0, 0.0, 0.0]
    def _probe():
        now = _t.time(); d = now - _s[0]; _s[0] = now
        _s[1] += 1; _s[2] += d; _s[3] = max(_s[3], d)
        if _s[1] >= 30:
            renpy.write_log("PSV FPS: %.2f (avg %.0f ms, worst %.0f ms)",
                            1.0/max(_s[2]/_s[1], 1e-4), _s[2]/_s[1]*1000, _s[3]*1000)
            _s[1] = 0; _s[2] = 0.0; _s[3] = 0.0
    config.periodic_callbacks.append(_probe)
```

**读法**：
- 稳态 FPS 低 → 渲染瓶颈
- 稳态正常但 `worst` 有几千 ms → 一次性加载/编译瓶颈
- 两者都低 → 先解决加载，再看渲染

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

## 附：一句话备忘

| 现象 | 先查 |
|---|---|
| 装到 99% 失败 `0x8010113D` | LiveArea PNG 不是 8-bit 索引色 |
| 启动即崩 `C2-12828-1` | 缺 `libshacccg.suprx` |
| 停在静态图 | 那是 `pic0.png`，引擎没起来 |
| 日志缺 `Set script version to:` | `script_version.txt` 被污染 |
| 日志缺 `Running init code` | init 里有联网/危险调用 |
| 黑屏有声音 | 渲染/素材问题 |
| 机器自动重启 | 内核级故障（模块 panic） |
| `Could not load from archive` | rpa 的 prefix 用了 `str ''` |
