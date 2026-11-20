#!/usr/bin/env bash
# Build and install Selene.app for macOS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_VERSION="$(grep -m1 '^version = ' "${REPO_ROOT}/pyproject.toml" | cut -d'"' -f2 || echo "2.5.0")"

if [[ -f "${REPO_ROOT}/.env.build" ]]; then
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.env.build"
fi

echo "🌸 ============================================="
echo "   Building Selene Standalone macOS Application"
echo "   ============================================="

# 1. Build release binary for Swift HUD & Daemon Controller
echo "📦 Compiling Selene Swift engine (release)..."
(cd "${REPO_ROOT}/hud" && swift build -c release)

# 2. Generate AppIcon.icns if needed
if [[ ! -f "${REPO_ROOT}/AppIcon.icns" ]]; then
    echo "✨ Generating high-resolution AppIcon.icns..."
    swift "${REPO_ROOT}/scripts/generate_icon.swift"
    iconutil -c icns "${REPO_ROOT}/Selene.iconset" -o "${REPO_ROOT}/AppIcon.icns"
    rm -rf "${REPO_ROOT}/Selene.iconset"
fi

# 3. Assemble App Bundle
BUILD_DIR="${REPO_ROOT}/build"
APP_BUNDLE="${BUILD_DIR}/Selene.app"
CONTENTS="${APP_BUNDLE}/Contents"
MACOS="${CONTENTS}/MacOS"
RESOURCES="${CONTENTS}/Resources"

echo "🔨 Assembling ${APP_BUNDLE}..."
rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS}" "${RESOURCES}"

cp "${REPO_ROOT}/hud/.build/release/SeleneHUD" "${MACOS}/Selene"
chmod +x "${MACOS}/Selene"
cp "${REPO_ROOT}/AppIcon.icns" "${RESOURCES}/AppIcon.icns"

if [[ -d "${REPO_ROOT}/hud/Resources/Automations" ]]; then
    echo "📜 Packaging bundled automation scripts..."
    mkdir -p "${RESOURCES}/Automations"
    cp -R "${REPO_ROOT}/hud/Resources/Automations/"* "${RESOURCES}/Automations/"
fi

cat <<EOF > "${CONTENTS}/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Selene</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.selene.assistant</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Selene</string>
    <key>CFBundleDisplayName</key>
    <string>Selene</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${APP_VERSION}</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Selene requires microphone access for voice input and push-to-talk.</string>
    <key>NSSpeechRecognitionUsageDescription</key>
    <string>Selene uses local speech recognition to understand your questions.</string>
    <key>NSScreenCaptureUsageDescription</key>
    <string>Selene requires screen recording permission for on-demand vision queries.</string>
    <key>NSCalendarsUsageDescription</key>
    <string>Selene creates and views calendar events on your schedule when you ask.</string>
    <key>NSCalendarsFullAccessUsageDescription</key>
    <string>Selene creates and views calendar events on your schedule with full native access when you ask.</string>
    <key>NSRemindersUsageDescription</key>
    <string>Selene creates and views reminders for your tasks when you ask.</string>
    <key>NSRemindersFullAccessUsageDescription</key>
    <string>Selene creates and views reminders for your tasks with full native access when you ask.</string>
    <key>NSAppleEventsUsageDescription</key>
    <string>Selene uses macOS Automation to control apps like Spotify, Calendar, Reminders, Notes, and Safari when you ask.</string>
</dict>
</plist>
EOF

echo -n "APPL????" > "${CONTENTS}/PkgInfo"

# Code sign: prefer stable local developer certificate if present, fallback to ad-hoc
SIGN_IDENTITY="${SELENE_SIGN_IDENTITY:-Selene Local Dev}"
if [[ -n "${SIGN_IDENTITY}" ]] && security find-certificate -c "${SIGN_IDENTITY}" >/dev/null 2>&1; then
    echo "🔐 Signing with stable developer certificate '${SIGN_IDENTITY}'..."
    codesign --force --deep --options runtime \
      --sign "${SIGN_IDENTITY}" \
      --requirements "=designated => identifier \"com.selene.assistant\" and certificate leaf[subject.CN] = \"${SIGN_IDENTITY}\"" \
      "${APP_BUNDLE}"
else
    echo "ℹ️  '${SIGN_IDENTITY}' certificate not found in Keychain; signing ad-hoc..."
    codesign --force --deep --sign - -r='designated => identifier "com.selene.assistant"' "${APP_BUNDLE}"
fi

# 4. Install to /Applications (skip if --no-install or NO_INSTALL=1)
if [[ "${1:-}" == "--no-install" || "${NO_INSTALL:-0}" == "1" ]]; then
    echo "💖 Done! Selene.app built successfully at ${APP_BUNDLE} (skipped /Applications install)."
    exit 0
fi

INSTALL_TARGET="/Applications/Selene.app"
echo "🚀 Installing to ${INSTALL_TARGET}..."
rm -rf "${INSTALL_TARGET}"
cp -R "${APP_BUNDLE}" "${INSTALL_TARGET}"

# Touch /Applications to inform LaunchServices / Spotlight
touch "/Applications" 2>/dev/null || true
touch "${INSTALL_TARGET}" 2>/dev/null || true

# Register with LaunchServices & Spotlight
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "${INSTALL_TARGET}"
mdimport "${INSTALL_TARGET}" 2>/dev/null || true

echo "💖 Done! Selene.app is installed and ready in /Applications."
echo "   You can launch it from Spotlight (Cmd + Space -> Selene), Finder, or run:"
echo "   open /Applications/Selene.app"
