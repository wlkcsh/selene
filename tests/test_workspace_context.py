"""Tests for passive <3ms macOS workspace context and privacy filters."""

from unittest.mock import MagicMock, patch

from selene.workspace_context import (
    WorkspaceContext,
    capture_workspace_context,
    format_context_prefix,
    is_sensitive_context,
)


def test_is_sensitive_context_detects_passwords_and_secrets():
    assert is_sensitive_context("1Password") is True
    assert is_sensitive_context("Bitwarden") is True
    assert is_sensitive_context("Keychain Access") is True
    assert is_sensitive_context("KeePassXC") is True
    assert is_sensitive_context("Google Chrome", "Editing .env.production") is True
    assert is_sensitive_context("Cursor", "id_rsa - Private Key") is True
    assert is_sensitive_context("VS Code", "api_credentials.pem") is True

    # Safe IDE/Browser contexts
    assert is_sensitive_context("Cursor", "voice_engine.py — selene") is False
    assert is_sensitive_context("Safari", "Python 3.12 Documentation") is False


def test_format_context_prefix():
    assert format_context_prefix(None) == ""

    ctx_app_only = WorkspaceContext(app_name="Spotify")
    assert format_context_prefix(ctx_app_only) == "[Active Context — App: Spotify]\n\n"

    ctx_with_window = WorkspaceContext(app_name="Cursor", window_title="voice_engine.py")
    assert (
        format_context_prefix(ctx_with_window)
        == "[Active Context — App: Cursor | Window: voice_engine.py]\n\n"
    )

    ctx_with_selection = WorkspaceContext(
        app_name="Cursor",
        window_title="voice_engine.py",
        selected_text="def convert_pcm16k():\n    pass",
    )
    expected = (
        "[Active Context — App: Cursor | Window: voice_engine.py]\n"
        "[Selected Text]:\n"
        "def convert_pcm16k():\n    pass\n"
        "[End Context]\n\n"
    )
    assert format_context_prefix(ctx_with_selection) == expected


def test_capture_workspace_context_privacy_and_terminal_suppression():
    # If app is sensitive, returns None
    fake_app = MagicMock()
    fake_app.localizedName.return_value = "1Password 7"
    mock_appkit = MagicMock()
    mock_appkit.NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value = fake_app

    with patch("selene.workspace_context.HAS_AX", True), patch(
        "selene.workspace_context.AppKit", mock_appkit
    ):
        assert capture_workspace_context() is None

    # If app is Terminal with no selection, returns None to avoid cluttering normal chats
    term_app = MagicMock()
    term_app.localizedName.return_value = "Terminal"
    term_app.processIdentifier.return_value = 1234
    mock_appkit_term = MagicMock()
    mock_appkit_term.NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value = term_app

    with patch("selene.workspace_context.HAS_AX", True), patch(
        "selene.workspace_context.AppKit", mock_appkit_term
    ), patch("selene.workspace_context.AS.AXIsProcessTrusted", return_value=True), patch(
        "selene.workspace_context._ax_attr", return_value=None
    ):
        assert capture_workspace_context() is None
