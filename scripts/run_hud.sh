#!/usr/bin/env bash
# Launch the native Selene HUD (SwiftUI + AppKit floating panel & MenuBarExtra)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

HUD_BIN="${REPO_ROOT}/hud/.build/release/SeleneHUD"

echo "📦 Ensuring SeleneHUD is up to date..."
(cd "${REPO_ROOT}/hud" && swift build -c release -q)

if [[ -d "/Applications/Selene.app" ]]; then
    echo "✨ Launching /Applications/Selene.app..."
    open /Applications/Selene.app
    exit 0
fi

echo "✨ Launching Selene HUD binary..."
exec "${HUD_BIN}" "$@"
