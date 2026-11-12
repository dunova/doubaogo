# fcitx5-vinput 本地补丁序列

语音听写的「采集 → 流式识别 → 组合区上屏」由 [fcitx5-vinput](https://github.com/xifan2333/fcitx5-vinput)
承担，本仓库不复制它的源码，只维护相对上游的补丁。补丁放在这里，是因为这些改动
是我们方案的产品选择与缺陷修复，既不该进入上游仓库，也不该只停留在某个人的工作区里。

- 上游基线：`5808fd0`（`refactor(quality): eliminate procedural duplication across downloader and daemon core (#578) (#616)`）
- 上游许可：GPL-3.0

## 补丁清单

| 文件 | 内容 | 性质 |
|---|---|---|
| `0001-feat-dictation.patch` | 内联组合区上屏（ClientPreedit）、听写直接提交不弹候选、上下文选区不读剪贴板 | 我们的产品定制 |
| `0002-fix-dictation.patch` | 听写不再创建客户端组合区：逐句 `commitString` 上屏，状态提示走 aux 窗口 | 缺陷修复 |

`0001` 的三处改动与上游行为不同，是刻意为之，不是上游能力；`0002` 修的是 `0001`
引入的副作用（受控编辑器无法承受组合区被高频改写）。因此两者必须按序号应用，
顺序不可交换。

**两条被证据否掉的错误做法，不要重走**：

1. **截断/折叠可见文字**（0.9.1：只留尾部 160 字、head…tail 折叠）。为了绕开报错
   而让说话人看不见自己说了什么，是不可接受的取舍。
2. **给组合区限长**（0.9.2：尾部 8–12 字）。一句三十来字的短听写同样复现崩溃，说明
   决定因素是「组合区本身」而非其长度；受控编辑器在每次 composition 更新时都要把
   组合区重新映射回自己的模型，听写速率下必然解析到已被替换的节点。

`0002` 现行的做法是**根本不创建组合区**：`commitString()` 与键盘打字走同一条纯文本
插入路径，不产生 composition；状态提示走输入法自己的 aux 窗口（不属于客户端 DOM）。

## 应用

```bash
git clone https://github.com/xifan2333/fcitx5-vinput
cd fcitx5-vinput
git checkout 5808fd0
git am /path/to/doubaogo/patches/fcitx5-vinput/*.patch
```

本机没有 clang / mold / ninja 时用 g++ 构建，并注意 `/tmp` 可能空间不足：

```bash
cmake -S . -B build-gcc -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release \
      -DVINPUT_ENABLE_LOCAL_ASR=OFF -DVINPUT_ENABLE_WERROR=OFF \
      -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF
TMPDIR=~/.cache/vinput-build-tmp make -C build-gcc -j"$(nproc)"
```

单测：`cd build-gcc && TMPDIR=~/.cache/vinput-build-tmp ctest -j4 --output-on-failure`

## 许可边界

补丁内容由 GPL-3.0 代码派生，按 GPL-3.0 提供；本仓库其余部分（bridge、fcitx5 插件、
脚本、文档）为 MIT。两者不混合编译，也不互相链接：补丁只作用于上游源码树。
分发二进制时需同时满足 GPL-3.0 的相应义务。

## 与 `fcitx5/voice.cpp` 的关系

本仓库自带的 `doubaovoice` 插件也有同一类修复（见
`docs/20261112_doubao_voice_long_dictation_slate_crash_fix.md`）。两条链路目前并存：
实际在跑的语音由 fcitx5-vinput + `doubaoime` 适配器完成，`doubaovoice` 在旁待命。
两处修复独立，互不依赖。
