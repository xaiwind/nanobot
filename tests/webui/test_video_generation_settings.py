from __future__ import annotations

import pytest
from nanobot.webui.settings_api import update_video_generation_settings
from nanobot.webui.settings_api import WebUISettingsError


def test_update_enabled(tmp_path, monkeypatch):
    from unittest.mock import patch
    from nanobot.config.schema import Config

    config = Config()
    with patch("nanobot.webui.settings_api.load_config", return_value=config), \
         patch("nanobot.webui.settings_api.save_config"):
        result = update_video_generation_settings({"enabled": ["true"]})

    assert result["video_generation"]["enabled"] is True


def test_update_model(tmp_path, monkeypatch):
    from unittest.mock import patch
    from nanobot.config.schema import Config

    config = Config()
    with patch("nanobot.webui.settings_api.load_config", return_value=config), \
         patch("nanobot.webui.settings_api.save_config"):
        result = update_video_generation_settings({"model": ["grok-imagine-video-1.5"]})

    assert result["video_generation"]["model"] == "grok-imagine-video-1.5"


def test_update_rejects_empty_model():
    from unittest.mock import patch
    from nanobot.config.schema import Config

    config = Config()
    with patch("nanobot.webui.settings_api.load_config", return_value=config), \
         patch("nanobot.webui.settings_api.save_config"):
        with pytest.raises(WebUISettingsError, match="model"):
            update_video_generation_settings({"model": [""]})


def test_update_duration_bounds():
    from unittest.mock import patch
    from nanobot.config.schema import Config

    config = Config()
    with patch("nanobot.webui.settings_api.load_config", return_value=config), \
         patch("nanobot.webui.settings_api.save_config"):
        with pytest.raises(WebUISettingsError, match="duration"):
            update_video_generation_settings({"defaultDuration": ["99"]})
