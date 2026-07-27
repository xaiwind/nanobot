from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.agent.tools.video_generation import VideoGenerationToolConfig


def test_default_config():
    cfg = VideoGenerationToolConfig()
    assert cfg.enabled is False
    assert cfg.provider == "xai_grok"
    assert cfg.model == "grok-imagine-video"
    assert cfg.default_duration == 5
    assert cfg.default_aspect_ratio == "16:9"
    assert cfg.save_dir == "generated"


def test_config_disabled_by_default():
    cfg = VideoGenerationToolConfig()
    assert not cfg.enabled
