## 🌸 Pull Request Details

### 1. Target Branch & PR Type
- [ ] Target Branch is **`develop`** (Standard features, bug fixes, refactoring)
- [ ] Target Branch is **`main`** (Critical production hotfix only)

**Type of Change:**
- [ ] `feat` — New feature or capability
- [ ] `fix` — Bug fix or error resolution
- [ ] `perf` — Latency, CPU, or VRAM performance improvement
- [ ] `refactor` — Code restructuring without behavioral change
- [ ] `docs` — Documentation or blueprint updates
- [ ] `test` — New or improved test coverage

---

### 2. Description & Motivation
<!-- Provide a clear, concise summary of what this PR does and why. Link any related issues with `#issue_number`. -->

**Summary:**

**Related Issue(s):**
Fixes #

---

### 3. Architecture & Core Invariants Checklist
<!-- Please verify that your changes adhere to Selene's macOS invariants: -->
- [ ] **Python 3.12**: No unsupported packages or version bumps breaking MPS/Torch.
- [ ] **OpenMP Safety**: `faiss` import remains above `torch` where applicable.
- [ ] **Non-Activating HUD**: Floating panel does not steal focus from code editors.
- [ ] **Tool Signatures**: Function calling schemas in `mac_tools.py` use JSON-safe types.
- [ ] **Security Guardrails**: No leakage of `.env`, SSH keys, or private SQLite state.

---

### 4. Verification & Testing
<!-- Detail the exact steps and tests you ran to verify this change. -->

- [ ] Offline Unit Tests passed: `uv run pytest -v`
- [ ] Linter passed: `uv run ruff check src tests`
- [ ] Swift Engine compiled cleanly: `swift build --package-path hud`
- [ ] Standalone App verified (if UI touched): `./scripts/build_app.sh`

**Test Output / Screenshots / Telemetry:**
```text
<!-- Paste test results or telemetry output here -->
```

---

### 5. Final Checklist
- [ ] My branch is rebased onto the latest `develop` (or `main` for hotfix).
- [ ] My commits adhere to [Conventional Commits](https://www.conventionalcommits.org/).
- [ ] Any new public methods or configuration keys are documented in `README.md` and `config.example.toml`.
