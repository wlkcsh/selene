# Selene — Native Apple Silicon AI Voice Companion Engine

Selene is a high-performance, local-first macOS voice assistant and desktop companion engine built specifically for Apple Silicon. Powered by **Gemini** (`google-genai`), **Kokoro-82M** (Apple Silicon MLX), **Silero v5** (CPU), optional **Metal RVC v2** (MPS GPU), **MLX-Whisper** (Speech-to-Text), **EventKit** (Apple Calendar & Reminders), **Screen Vision**, and **SQLite** persistent memory.

Designed from first principles as a **100% persona-agnostic engine**, Selene boots out-of-the-box with clean, neutral defaults while allowing developers to plug in custom personalities, vocal idiosyncrasies, and voice models via layered local configuration.

---

## 🏛️ Architecture

```text
Right Option PTT (Tink/Pop chimes)
  ├── Built-in Mic Isolation (Prevents Bluetooth SCO 16kHz audio degradation)
  ├── Passive <3ms App & Selection Context (NSWorkspace + AXUIElement)
  ├── RMS Silence Gate (>= 0.0012) & Acoustic Language ID (English / Russian)
  ├── Speculatively Pre-warmed MLX-Whisper STT (~0.17s) [or Groq Whisper fallback]
  │     └── Auto-evicted from Unified Memory after 180s idle (~464 MB reclaimed)
  ├── Gemini 3.5 Flash-Lite + 26 Safe Mac, Automations, Memory, Vision & Study Tools
  ├── First-Clause Fast-Start Streamer (<40 char trigger)
  ├── Bilingual Clause Router:
  │     ├── English -> Kokoro-82M (MLX Metal bf16)
  │     └── Russian -> Silero v5 CPU (with developer loanwords stress map & SSML pacing)
  ├── Audio Conversion:
  │     ├── Zero-Checkpoint Mode -> Passthrough 16kHz PCM (runs without weights)
  │     └── Voice Conversion -> Metal RVC v2 (MPS) with per-language acoustic profiles
  ├── GaplessSpeaker -> 16kHz / 48kHz CoreAudio output
  └── Darwin Memory Reclaimer -> malloc_zone_pressure_relief + MLX cache flush
```

---

### 📦 Package Layout

#### Python Core Daemon (`src/selene/`)
* `cli.py` — Main event loop, CLI argument parser, and `selene-voice` entrypoint
* `config.py` — Centralized frozen `SeleneConfig` with TOML and `SELENE_*` environment overrides
* `voice_router.py` — Bilingual clause-level TTS router (MLX Kokoro + Silero v5 with loanwords stress dictionary)
* `ear_engine.py` — 16 kHz CoreAudio recorder, passive Quartz `Right Option` PTT, built-in mic selector, acoustic language ID
* `tts_engine.py` — Apple Silicon MLX Kokoro-82M TTS (~120–220ms first clause) with polyphase resampling & click-free silence trimming
* `voice_engine.py` — Apple Silicon Metal RVC v2 (`.pth` + optional FAISS), `PassthroughRVCEngine` fallback, and `GaplessSpeaker`
* `memory_reclaimer.py` — Darwin `libSystem` `malloc_zone_pressure_relief`, MLX Metal BufferCache limits, and MPS pool flushing
* `apple_automations.py` — Natural language datetime parser and handlers for Calendar, Reminders, Notes, and Safari
* `spotify_resolver.py` — Headless track resolution via Spotify Web API with zero-credential iTunes Search fallback
* `mac_tools.py` — 26 safe macOS system, automation, memory, vision, timer, and study card tools
* `pipeline.py` — First-clause fast-start splitter and two-stage concurrent TTS/RVC streaming pipeline
* `memory_store.py` — Thread-safe SQLite history, rolling turn compaction, and permanent pinned `facts`
* `study_cards.py` — SQLite SM-2 spaced-repetition coding & study cards with review scheduling
* `workspace_context.py` — Passive `<3ms` active macOS app, window title, and highlighted selection snapshot
* `screen_vision.py` — On-demand silent window/display capture (JPEG <= 1568px) and Gemini multimodal vision
* `ipc_server.py` — Local Unix Domain Socket (`/tmp/selene.sock`) bidirectional JSON-RPC streaming server
* `timers.py` — Spoken study timers and macOS banner notifications
* `web_search.py` — Gemini Google Search grounding with zero-quota DuckDuckGo + Wikipedia fallback
* `persona.py` — External persona loader & stage-direction-safe speech sanitization
* `slash_commands.py` — Interactive `/help`, `/lang`, `/cards`, `/screen`, `/memory`, `/timers`, `/config`, `/mute`, `/compact`, `/forget`

#### Native Swift 6 HUD & Menu Bar (`hud/`)
* `main.swift` — Application entrypoint, non-activating AppKit window lifecycle, and NSApplication delegate
* `HUDView.swift` — Floating Dynamic Island / Notch capsule with Emil Kowalski spring animations
* `WaveformView.swift` — 60 FPS kinetic amber wave strictly during thinking states; energy-efficient static bars when idle
* `MenuBarController.swift` — Modern macOS Menu Bar control plane with live status header, SF Symbols, and language selector
* `EventKitAdapter.swift` — Native Swift actor interfacing directly with macOS `EKEventStore` for Calendar and Reminders
* `AutomationRouter.swift` — Host-side IPC router executing native automations and bundled AppleScript/JXA scripts
* `AutomationPermissionGuard.swift` — Off-main-thread TCC permission validation with silent background target launching
* `DaemonManager.swift` — Out-of-process Python daemon supervisor with zombie cleanup (`killStaleDaemon`)
* `QuickInputPanel.swift` — Spotlight-style floating text query bar (`Cmd + K`) for quiet environments
* `RightOptionHotkeyController.swift` — Global Quartz event tap listening for low-latency Push-to-Talk

---

## 🚀 Setup & Usage

### 1. Prerequisites
* Apple Silicon Mac (macOS 14+ recommended) with Python 3.12 (managed via `uv`)
* `GEMINI_API_KEY` set in your shell environment or `~/.zshrc`
* Optional: Custom RVC v2 voice model (`.pth` & `.index`) placed under `models/custom_voice/` (or configured in `config.toml`)

### 2. Install Dependencies
```bash
cd ~/selene
uv sync
```

### 3. Launch Selene as a Native macOS Application
You can run Selene completely terminal-free as a native macOS Application bundle:

```bash
./scripts/build_app.sh
```

This compiles the pure Swift 6 HUD, packages bundled automation scripts, and installs **`Selene.app`** directly into `/Applications`. Once built:
1. Open **Spotlight** (`Cmd + Space`) and type `Selene`.
2. A status icon appears in your **Menu Bar**, and the floating **Dynamic Island / Notch HUD** appears top-center.
3. Selene automatically manages and boots the background Python voice daemon.
4. Talk anytime by holding **`Right Option`** anywhere in macOS.
5. In quiet spaces, press **`Cmd + K`** to open the Spotlight-style Quick Input bar and type your question.
6. The Menu Bar gives you full control: Start/Stop voice engine, Mute, Switch Language (`AUTO` / `EN` / `RU`), Review study cards, and View Console activity logs.

---

### Alternative: CLI Terminal Mode

If you prefer running directly in a terminal tab:
```bash
# Fast mode (zero-checkpoint pure TTS, lowest latency)
uv run selene-voice --fast

# Full voice engine with RVC (if model weights are configured)
uv run selene-voice

# Run the native HUD companion alongside the terminal engine
./scripts/run_hud.sh
```

---

## ⚙️ 3-Tier Configuration & Pluggable Personas

Selene cleanly separates **system mechanics** (Git-tracked engine) from **persona styling and voice models** (uncommitted local config):

```text
Layer 1: Repo Defaults (Git-tracked, 100% neutral & immediately runnable)
  └── config.example.toml   # rvc_enabled = false, neutral language routing, clean prompts

Layer 2: User Workspace (Local, git-ignored, keeps your custom persona & models)
  ├── config.toml           # Voice models, speaker selection, custom style directives
  └── .env                  # API keys and optional build signing identity (SELENE_SIGN_IDENTITY)

Layer 3: Environment Variables (CI / ad-hoc shell overrides)
  └── SELENE_MODEL_ID, SELENE_WHISPER_LANGUAGE, SELENE_RVC_ENABLED, etc.
```

### Customizing Your Setup
Copy `config.example.toml` to `config.toml` (git-ignored) to customize your voice and tone:

```toml
[voice]
rvc_enabled = true                             # Enable Metal RVC v2 inference
model_workdir = "~/selene/models/custom_voice"
rvc_model_path = "model.pth"
rvc_index_path = "model.index"
russian_speaker = "baya"                       # "baya" | "kseniya" | "xenia"

[languages.ru]
# Optional character tone guidance appended to Russian prompt directives
style_directive = "authentic, idiomatic native Russian as a warm, knowledgeable technical mentor..."

[languages.en]
# Optional character tone guidance appended to English prompt directives
style_directive = "clear, concise, and helpful..."

[ears]
prefer_builtin_mic = true                      # Always use internal mic to keep Bluetooth audio in high-res mode
whisper_language = "auto"                      # "auto" | "en" | "ru"
```

---

## ⌨️ Interactive Slash Commands

When running in terminal mode or via `Cmd + K`:
* `/help` — Show all commands
* `/lang [en|ru|auto]` — Switch active language mode and auto-detection policy
* `/cards` — View due spaced-repetition coding and study cards
* `/screen [q]` — Capture frontmost window and ask Selene about it
* `/memory` — Inspect pinned facts, rolling summary, and conversation state
* `/timers` — List active spoken study timers
* `/config` — Inspect active model, voice, pitch, and path configuration
* `/mute` — Toggle quiet text-only mode (mutes voice & PTT chimes)
* `/compact` — Compact recent conversation turns into long-term summary immediately
* `/forget` — Clear conversation history while keeping pinned facts (`/forget all` wipes everything)

---

## 🧪 Development & Testing

```bash
# Fast offline unit tests (70 tests in ~2s)
uv run pytest -v

# Code formatting and linting
uv run ruff check src tests

# Native Swift HUD compilation
swift build --package-path hud

# Full pre-flight verification across Python and Swift
./scripts/git-workflow.sh check
```

---

## 🌳 Branching Strategy & Contributing

We follow a structured GitFlow-style multi-branch model:

* **`main`**: Production-ready, tagged releases only (`vX.Y.Z`).
* **`develop`**: Active integration branch. All feature branches and routine fixes merge here.
* **`feature/<name>`**: New capabilities branched from `develop`.
* **`fix/<name>`**: Routine bug fixes branched from `develop`.
* **`hotfix/<name>`**: Urgent production fixes branched from `main` and backported to `develop`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full pull request guidelines and architecture invariants.
