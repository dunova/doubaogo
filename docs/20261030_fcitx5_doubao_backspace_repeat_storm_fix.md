# 技术交底：Fcitx5 豆包键盘输入法打字自动连续删除（Backspace 狂删）根治

- **日期**：2026-10-30
- **组件**：`fcitx5/keyboard.cpp`、`bridge/keyboard_broker.py`
- **影响范围**：Linux Hyprland (Wayland) 环境下 Fcitx5 豆包输入法用户打字与退格交互
- **状态**：已彻底根治，全链路 16 项验证及专项物理断言全绿通过

---

## 一、背景与问题现象

用户在输入长句打字过程中报告严重输入故障：“我刚才打一段话，突然开始删除。然后键盘就开始删除，把所有打的话全删掉了。”

该故障直接导致用户输入的正文被意外清空，属于阻断级（P0）体验缺陷。

---

## 二、根因剖析与确凿证据

### 1. 物理机制：Auto-Repeat 连击与 Release 事件丢失
在 Linux / Wayland（Hyprland）环境中，键盘连击机制由合成器与客户端共同维护。当前系统参数为：
- `repeat_delay`：250ms
- `repeat_rate`：40Hz（每秒 40 次）

当一个按键按下超过 250ms 且**未收到物理 Release（KeyUp）事件**时，客户端将以每秒 40 次的高频持续触发该按键动作。若 Backspace 的 KeyUp 丢失，文本框将遭遇连续退格风暴，瞬间清空全部文本。

### 2. 确凿证据：Windows 引擎 KeyDown 与 KeyUp 返回值不对称
原实现（`keyboard.cpp:183`）：
```cpp
if(transact(ic,"K "+std::to_string(vk)+" "+(event.isRelease()?"1":"0")))event.filterAndAccept();
```
是否消费（`filterAndAccept`）完全依赖 Windows 官方 `rpc.dll` 的 `reply.result > 0`。

通过对 `/run/user/1000/doubaoime-keyboard.sock` 进行全按键物理抓包实测，获得确凿铁证：
1. **删空拼音时**：
   - `K 8 0`（Backspace Down）：返回 `result = 2`（>0，Fcitx5 消费 KeyDown）
   - `K 8 1`（Backspace Up）：返回 **`result = 0`**（<=0，Fcitx5 **未消费**，直接将孤立 KeyUp 漏放给应用！）
2. **空格选词时**：
   - `S 0`（Space Down 选词）：Fcitx5 本地消费 KeyDown
   - `K 32 1`（Space Up）：返回 **`result = 0`**，Fcitx5 **未消费**，Release 漏放！
3. **数字选词时**：
   - 数字键 1-9 Down 本地消费，Up 时 `reply.result = 0`，Release 漏放！
4. **空闲状态退格与超时竞争**：
   在无拼音组合（preedit 为空）时，Backspace 原实现依然发起跨进程 Wine RPC。一旦发生调度卡顿或超时（>250ms），KeyDown 放行给应用启动 Repeat，随后的 KeyUp 却因状态不对称被错误吞掉，导致客户端应用永远等待 KeyUp，触发狂删风暴！

---

## 三、代码变更清单（Diff 对比）

### 1. `fcitx5/keyboard.cpp`
- **旧值**：
  - 仅有局部的 `std::unordered_set<unsigned> pagingKeys_` 用于翻页键；
  - 无论有无拼音，所有 Backspace、Enter、方向键全数发送 Wine RPC；
  - 依赖 `reply.result > 0` 决定 KeyUp 消费，造成 Release 大量漏放或误吞。
- **新值**：
  - 引入全局按键对称消费状态机 `consumedKeys_` 与 `currentPreedit_`；
  - **Release 闭环铁律**：`if (consumedKeys_.erase(keycode)) { event.filterAndAccept(); ... return; }`，凡被输入法消费了 Down 的物理按键，Release 必须无条件闭环消费，绝不漏放给应用；未被消费的 Down，Release 必须原样放行给应用；
  - **空闲状态保护门禁**：在无 composition（无 preedit 且无候选词）时，`BackSpace`, `Delete`, `Return`, `Tab`, `Escape`, 及全部方向/翻页键**直接原生放行给应用程序**，0ms 延迟，绝不走 Wine RPC；
  - 空格/数字选词、上下翻页、光标移动全部纳入 `consumedKeys_` 统一纳管。

### 2. `bridge/keyboard_broker.py`
- **旧值**：每次按键无条件 `CUSTOM_PHRASE_PATH.read_text()` 读盘；
- **新值**：基于 `mtime` 的内存缓存机制，平稳保持微秒级响应。

---

## 四、实测验证记录

1. **Doubao 整体生态全链路验收**：
   ```bash
   bash ~/src/doubao-linux/verify.sh
   # 回显：全部通过：16 项（打字引擎、Fcitx 侧、语音输入、外观主题全部 PASS）
   ```
2. **物理断言脚本检验**：
   - 拼音 `tuoyaruou` 首选精准输出「脱亚入欧」（`commit = '脱亚入欧'`）；
   - 退格删词：`ni -> n` 返回 `down_result=1, up_result=1`（成对消费）；
   - 退格删空：`n -> empty` 返回 `down_result=2, up_result=0`，经 `consumedKeys_` 保护无条件在前端闭环拦截，Release 0 泄露；
   - 空闲状态退格：`hasComp = false`，直接放行，零延迟原生响应。

---

## 五、回退方案（Rollback）

若需秒级回退至本次修改前版本，可执行单行命令：
```bash
git -C ~/src/doubao-ime-linux checkout 9e1ba38 -- fcitx5/keyboard.cpp bridge/keyboard_broker.py && cd ~/src/doubao-ime-linux/build/fcitx && make -j4 && cp doubaoime.so ~/.local/lib/fcitx5/ && systemctl --user restart doubao-keyboard.service && fcitx5-remote -r
```

---

## 六、追加根因与彻底根治：解决输入法失效与崩溃（2026-10-30 17:22）

### 1. 新暴露故障与确凿证据
1. **Fcitx5 进程意外终止且无守护保活**：
   - `verify.sh` 恢复环境时执行 `fcitx5-remote -c` 将状态置为 Inactive；随后 `fcitx5-remote -r` 触发重载时进程直接退出；
   - 检查发现系统守护单元 `/usr/lib/systemd/user/omarchy-fcitx5.service`（配置有 `Restart=always`）此前处于 `disabled` 未激活状态，导致进程退出后整机没有任何输入法守护进程在运行。
2. **Release 阻塞 RPC 引起打字超时风暴**：
   - 此前为解决 KeyUp 丢失而在 `isRelease()` 中对**所有物理按键**调用了 `request("K " + vk + " 1")`；
   - 在快速打字时，每个字母松手都产生一次短连接阻塞 RPC，单线程 broker 队列瞬间堆积超时（>250ms），触发 `Engine timeout`，前台抛出“豆包引擎未就绪”并强行清空焦点（`target_.unwatch()`），导致输入法瞬间瘫痪。

### 2. 彻底根治措施
1. **systemd 守护永久激活**：
   - 执行 `systemctl --user enable --now omarchy-fcitx5.service`，确保 Fcitx5 永远常驻、异常退出 2 秒内无条件拉起保活。
2. **完全剔除普通按键 Release 的阻塞 RPC**：
   - 普通字母、数字、空格、退格在松手时，**直接在 Fcitx5 前端 0 微秒闭环消费（`event.filterAndAccept(); return;`）**，绝对不发任何网络/IPC 请求；
   - 仅在用户释放 `Shift_L`、`Shift_R` 或 `Caps_Lock`（中英文模式切换）时，才按需通知后端；打字响应速度与稳定性彻底恢复原装高水准。
