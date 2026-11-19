# Selene — Custom Anime Voice AI Assistant (macOS)

Selene is a local-first, voice-in / voice-out macOS anime mentor & personal Jarvis assistant powered by **Gemini** (`google-genai`), **Kokoro-82M** (Apple Silicon MLX or PyTorch CPU), **RVC v2** (Apple Silicon Metal MPS GPU), **MLX-Whisper** (local Speech-to-Text), **Screen Vision**, and **SQLite** persistent memory.

---

## Architecture

```text
Right Option PTT (Tink/Pop chimes)
  -> Passive <3ms App & Selection Context (NSWorkspace + AXUIElement)
  -> RMS Silence Gate (>= 0.004)
  -> Pre-warmed MLX-Whisper STT (~0.17s) [or Groq Whisper fallback]
  -> Gemini 3.5 Flash-Lite + 20 Safe Mac / Memory / Vision / Card Tools
  -> First-Clause Fast-Start Streamer (Clause 1 RVC Index-Skip)
  -> Kokoro-82M (MLX bf16 / CPU) -> Metal RVC v2 (MPS) -> 48kHz Stereo GaplessSpeaker
```

### Package Layout

* `src/selene/cli.py` — Main event loop, CLI argument parser, and `selene-voice` entrypoint
* `src/selene/config.py` — Frozen `SeleneConfig` loaded from defaults → `config.toml` → `SELENE_*` env vars
* `src/selene/ear_engine.py` — Persistent 16 kHz CoreAudio mic, passive Quartz `Right Option` PTT tap, chimes, RMS gate, MLX/Groq STT
* `src/selene/tts_engine.py` — Apple Silicon MLX Kokoro-82M TTS (~120–220ms first clause) with PyTorch CPU fallback & polyphase resampling
* `src/selene/voice_engine.py` — Apple Silicon Metal RVC (`.pth` + optional FAISS with Clause 1 skip-index), 48 kHz `GaplessSpeaker`
* `src/selene/pipeline.py` — First-clause fast-start splitter & two-stage concurrent TTS/RVC streaming pipeline
* `src/selene/memory_store.py` — Thread-safe SQLite history, rolling compaction, and permanent pinned `facts`
* `src/selene/study_cards.py` — SQLite SM-2 spaced-repetition coding & study cards with review scheduling
* `src/selene/workspace_context.py` — Passive `<3ms` active macOS app, window title, and highlighted code/text snapshot
* `src/selene/screen_vision.py` — On-demand silent window/display capture (JPEG <= 1568px) and Gemini multimodal vision
* `src/selene/ipc_server.py` — Local Unix Domain Socket (`/tmp/selene.sock`) NDJSON streaming server
* `src/selene/mac_tools.py` — 20 safe macOS, Memory, Screen Vision, and Study Card Jarvis tools
* `src/selene/timers.py` — Spoken study timers + macOS banner notifications
* `src/selene/web_search.py` — Gemini Google Search grounding with zero-quota DuckDuckGo + Wikipedia fallback
* `src/selene/persona.py` — `GEMINI.md` persona loader & stage-direction-safe speech cleaner
* `src/selene/slash_commands.py` — Interactive `/help`, `/cards`, `/screen`, `/memory`, `/timers`, `/config`, `/mute`, `/compact`, `/forget`
* `hud/` — Native Swift 6 SwiftUI + AppKit floating HUD pill (`NSPanel`) and MenuBarExtra (324 KB binary, ~18 MB RAM)

---

## Setup & Usage

### 1. Prerequisites
* Apple Silicon Mac (macOS) with `uv` installed and Python 3.12 (pinned in `.python-version`)
* `GEMINI_API_KEY` set in your shell environment or `~/.zshrc`
* Read-only RVC library installed at `/Applications/Applio.app`
* Optional: Custom RVC v2 voice model (`.pth` & `.index`) placed under `~/selene/models/custom_voice/` (or configured in `config.toml`)

### 2. Install Dependencies
```bash
cd ~/selene
uv sync
```

### 3. Launch Selene as a Standalone App (No Terminal Required!)

You can run Selene completely terminal-free as a native macOS Application:

```bash
./scripts/build_app.sh
```

This compiles and installs **`Selene.app`** directly into `/Applications`. Once built:
1. Open **Spotlight** (`Cmd + Space`) and type `Selene` (or launch from Finder / Launchpad / Raycast).
2. A sparkling heart icon appears in your **Menu Bar**, and the floating **Dynamic Island / Notch HUD** appears top-center.
3. Selene automatically manages and boots the background voice engine daemon for you.
4. Talk anytime by holding **`Right Option`** anywhere in macOS.
5. In quiet spaces, click **`💬 Ask Selene...`** in the Menu Bar (or press `Cmd + K`) to bring up the Spotlight-style Quick Input bar and type your question.
6. The Menu Bar gives you full control: Start/Stop voice engine, Mute, Notch vs Floating pill mode, Review study cards, and View activity logs.

---

### Alternative: CLI Terminal Mode

If you prefer running directly in a terminal tab:
```bash
# Fast mode (pure .pth — lowest latency)
selene-voice --fast

# Full FAISS voice fidelity
selene-voice

# Run HUD companion
./scripts/run_hud.sh
```

### 4. Global Eyes-Free Push-to-Talk (`Right Option`)
To hold **`Right Option`** from any macOS app (VS Code, Safari, etc.):
1. Open **System Settings → Privacy & Security → Accessibility**.
2. Enable your terminal app (Kitty, Terminal, or iTerm2).
3. If Accessibility isn't granted, Selene automatically falls back to **`Enter`-toggle mic mode** (press `Enter` on an empty line to start/stop recording).

### 5. Interactive Slash Commands
* `/help` — Show all commands
* `/cards` — View due spaced-repetition coding/study cards
* `/screen [q]` — Capture frontmost window and ask Selene about it
* `/memory` — Inspect pinned facts, rolling summary, and unsummarized message count
* `/timers` — List active spoken study timers
* `/config` — View active model, voice, pitch, and paths
* `/mute` — Toggle quiet text-only mode (mutes voice & PTT chimes)
* `/compact` — Compact recent turns into long-term summary immediately
* `/forget` — Wipe chat history & summary while keeping pinned facts (`/forget all` wipes everything)

---

## Customizing Configuration

Copy `config.example.toml` to `config.toml` (git-ignored) and edit any section (`[llm]`, `[voice]`, `[ears]`, `[memory]`, `[paths]`), or pass environment overrides like:

```bash
SELENE_RVC_PITCH=2 selene-voice --fast
```

---

## Development & Testing

```bash
# Fast offline unit tests (< 1s)
uv run pytest -v

# Linting
uv run ruff check src tests

# Live GPU + Kokoro + Metal RVC + MLX-Whisper integration test
uv run pytest -m integration -v -s

# Automated pre-flight check across Python and Swift
./scripts/git-workflow.sh check
```

---

## 🌳 Branching Strategy & Contributing

We follow a structured GitFlow-style multi-branch model:

* **`main`**: Production-ready, tagged releases only (`v0.x.x`). Never commit directly.
* **`develop`**: Active integration branch. All feature branches and routine fixes merge here.
* **`feature/<name>`**: New capabilities branched from `develop`.
* **`fix/<name>`**: Routine bug fixes branched from `develop`.
* **`hotfix/<name>`**: Urgent production fixes branched from `main` and backported to `develop`.

To start working on a feature or fix:
```bash
./scripts/git-workflow.sh start feature my-new-feature
# or
./scripts/git-workflow.sh start fix my-bug-fix
```

See [CONTRIBUTING.md](file:///Users/mac/selene/CONTRIBUTING.md) for full pull request guidelines and architecture invariants.

