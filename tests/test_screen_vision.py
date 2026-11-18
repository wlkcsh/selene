"""Tests for macOS Screen Vision capture and Gemini multimodal analysis."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from selene.config import SeleneConfig
from selene.screen_vision import capture_screen_jpeg, inspect_screen


def test_capture_screen_jpeg_cleans_up_temp_file_on_success_and_failure(tmp_path: Path):
    captured_paths: list[Path] = []

    def fake_subprocess(cmd, **kwargs):
        if cmd[0] == "screencapture":
            out_file = Path(cmd[-1])
            captured_paths.append(out_file)
            out_file.write_bytes(b"\xff\xd8\xff\xe0mockjpeg")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("selene.screen_vision.subprocess.run", side_effect=fake_subprocess):
        data = capture_screen_jpeg(scope="display", max_edge=1024, quality=70)
        assert data == b"\xff\xd8\xff\xe0mockjpeg"
        assert len(captured_paths) == 1
        # Invariant: temp file must be unlinked in finally:
        assert not captured_paths[0].exists()

    # Failure path: screencapture fails
    def fail_subprocess(cmd, **kwargs):
        if cmd[0] == "screencapture":
            out_file = Path(cmd[-1])
            captured_paths.append(out_file)
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="permission denied")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("selene.screen_vision.subprocess.run", side_effect=fail_subprocess):
        with pytest.raises(RuntimeError) as exc_info:
            capture_screen_jpeg(scope="display")
        assert "Screen Recording" in str(exc_info.value)
        # Temp file must still be unlinked on failure
        assert not captured_paths[-1].exists()


def test_inspect_screen_multimodal_gemini_call(isolated_cfg: SeleneConfig):
    fake_jpeg = b"\xff\xd8\xff\xe0mockjpeg"
    mock_resp = MagicMock()
    mock_resp.text = "You have a syntax error on line 42 of voice_engine.py."

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    with patch("selene.screen_vision.capture_screen_jpeg", return_value=fake_jpeg), patch(
        "selene.screen_vision.genai.Client", return_value=mock_client
    ):
        result = inspect_screen("What is failing?", scope="front_window", cfg=isolated_cfg)
        assert "syntax error on line 42" in result
        mock_client.models.generate_content.assert_called_once()
