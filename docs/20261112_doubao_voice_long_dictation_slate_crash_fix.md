# 技术交底：豆包语音长句上屏导致受控编辑器崩溃、以及整理阶段清空已显示文字

- **日期**：2026-11-12
- **组件**：`fcitx5/voice.cpp`、`bridge/audio.py`、`bridge/daemon.py`
- **影响范围**：所有使用 ClientPreedit 流式上屏的宿主应用，尤其是基于 Slate / Lexical / ProseMirror 等受控编辑器的网页与 Electron 应用
- **状态**：已修复，源码编译与单元测试全绿
- **修订（2026-11-12 11:00，v0.9.2）**：本文原先采用的「尾部窗口 + `…` 折叠」方案**已废弃**。
  把可见文字截断，等于为了绕开宿主编辑器的报错而让说话人看不见自己刚说的内容——这是
  错的取舍。现行方案是**逐句落定**：说完的句子直接 `commitString` 成正文，只有仍在改写
  的尾部留在组合区（详见 `patches/fcitx5-vinput/0002-fix-dictation.patch`）。本文描述
  的 `voice.cpp` 侧 `MaxPreviewChars` 截断实现属于同一思路，`doubaovoice` 插件当前待命
  未上链路，移植时按逐句落定改写，不要再保留截断。

---

## 〇、代码归属：哪些是上游的，哪些是我们的

这次缺陷横跨两个仓库，先把边界钉死，避免把上游代码当成自研、或把自研决策当成上游行为。

| 组件 | 位置 | 归属 |
|---|---|---|
| 语音采集、流式 ASR、**组合区渲染（崩溃点）** | `fcitx5-vinput` | 上游 [xifan2333/fcitx5-vinput](https://github.com/xifan2333/fcitx5-vinput)，GPL-3.0。我们只以补丁形式定制，见 `patches/fcitx5-vinput/` |
| 「正在优化」这一步的整理调用 | `doubaoime` 适配器（`~/.local/share/vinput/adapters/`） | 外部适配器，来自 vinput-registry，由用户自备；本仓库只在 `THIRD_PARTY.md` 声明依赖，不分发 |
| 录音协调、结果校验、整理提示、日志 | `bridge/`（`audio.py`、`daemon.py`、`organize.py`） | 本仓库，MIT |
| 键盘引擎桥接 | `fcitx5/keyboard.cpp`、`bridge/keyboard_broker.py` | 本仓库，MIT |
| 独立提交插件 `doubaovoice` | `fcitx5/voice.cpp` | 本仓库，MIT。当前链路旁待命，本文第三、四节记录的是它的同类修复 |

因此对「这些功能是上游的还是我们自己写的」这个问题，答案是分层的：

- **把组合区改成「全文直写」是我们的产品决策**（`0001` 补丁），上游原本会折叠成 `head…tail`；
- **组合区失控后崩溃的渲染代码是上游的**，我们改不了宿主编辑器的断言，只能约束组合区长度；
- **「正在优化」的文案属于上游插件的状态机，真正干活的整理接口是外部适配器**，本仓库负责编排与提示。

补丁序列与应用方式见 `patches/fcitx5-vinput/README.md`。

---

## 一、问题现象

用户在使用豆包语音输入法（doubaogo 0.9.0）时报告两个缺陷：

1. **长句语音后宿主应用报错**：输入框区域弹出红色错误条

   ```
   输入框遇到错误
   Cannot resolve a Slate node from DOM node: [object HTMLSpanElement]
   ```

   短句（几百字以内）正常，长句必现或高频出现。报错后点击「重试」可以恢复，文字最终仍能上屏——说明**语音识别与整理链路本身是好的，崩的是宿主应用的渲染层**。

2. **整理阶段清空已经显示的文字**：按下语音结束键后进入「优化」阶段，屏幕上已经流式显示出来的文字被整体抹掉，只剩一句「正在优化」提示。

---

## 二、根因剖析

两个现象同源，都指向「把整段文字当作组合区（preedit）反复重设」这一实现方式。

### 1. 组合区长度决定受控编辑器能否映射回文档模型

`fcitx5/voice.cpp` 的 `preview()` 在每一个流式分片到达时，都会把「截至目前的全部文字」重新设置一次 ClientPreedit：

```cpp
// 旧实现（voice.cpp:236）
bool preview(const std::string &ticket, const std::string &text) {
    if (!valid(ticket) || !safeText(text)) return false;
    auto *field = pending->field.get();
    fcitx::Text preedit(text, ...);          // text = 全部累积文字
    field->inputPanel().setClientPreedit(preedit);
    field->inputPanel().setPreedit(preedit); // 同时写第二条通道
```

浏览器会把这段组合区落成 contenteditable 里的一棵 DOM 子树。Slate 维护着「Slate 数据模型 ↔ 真实 DOM 节点」的双向映射表，它只能容忍**落在单个文本叶子（leaf）内部**的组合区。

- 短句：组合区始终在同一个 `data-slate-string` 叶子 span 内，Slate 能正常映射；
- 长句：组合区越写越长，一旦跨过叶子或段落边界，浏览器必须拆分／重建 DOM，Slate 就在映射表里查不到那个 `HTMLSpanElement`，随即抛出断言并中断渲染。

这解释了「不是对话框被撑爆，而是组合区太长」。`safeText()` 的上限是 64 KiB（约 2 万汉字），远高于实际触发点——代码里**根本没有针对组合区长度的保护**。

### 2. 同一条组合区同时写进两条渲染通道

旧实现同时调用 `setClientPreedit()` 与 `setPreedit()`。前者把文字交给应用内联渲染，后者交给 Fcitx 候选窗渲染。两条渲染路径驱动同一段文字，DOM 变更频率翻倍，放大了受控编辑器失步的概率。

### 3. 提交时先清空、再上屏

```cpp
// 旧实现（voice.cpp:249）
auto delivery = std::move(pending);
clearPreview(*delivery);   // 先清空组合区
if (accepted) field->commitString(output);   // 再插入正文
```

中间存在一帧「组合区已消失、正文还没落地」的空窗。受控编辑器恰恰是在这一帧去解析刚被删掉的 span 而抛错，用户看到的就是「文字突然被清空、然后报错」。

### 4. 空文本预览没有任何防护

`bridge/audio.py` 会把空的识别结果也转发为 `preview` 事件，而 C++ 侧 `safeText("")` 返回 `true`。任何一次空 preview 都会把屏幕上的组合区抹掉。识别收尾阶段若先回吐「最后一段」而非全文，预览还会**突然变短**，观感同样是「文字被清掉」。

---

## 三、代码变更清单

### 1. `fcitx5/voice.cpp`

- **新增配置项** `MaxPreviewChars`（默认 120，范围 20–2000）：内联预览的字符上限。
- **新增** `characters()` / `tailChars()`：按 UTF-8 码点安全截取尾部窗口，绝不切断汉字。
- **新增** `render()`：统一渲染入口。
  - 组合区只承载**尾部窗口**，超出上限时前缀补 `…` 并附「（已说 N 字）」，完整文本保留在 `delivery.shown` 里等待提交；
  - **只走一条通道**：应用声明 `CapabilityFlag::Preedit` 时用 `setClientPreedit()`，否则用 `setPreedit()`，另一条显式置空。
- **`preview()`**：拒绝空文本，空 preview 不再能抹掉已有组合区；同时清除 `finishing` 标记。
- **新增 D-Bus 方法 `Note(ticket, suffix)`**：保留已显示的文字，只在其后追加状态后缀，并把 `finishing` 置位。
- **`commit()`**：顺序反转为「先 `commitString()`，再 `clearPreview()`」，消除空窗帧。
- **`observe()`**：`finishing` 阶段不再因落键 `revoke("typing")`——整理结果马上要提交，此时丢弃正是用户看到的「文字被清空」。Esc 仍然可以取消。

### 2. `bridge/audio.py`

- 空识别结果不再转发为 `preview`。
- 新增单调性保护：新结果明显短于当前预览（<90%）时视为收尾阶段回吐的「分段结果」，不绘制，避免屏幕上文字突然变短。

### 3. `bridge/daemon.py`

- `organizing` 阶段改为先调用 `Note(token, "  ·  正在优化…")`，把提示接在已显示文字后面，再发通知；不再有任何清空动作。

### 4. `tests/test_audio_buffer.py`

- 原断言把「转发空文本」当成正确行为（`['初步','修订','','下一句']`），已修正为 `['初步','修订','下一句']`。
- 新增 `test_shrinking_stream_does_not_erase_visible_preview` 覆盖单调性保护。

---

## 四、验证记录

1. **编译**：`cmake --build build/fcitx -j4`，`doubaoime` 与 `doubaovoice` 均干净通过，无告警。
2. **单元测试**：`/usr/bin/python3 -m pytest tests/ -q` → `66 passed, 37 subtests passed`。
3. **UTF-8 截断专项**：对 `"abc中文def中文ghi"` 逐一切割点验证，输出恒为合法 UTF-8，码点数与预期一致（`tailChars(x,5) == "中文ghi"`）。
4. **产物一致性**：`md5sum` 校验 `build/fcitx/doubaovoice.so` 与 `~/.local/lib/fcitx5/doubaovoice.so` 一致，且与备份版本不同。

---

## 五、效果对照

| 场景 | 修复前 | 修复后 |
|---|---|---|
| 说了 500 字 | 组合区跨越叶子边界，Slate 抛错 | 组合区恒 ≤120 字，稳定不崩 |
| 结束语音进入整理 | 文字被清空，只剩「正在优化」 | 原文保留，尾部追加「· 正在优化…」 |
| 提交瞬间 | 先清空再插入，闪一下并可能报错 | 先插入再收起组合区，无空窗 |
| 收到空识别结果 | 组合区被抹掉 | 直接忽略 |
| 识别收尾回吐分段 | 预览突然变短/消失 | 保持不缩短 |

---

## 六、回退方案

```bash
# 恢复插件
cp ~/.local/lib/fcitx5/doubaovoice.so.bak-20261112-095715 \
   ~/.local/lib/fcitx5/doubaovoice.so
fcitx5-remote -r

# 或回退源码
git -C ~/src/doubao-ime-linux checkout HEAD -- fcitx5/voice.cpp bridge/audio.py bridge/daemon.py tests/test_audio_buffer.py
```

---

## 七、遗留与后续

- 组合区上限是**按宿主编辑器容忍度**取的保守值。若宿主应用换成非受控编辑器（如原生 GtkTextView），可把 `MaxPreviewChars` 调大以恢复更长的内联预览。
- 更彻底的方案是「增量固化」：把已确认到句末标点的部分直接 `commitString` 成正文，组合区只保留最新一句。这能让预览长度与说话时长彻底解耦，但要求上游 ASR 的最终结果完全单调，否则存在回改风险，因此本次未启用。
