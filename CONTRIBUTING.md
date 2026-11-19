# Contributing to Selene

First off, thank you for taking the time to contribute! Whether you're fixing a bug, adding a new voice engine capability, or improving the native macOS HUD, your contributions help make Selene the most refined desktop anime mentor and voice companion on Apple Silicon.

---

## 🌳 Branching Strategy

Selene follows a structured **GitFlow-inspired branching strategy** designed to ensure the production `main` branch remains rock-solid while active feature development continues smoothly.

```text
[main] ─────────────────────●──────────────●──────── (Production Releases)
                             ▲              ▲
                              \ [release]  / [hotfix]
                               \          /
[develop] ──●──────●────────────●────────●─────────── (Active Integration)
             \    / \          /
    [feature] ──●─   ─[fix]──●─
```

### Core Branches

| Branch | Stability | Description |
| :--- | :--- | :--- |
| **`main`** | **Production-Ready** | Only contains stable, tested release code. Tagged with version numbers (e.g. `v0.3.0`). **Never commit directly to `main`**. |
| **`develop`** | **Integration** | The default target for all new features and routine bug fixes. Nightly builds and active development live here. |

### Supporting Branches

| Branch Prefix | Source Branch | Target Branch | Purpose | Example |
| :--- | :--- | :--- | :--- | :--- |
| `feature/` or `feat/` | `develop` | `develop` | New features, integrations, or capabilities | `feature/whisper-turbo` |
| `fix/` or `bugfix/` | `develop` | `develop` | Routine bug fixes and test repairs | `fix/ptt-hangover-jitter` |
| `hotfix/` | `main` | `main` & `develop` | Critical emergency fixes for production bugs | `hotfix/openmp-crash-guard` |
| `release/` | `develop` | `main` & `develop` | Release candidate preparation and version bumps | `release/v0.4.0` |
| `docs/` | `develop` | `develop` | Documentation, guides, and diagrams | `docs/architecture-flowchart` |

---

## 🛠️ Step-by-Step Contribution Workflow

### 1. Fork & Clone
Fork the repository on GitHub, then clone your fork locally:
```bash
git clone https://github.com/<your-username>/selene.git
cd selene
```

### 2. Create Your Working Branch
Always branch from **`develop`** (unless you are working on an emergency production `hotfix` targeting `main`):

```bash
# Ensure develop is up to date
git checkout develop
git pull origin develop

# For a new feature:
git checkout -b feature/your-feature-name develop

# For a bug fix:
git checkout -b fix/issue-description develop
```

> **Tip:** You can also use `./scripts/git-workflow.sh start feature your-feature-name` to automate this.

### 3. Local Development Setup
Ensure your local environment meets the Apple Silicon requirements:
* macOS Sonoma 14+ on Apple Silicon (M1/M2/M3/M4)
* Python 3.12 pinned via `.python-version`
* `uv` package manager (`brew install uv`)
* Xcode 15+ / Swift 6 toolchain (`xcode-select --install`)

Sync virtual environment and test offline:
```bash
# Sync dependencies
uv sync

# Run offline unit tests (< 1.5s)
uv run pytest -v

# Run Python linter
uv run ruff check src tests

# Verify Swift HUD compilation
swift build --package-path hud
```

### 4. Commit Your Changes
We adhere strictly to [Conventional Commits](https://www.conventionalcommits.org/):
* `feat:` A new feature or user-facing capability
* `fix:` A bug fix or patch
* `docs:` Documentation-only changes
* `refactor:` Code change that neither fixes a bug nor adds a feature
* `perf:` Performance improvements (e.g. latency reduction, VRAM optimization)
* `test:` Adding or updating tests
* `chore:` Build process, tooling, or dependency updates

**Example:**
```bash
git commit -m "feat(hud): add customizable waveform smoothing curve"
```

### 5. Run Verification Before Pushing
Run all tests and linters to ensure green status before opening your PR:
```bash
./scripts/git-workflow.sh check
# Or manually:
uv run pytest -v
uv run ruff check src tests
swift build --package-path hud
```

### 6. Submit a Pull Request
1. Push your branch to your fork:
   ```bash
   git push -u origin feature/your-feature-name
   ```
2. Open a Pull Request on GitHub.
3. **Verify the Target Branch**:
   * For standard features and fixes: target **`develop`** (not `main`!).
   * For critical production emergency patches: target **`main`**.
4. Fill in the provided Pull Request template completely.

---

## 🚀 Releasing & Automatic Tagging

When preparing a production release:
1. Ensure all features for the milestone are merged into `develop`.
2. Run the automated release workflow from your Mac:
   ```bash
   ./scripts/git-workflow.sh release 2.5.0
   ```
3. This helper will:
   * Verify all tests pass locally (`pytest`, `ruff`, `swift build`).
   * Bump the version in `pyproject.toml`.
   * Create a signed Git tag `v2.5.0` on `main`.
   * Push the commit and tag to GitHub, then merge back to `develop`.
4. **GitHub Actions Release CI** will automatically:
   * Compile the standalone macOS application bundle (`Selene.app`).
   * Compress it into a standalone Apple Silicon archive (`Selene-v2.5.0-macOS-arm64.zip`).
   * Generate release notes from commit history.
   * Publish the official GitHub Release with downloadable assets.

---

## ⚖️ Code & Architectural Invariants

Before submitting, please make sure your changes respect Selene's core invariants:

1. **Python 3.12 Pin**: Do not upgrade Python version beyond 3.12 without verifying `faiss-cpu`, `spacy`, and `torch` compatibility.
2. **Import Ordering in Voice Engine**: Inside `src/selene/voice_engine.py`, `import faiss` must ALWAYS precede `import torch` to prevent OpenMP runtime crashes on macOS.
3. **Process Isolation & Non-Activating HUD**:
   * Clicks on the floating HUD must never steal key keyboard focus from active editors (`NSPanel.nonactivatingPanel`).
   * Daemon processes must be cleanly terminated upon app shutdown (`/tmp/selene.sock` unlinked).
4. **Tool Signatures**: Tools in `src/selene/mac_tools.py` must use simple JSON types (`str`, `int`) compatible with Gemini Function Calling schemas.
5. **No Monolithic Bloat**: Keep modules cohesive and focused (< 350 lines).

---

## 💖 Questions or Ideas?

Feel free to open an **Issue** or start a **Discussion** on GitHub! We're thrilled to build alongside you.
