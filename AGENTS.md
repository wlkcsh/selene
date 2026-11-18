# Selene Workspace Guide (`AGENTS.md`)

Concise architecture map and non-negotiable macOS invariants for working inside `/Users/mac/selene`.

## Project Layout
* Package source: `src/selene/` (each module strictly cohesive and under ~300 lines)
* Unit & integration tests: `tests/`
* Local weights (git-ignored): `models/custom_voice/custom_voice/`
* Archived Phase 1 script: `archive/selene_phase1.py`
* External companion files:
  * Persona: `~/.gemini/GEMINI.md`
  * Persistent SQLite DB: `~/.gemini/selene_memory.db`
  * Shell alias (`~/.zshrc`): `alias selene-voice='uv run --project ~/selene selene-voice'`

## Critical macOS Invariants (DO NOT BREAK)
1. **Python 3.12 Pin (`.python-version`):** `torch`, `faiss-cpu`, `spacy`, and `kokoro` require Python `3.12` (`>=3.12,<3.13`). Do not upgrade to 3.14/3.15 until wheels exist.
2. **Environment Vars & `faiss` Before `torch`:** `selene.cli` sets `OMP_NUM_THREADS=1`, `KMP_DUPLICATE_LIB_OK=TRUE`, `PYTORCH_ENABLE_MPS_FALLBACK=1`, `TOKENIZERS_PARALLELISM=false`, and `TORCH_CPP_LOG_LEVEL=ERROR` **before** importing `selene.voice_engine`. Inside `selene.voice_engine`, `import faiss` MUST stay above `import torch` to prevent macOS OpenMP crashes.
3. **`rvc` Namespace Isolation:** Never add `/Applications/Applio.app/Contents/Resources` to `sys.path` — Applio bundles stale `aiohttp`/`pytz` stubs that break `google-genai` and `kokoro`. Always use `_register_rvc_namespace()`.
4. **`os.chdir(model_workdir)` Side-Effect:** `MetalRVCEngine` and `boot_voice_engines()` change CWD to `cfg.model_workdir` for relative RVC weights. Always call `load_config()` *before* booting voice engines, and resolve repo paths from `PROJECT_ROOT` (`Path(__file__).resolve().parents[2]`), never `Path.cwd()`.
5. **Gemini Tool Signatures:** Functions returned by `build_jarvis_tools()` must keep simple JSON-schema-friendly parameter types (`str`, `int`) — bind `MemoryStore` and `SeleneConfig` via closures, never as tool parameters.
6. **Security Guardrails:** `read_text_file()` must stay restricted to `Path.home()`, reject binaries, and block `.env*`, shell rc files, SSH/cloud key dirs, and `*.pem`/`*.key`.

## Verification Commands
```bash
# Sync dependencies into unified .venv
uv sync

# Fast offline unit tests (< 1s)
uv run pytest -v

# Ruff lint check
uv run ruff check src tests

# CLI smoke test from outside the repo
cd ~ && uv run --project ~/selene selene-voice --help

# Live GPU + MLX-Whisper + Metal RVC verification
uv run pytest -m integration -v -s
```
