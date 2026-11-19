Here is the architectural and design blueprint for evolving **Selene** from a terminal CLI into a native macOS desktop application on Apple Silicon.

---

### 1. Native macOS Surface Architecture

To feel like a true macOS citizen rather than an Electron-style web wrapper or intrusive "desktop buddy," Selene should split its UI across **four distinct AppKit/SwiftUI surface tiers** based on immediacy and cognitive load.

#### A. The Ambient HUD (`NSPanel` Subclass — Non-Activating)
Standard SwiftUI `Window` / `WindowGroup` scenes cannot replicate Spotlight/Dynamic-Island behavior cleanly because they fight window focus and Space switching.
* **Implementation:** Subclass `NSPanel` with `styleMask: [.nonactivatingPanel, .fullSizeContentView, .borderless]` and host SwiftUI inside an `NSHostingView`.
* **Window Behavior:**
  * `collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]` so Selene floats seamlessly over full-screen Xcode, Terminal, or browsers without appearing in `⌘-Tab`.
  * `level = .floating` (elevated to `.statusBar` only during active PTT/dictation).
  * `becomesKeyOnlyIfNeeded = true` so clicking mute/stop never steals keyboard focus from the user’s editor; focus is only acquired when the user clicks into the quick-prompt text field.
* **States:**
  1. **Dormant Dot / Micro-Pill:** Minimal edge-anchored status indicator (or hidden completely when wake-word/hotkey-only mode is preferred).
  2. **Active Voice Capsule:** Morphs smoothly to show Selene’s avatar crest, real-time audio reactivity, live Whisper partial transcription, and a one-click cancel/interrupt control.

#### B. Attached Transcript & Context Wing (HUD Expansion)
When a response requires reading (code snippets, Japanese/study explanations, screen-capture analysis), the HUD capsule expands downward or outward into a compact, dismissible drawer:
* **Contents:** Streaming Markdown with syntax highlighting, thumbnail pill of captured screen/clipboard context, inline audio playback scrubber, and contextual action chips (e.g., *"Save to Study Deck"*, *"Pin Fact"*).
* **Behavior:** Auto-collapses back to the micro-pill on `Esc` or outside click (unless pinned by the user).

#### C. System Presence (`MenuBarExtra`)
Use `MenuBarExtra(style: .window)` as the persistent control plane:
* **Quick Toggles:** Mic armed / Wake-word / Do Not Disturb (suspends proactive mentor nudges).
* **Apple Silicon Telemetry:** Compact readout of daemon status, active models in Unified Memory (e.g., `Whisper + Kokoro + RVC: 1.4 GB`), and an instant **"Flush MLX Cache"** action.
* **Launchers:** Quick triggers for the Workspace windows and global hotkey cheat sheet.

#### D. Dedicated Workspace Windows (`SwiftUI Window` Scenes)
Heavy, focused workflows do **not** belong in a floating HUD. Give them standard macOS windows (`NavigationSplitView`) managed via `openWindow(id:)`:
1. **Study Cards & SRS Deck (`id: "study-deck"`):**
   * Distraction-free, keyboard-first review surface (`Space` to reveal, `1–4` for FSRS/SM-2 grading, `R` to replay Kokoro+RVC mentor pronunciation).
   * Supports split-pane note preview and audio shadowing mode.
2. **Memory & Persona Studio (`id: "memory-studio"`):**
   * Transparent CRUD interface for Selene’s local persistence layer: **Pinned Facts** (hard truths about the user), **Episodic Memory Timeline** (searchable conversation summaries), **Voice/RVC Checkpoint Selector**, and **Routing Rules** (local vs. Gemini multimodal escalation).
3. **Settings & Permissions (`Settings` scene):**
   * Guided diagnostics for macOS TCC permissions (Microphone, Screen Recording for multimodal vision, Accessibility for global hotkeys/active-app context) and `SMAppService` Launch-at-Login.

---

### 2. Design Taste & Motion Craft

The primary visual risk for an AI anime assistant is falling into either "generic AI neon gradient slop" or "2008 desktop waifu clutter." The target aesthetic is **Tactile Apple Pro Utility + Subtle Editorial Anime Craft**.

#### Materiality & Typography (macOS HIG)
* **Surfaces:** Use native `NSVisualEffectView` (`.hudWindow` for the floating capsule, `.sidebar` for workspace windows) layered with a crisp `0.5pt` inner stroke (`Color.white.opacity(0.14)` in dark mode, `Color.black.opacity(0.08)` in light mode) and soft ambient shadow. Avoid muddy fake blurs or dark-purple RGB glows.
* **Typography:** System `SF Pro` for UI chrome, paired with `.monospacedDigit()` for latency/VRAM metrics and SRS intervals, and clean editorial serif or high-legibility CJK-compatible sans for mentor study cards.
* **Restrained Character Presence:** Never render a full-body animated sprite blocking the user's code. Represent Selene through a **precision-framed circular/squircle Avatar Crest** (high-DPI vector/illustrated bust) that swaps subtle expression states (*Attentive, Thinking, Speaking, Encouraging*) via crisp cross-dissolves, paired with one signature ink accent (e.g., *Lunar Indigo* or *Warm Vermilion*) for active speaking rings.

#### Emil Kowalski-Style Physics & Choreography
Motion must feel **fast, interruptible, and physically grounded**—never sluggish or theatrical:
* **Spring Curves:**
  * *HUD Morphing (Pill $\leftrightarrow$ Transcript Wing):* Tight, critically damped spring: `Animation.spring(response: 0.28, dampingFraction: 0.86)`. Zero overshoot bounce on structural chrome.
  * *Micro-Interactions (Toggles, Grading Cards, Action Chips):* Snappy `response: 0.18, dampingFraction: 0.90` with `scaleEffect(isPressed ? 0.96 : 1.0)`.
* **Blur-Scale Transitions:** Instead of sliding panels across the screen, reveal HUD drawers and card flips using combined opacity + subtle scale (`0.96 -> 1.0`) + `2px -> 0px` Gaussian blur transitions.
* **Interruptible Voice Reactivity:** Do not drive UI bars directly from raw, jittery microphone buffers. Pass RMS energy from `AVAudioEngine` / Kokoro playback through a 60/120Hz `TimelineView` spring-damper smoother to animate a single minimalist breathing ring or 5-node fluid waveform.
* **Barge-In Feedback:** Pressing the hotkey or speaking while Selene is talking must immediately duck/fade Kokoro+RVC output over `80ms` (`AVAudioPlayerNode` volume ramp) and snap the HUD ring back to *Listening* state without waiting for the daemon roundtrip.

---

### 3. Daemon Supervision & Apple Silicon Lifecycle

Never embed CPython in-process inside the Swift binary. Keep the Python MLX/Metal runtime as an **isolated out-of-process worker daemon** supervised by Swift.

```
┌──────────────────────────────────────────────────────────┐
│ Selene.app (SwiftUI + AppKit + AVAudioEngine)            │
│  ├─ HUD / MenuBar / Workspace Windows                    │
│  ├─ Global Hotkey & Barge-in Audio Tap                   │
│  └─ DaemonSupervisor (kqueue, Sleep/Wake, MemorySource)  │
└──────────────┬─────────────────────────────┬─────────────┘
               │ UDS Control (MsgPack/JSON)  │ UDS Audio Pipe (PCM f32)
┌──────────────▼─────────────────────────────▼─────────────┐
│ selene-daemon (Python 3.12+ / MLX / Metal)               │
│  ├─ mlx-whisper (STT)      ├─ Gemini Multimodal Client   │
│  ├─ Kokoro-82M (TTS)       └─ SQLite + Vector Memory     │
│  └─ Metal RVC (Voice Conv.)                              │
└──────────────────────────────────────────────────────────┘
```

#### A. Process Lifecycle & Orphan Prevention
* **Bundling:** Package a relocatable Python environment (built via `uv` / `python-build-standalone`) inside `Selene.app/Contents/Resources/runtime/`, launching via `Foundation.Process`.
* **Zero-Zombie Guarantee:** Pass a pipe file descriptor or parent PID to the Python daemon. On the Python side, spawn a background `kqueue` watcher (or `os.getppid()` / pipe-EOF reader) so if `Selene.app` crashes or gets `SIGKILL`ed, the Python process immediately flushes SQLite, releases Metal buffers, and exits.
* **Swift Watchdog:** Swift tracks the child PID via `DispatchSource.makeProcessSource(identifier: pid, eventMask: .exit)` and runs an exponential backoff restart state machine (`stopped → booting → ready → degraded → restarting`), capping crash-loops with a clear recovery prompt in the MenuBar.

#### B. Dual-Channel Unix Domain Socket (UDS) IPC
Avoid HTTP/FastAPI overhead for local real-time audio:
* **Socket Path:** `~/Library/Application Support/Selene/run/selene.sock` (`0600` permissions).
* **Control Channel:** Length-prefixed MessagePack (or NDJSON) RPC for requests (`transcribe_commit`, `generate_reply`, `review_card`), streaming token chunks, and telemetry events.
* **Audio Streaming:** Keep microphone capture (`AVAudioEngine`) and speaker playback (`AVAudioPlayerNode`) in **Swift/CoreAudio** rather than Python `pyaudio`/`sounddevice`. Swift handles Bluetooth HFP/AirPods sample-rate switching reliably and streams raw `Float32` 16kHz/24kHz PCM frames over a dedicated UDS stream to `mlx-whisper` and back from `Kokoro+RVC`.

#### C. Sleep, Wake, and Audio Route Transitions
* **Pre-Sleep (`NSWorkspace.willSleepNotification`):** Stop `AVAudioEngine` input taps, send a `quiesce` RPC to Python so Metal finishes any in-flight command buffers (preventing Metal GPU context corruption on wake), and checkpoint SQLite WAL.
* **Post-Wake (`NSWorkspace.didWakeNotification`):** Re-bind `AVAudioEngine` (crucial if the user connected/disconnected AirPods or a Studio Display while asleep) and issue a lightweight UDS `ping` with a `500ms` timeout—triggering a clean daemon respawn if the worker hung across sleep.

#### D. Unified Memory & Thermal Stewardship
On 16GB–32GB Apple Silicon Macs, Selene shares RAM with Xcode, Docker, and browsers. Models must not squat on Unified Memory indefinitely:
* **Swift Pressure Listener:** Use `DispatchSource.makeMemoryPressureSource(eventMask: [.warning, .critical])`. Forward `.warning` immediately to the daemon.
* **Tiered Model Residency in Python:**
  * **Tier 1 (Hot — ~400MB):** VAD + `mlx-whisper` (quantized/turbo) while mic is armed.
  * **Tier 2 (Warm — ~1.0GB):** `Kokoro-82M` + `Metal RVC` weights. Loaded lazily on first TTS call; **auto-evicted** after `N` minutes of idle conversation or immediately on macOS `.warning` memory pressure.
  * **Explicit Cache Hygiene:** Call `mx.metal.clear_cache()` between heavy inference bursts and configure `mx.metal.set_cache_limit(...)` so MLX’s allocator doesn't hoard inactive Metal heaps when the user opens a heavy build.

---

### 4. Concrete Prioritized Roadmap

#### Phase 1: Daemon Extraction & Headless Contract (Weeks 1–2)
* **Goal:** Decouple the existing Python CLI into a headless `selene-daemon` before writing UI.
* **Tasks:**
  1. Refactor CLI loop into an event-driven `asyncio` server speaking length-prefixed JSON/MsgPack over UDS.
  2. Move SQLite/memory/SRS deck storage into a strict schema under `~/Library/Application Support/Selene/`.
  3. Implement `mx.metal.set_cache_limit`, idle RVC/Kokoro eviction, and parent-EOF self-termination.
  4. Verify roundtrip latency (Whisper $\rightarrow$ Gemini $\rightarrow$ Kokoro $\rightarrow$ RVC streaming) using a minimal Python/Swift CLI test harness.

#### Phase 2: Native App Shell, Audio Engine & Floating HUD (Weeks 3–5)
* **Goal:** Daily-drivable voice/text Jarvis loop on the desktop.
* **Tasks:**
  1. Build `DaemonSupervisor` in Swift (process spawn, UDS client, reconnect state machine, sleep/wake hooks, memory pressure forwarding).
  2. Implement Swift-native `AVAudioEngine` capture/playback + `80ms` barge-in ducking + global hotkey listener (Carbon `RegisterEventHotKey` or CGEventTap with Accessibility check).
  3. Build the non-activating `NSPanel` HUD capsule with Emil-style spring physics, audio-reactive ring, live partial STT, and expandable Markdown transcript wing.
  4. Add `MenuBarExtra` status popover with VRAM telemetry and quick toggles.

#### Phase 3: Multimodal Context & Dedicated Workspace Surfaces (Weeks 6–8)
* **Goal:** Elevate Selene from "voice toy" to a genuine mentor and personal knowledge tool.
* **Tasks:**
  1. Integrate `ScreenCaptureKit` (single-frame active window / region capture on demand) to feed visual context directly into Gemini multimodal turns.
  2. Build the **Study Cards & SRS Deck** `Window` with keyboard-driven review and instant Kokoro+RVC audio playback.
  3. Build the **Memory & Persona Studio** `Window` so users can inspect, edit, and delete pinned facts and conversation memories.

#### Phase 4: Polish, Hardening & Distribution (Weeks 9–10)
* **Goal:** Rock-solid reliability and native distribution.
* **Tasks:**
  1. Build First-Run Onboarding & TCC Permission Checklist (Mic, Screen Recording, Accessibility, `SMAppService` Login Item).
  2. Profile Unified Memory under stress (Xcode build + 16GB M-series Mac + sustained voice loop) and tune eviction thresholds.
  3. Package relocatable Python/MLX runtime inside `Selene.app`, codesign with Hardened Runtime (or appropriate entitlements for Python/Metal JIT), and configure Sparkle or GitHub-release notarized `.dmg` builds.