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
| `0002-fix-dictation.patch` | 组合区限长（尾部 160 字符）、收尾阶段状态提示追加而非覆盖 | 缺陷修复 |

`0001` 的三处改动与上游行为不同，是刻意为之，不是上游能力；`0002` 修的是 `0001`
引入的副作用（组合区长度失控打崩受控编辑器）。因此两者必须按序号应用，顺序不可交换。

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
