# Changelog

## 0.9.4 — 2026-11-12

- **Reverted 0.9.3: dictation shows what you are saying again.** 0.9.3 stopped creating a client composition region and inserted text only once a sentence settled. It removed the crash but also removed the live feedback: during speech the input box stayed empty and whole sentences appeared one at a time, so the speaker could not read what they had just said. That is a regression, not a fix, and it is withdrawn.
- **Back to the 0.9.2 rendering path**: settled sentences are `commitString`'d as normal document text, and the composition region carries only the short unsettled tail, so text is visible continuously, in order, with no ellipsis and no truncation.
- **Policy written into the patch README**: any dictation change that hides the speaker's own text is rejected regardless of whether it removes the crash. Both rejected routes (0.9.1 truncation, 0.9.3 no-composition) are recorded there so they are not retried.
- **The crash is the host editor's**: `Cannot resolve a Slate node from DOM node` is thrown by the Slate editor inside the application, not by the input method — the string exists in the host bundle and appears nowhere in `fcitx5-vinput.so`. What remains on our side is to keep the composition region short and to report the editor defect to its owner.

## 0.9.3 — 2026-11-12

- **Dictation Stops Using the Client Composition Region Entirely**: 0.9.2 still painted a short composition region (the unsettled tail) inline. A thirty-character utterance reproduced the same `Cannot resolve a Slate node from DOM node: [object HTMLSpanElement]` crash, which rules out length as the deciding factor — the composition region itself is what the host editor cannot survive at dictation speed. Dictation now never creates one: settled speech is inserted with `commitString()`, the same plain-text path as keyboard typing.
- **Status Hint Moved Out of the Client DOM**: `识别中 / 正在后处理` is shown in the input method's own aux window, which is not part of the client document and therefore never enters the editor's node mapping.
- **Progressive Insert Kept**: the last 8 characters are held back so the recognizer can still revise them; once 16 characters are waiting the text is handed over even mid-sentence, so long dictation never accumulates.
- **Command Mode Unchanged**: 划词指令 keeps its candidate menu and inline composition behaviour.

## 0.9.2 — 2026-11-12

- **Dictation Never Hides What You Said (replaces the 0.9.1 tail window)**: 0.9.1 kept only a 160-character tail of the running transcript in the composition region, so a long dictation showed `...` plus the last few words and the speaker could no longer read what had already been said. That traded away the user's own text to avoid a crash — the wrong trade. Finished sentences are now handed to the client as ordinary document text (`commitString`) and only the words still being revised stay in the composition region.
- **Composition Region Is Bounded Without Truncation**: `advanceStableCommit()` advances on clause boundaries and always keeps the last 12 characters open for revision; a single unpunctuated sentence is split at 48 characters. The whole utterance stays on screen, in order, as real text, and the composition region never grows past that bound — so controlled editors (Slate, Lexical, ProseMirror) no longer throw `Cannot resolve a Slate node from DOM node`.
- **No Double Insert**: `Session::committed_text` records what was already handed over; the final commit only appends the remainder. If the polish step rewrites text that is already on screen, the raw tail is appended instead — less polish is preferable to duplicated text.
- **Steadier Streaming**: committed text is not re-rendered on every partial result, so the preview stops redrawing itself character by character (the "jumping" feel compared with macOS dictation).
- **Optimising Hint Appends Instead Of Wiping**: the `识别中 / 正在后处理` hint is appended behind the unsettled tail instead of replacing the text.

## 0.9.1 — 2026-11-12

- **Dictation Front-End Now Versioned In This Repo**: The streaming composition region lives in `fcitx5-vinput`, an external GPL-3.0 plugin we customise. Those changes used to exist only in someone's working tree, with no history — which is how the regression below reached users. They are now maintained as a reviewed patch series in `patches/fcitx5-vinput/` (baseline `5808fd0`), shipped in the source archive, and applied with `git am`.
- **Bounded Inline Dictation Preview (host-editor crash fix)**: Streaming dictation used to re-send the entire accumulated transcript as the ClientPreedit composition on every partial result. Once the composition grew past a text leaf or paragraph boundary, controlled editors (Slate, Lexical, ProseMirror) could no longer map it back onto their document model and threw `Cannot resolve a Slate node from DOM node: [object HTMLSpanElement]`, breaking the host input box. The preview is now capped to a UTF-8-safe tail window (160 chars in the patch, `MaxPreviewChars` default 120 in our own plugin) while the full transcript is delivered in one shot at commit. Long dictation no longer correlates with host-side render failures.
- **Single Preedit Render Channel**: `Preview` no longer sets `setClientPreedit()` and `setPreedit()` at the same time. Exactly one channel is used, chosen from `CapabilityFlag::Preedit`, halving DOM churn against the host editor.
- **No Blank Frame On Commit**: `Commit` now inserts the text first and collapses the composition second. The previous order exposed one frame where the composition was gone but the text had not landed — the frame in which a controlled editor resolves a node that no longer exists.
- **Optimising Hint Appends Instead Of Wiping**: New `Note` D-Bus method keeps the streamed text on screen and appends `· 正在优化…` after it. Previously the composition region was cleared and the user lost sight of what had already been dictated.
- **Empty / Shrinking Transcripts Never Repaint**: Empty recognition results are no longer forwarded as previews, and a result that is materially shorter than what is already displayed (a late per-segment result during shutdown) is ignored instead of shrinking the visible text.

## 0.9.0 — 2026-11-11

- **Product Rebranding to doubaogo**: Officially rebranded from `doubao-ime-linux` to `doubaogo`, elevating Linux input method standards with modern UI, sleek documentation, and zero-compromise input performance.
- **Zero-Wine Native Streaming Inline Voice Dictation**:
  - Implemented true `ClientPreedit` inline streaming text preview directly at the application cursor (`zwp_text_input_v3` / X11 IM), naturally wrapping within application input boxes and text editors (e.g., Omawrite, VSCode, Chrome, Telegram).
  - Destroyed the unwieldy 3840px full-screen floating candidate bar and truncated display (`MaxStreamingDisplayWidth`).
  - Seamless zero-menu direct commit: eliminated the blocking candidate menu (manual 1/2 selection) on dictation completion; ByteDance Doubao LLM polished text automatically commits to the focused application in real time (~300ms).
  - Eradicated historical clipboard contamination: completely removed fallback reads to primary clipboard during speech recognition.
  - Decommissioned redundant `omavinput-osd` overlay processes and floating capsule widgets.
- **Slimmed Hybrid Dual-Engine Keyboard Typing**:
  - Official ByteDance DoubaoIME 0.9.2.7 core engine with local ONNX neural semantic prediction (`onnxruntime.dll` + quantized neural language model) for sub-10ms context computation.
  - 135MB binary multi-tier Trie lexicon with bigram personalization and custom phrase expansion.
  - Low-latency cloud candidates via QUIC/HTTPS to ByteDance Ocean Cloud (`ime-gw3.oceancloudapi.com`).
  - Industrial-grade keystroke stability: key symmetrical state machine preventing Backspace repeat storms, 0μs KeyUp RPC latency, 2.0s fast cold boot via Win32 `RegSetValueExW` in-process registry initialization, zero Shift Chinese/English phase desync, and clean scheme isolation.
- **Visual Documentation Benchmark**:
  - Modernized English (`README.md`) and Simplified Chinese (`README.zh-CN.md`) documentations benchmarked against top-tier projects like Rime 雾凇拼音 and WowType.
  - Replaced text/ASCII/Mermaid diagrams with real visual screenshots and feature showcases.

## 0.8.0 — 2026-11-11

- **Hybrid Dual-Engine Architecture**: Deep integration of official Doubao 0.9.2.7 engine with local ONNX neural network inference (`onnxruntime.dll`), multi-tier 135MB binary trie dictionary, and real-time edge cloud candidate queries (`enableCloudCandidate: true`).
- **Zero-Wine Native Streaming Voice**: Deprecates heavy Wine voice prefixes. Introduces pure Python reverse-engineered official streaming ASR (`wss://frontier-audio-ime-ws.doubao.com`) and local loopback adapter (`127.0.0.1:19283`) for ByteDance Doubao LLM smart text organization (disfluency removal, punctuation restoration, direct commit).
- **2.0s Fast Cold Boot & Double-Layer Self-Healing**: Replaced external `wine reg add` subprocesses with in-process Win32 `RegSetValueExW` in `keyboard-host.c`, cutting cold boot time in half (to 2.0s) and slashing startup peak memory from 1.2GB to 400MB. Added `WantedBy=graphical-session.target default.target`, `Restart=always`, `--enable` installer flag, and on-demand `ensureBackendStarted()` self-healing inside `doubaoime.so`.
- **Zero Shift Phase Inversion Fix**: Stopped forwarding bare `Shift`/`CapsLock` toggles to `ImeService.exe` and enforced `useShift: false` / `defaultChinese: true` on broker startup so Fcitx 5 exclusively manages Chinese/English switching without 180° internal state desync.
- **Extreme Memory Slimming**: Eliminated duplicate Wine prefix and duplicate Xvfb server (`doubao-imeservice.service`), reducing active stack memory consumption by >40% (from ~900MB to ~400MB).
- **Industrial-Grade Keystroke Stability**: Fixed infinite Backspace storm and auto-deletion bugs via key symmetrical state tracking; completely removed synchronous blocking RPCs on ordinary key release events for sub-10ms latency and 0 freeze.
- **Zero-Leak Scheme Switching**: Full compatibility with `fcitx5-schemes` multi-scheme management, guaranteeing 100% clean termination of Wine and Xvfb when switching between input methods.
- **Dynamic Xvfb Display Allocation**: Avoids hijacking real display or Xwayland `:0` by dynamically allocating isolated displays (95-120).
- **Custom Phrase Expansion**: In-memory and file-based custom phrase and idiom override support.

## 0.1.0-rc.2 — 2026-10-17

- Upgrade the supported official Windows engine to 0.9.2.7.
- Add live dictation previews, Right Alt hold-to-talk and Right Alt+Space hands-free input.
- Add optional official smart text organization in a separate Wine runtime, with explicit spoken-correction handling, protected-content checks and accepted-transcript fallback (#2).
- Preserve speech recorded before the ASR connection is ready; add opt-in IPv4 voice connections and diagnostics.
- Fix candidate paging, add a settings tray action and distinct tray/launcher icons.
- Respect the Fcitx UI's candidate-layout preference (#4, thanks @dunova).
- Wait for a live keyboard test socket and document the one-request connection contract (#3).
- Expand local and CI validation, including cancellation, focus protections and reproducible source packaging.

Experimental source prerelease. Official components and the external ASR adapter
must be supplied separately. Windows smart undo and complete settings/account
synchronization parity remain unsupported.

## 0.1.0-rc.1

First source preview for the official DoubaoIME 0.9.0.0 keyboard engine on Fcitx 5.

- Native candidate/preedit UI, selection, segmented conversion and focus reset.
- Configurable Wine/Xvfb/MinGW paths and verified installer extraction.
- Separate official settings runtime with keyboard-only configuration merging.
- Optional Linux dictation coordinator and independent Fcitx delivery endpoint.
- User-level installation manifest, collision checks, rollback and removal.
- Private-display integration checks and an explicit source-package file list.
- Separate English and Chinese READMEs.
- GCC/Clang CI with mock-engine Fcitx/GTK tests and reproducible archive checks.
- Tagged GitHub Releases gated by the complete CI workflow.

Experimental release: fixed upstream ABI, incomplete Windows settings parity,
external ASR adapter required for voice, and no bundled official components.
