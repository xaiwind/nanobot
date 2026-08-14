from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from nanobot.agent.tools.loader import ToolLoader
from nanobot.agent.tools.video_generation import (
    VideoGenerationTool,
    VideoGenerationToolConfig,
)
from nanobot.providers.video_generation import (
    GeneratedVideoResponse,
    VideoGenerationError,
)


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


def test_tool_is_concrete_and_discoverable():
    """The loader skips classes with unimplemented abstract methods.

    A stray abstract method silently drops the tool from the registry, so the
    agent never sees it. Guard the interface rather than only the config.
    """
    assert not getattr(VideoGenerationTool, "__abstractmethods__", None)
    discovered = ToolLoader().discover()
    assert any(cls.__name__ == "VideoGenerationTool" for cls in discovered)


def test_tool_exposes_expected_name():
    tool = VideoGenerationTool(config=VideoGenerationToolConfig())
    assert tool.name == "generate_video"
    assert tool.description


class _FakeProvider:
    last_kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        self.init_kwargs = kwargs

    async def generate(self, **kwargs: Any) -> GeneratedVideoResponse:
        _FakeProvider.last_kwargs = kwargs
        return GeneratedVideoResponse(
            local_path="/tmp/out.mp4", duration=5.0, model=kwargs["model"]
        )


@pytest.mark.asyncio
async def test_execute_generates_with_configured_defaults():
    config = VideoGenerationToolConfig(enabled=True)
    tool = VideoGenerationTool(config=config)

    with patch(
        "nanobot.agent.tools.video_generation.get_video_gen_provider",
        return_value=_FakeProvider,
    ):
        result = await tool.execute(prompt="a rotating cube")

    assert "/tmp/out.mp4" in result
    assert _FakeProvider.last_kwargs["model"] == "grok-imagine-video"
    assert _FakeProvider.last_kwargs["duration"] == 5
    assert _FakeProvider.last_kwargs["aspect_ratio"] == "16:9"
    assert _FakeProvider.last_kwargs["resolution"] == "720p"


@pytest.mark.asyncio
async def test_execute_overrides_duration_and_aspect_ratio():
    tool = VideoGenerationTool(config=VideoGenerationToolConfig(enabled=True))

    with patch(
        "nanobot.agent.tools.video_generation.get_video_gen_provider",
        return_value=_FakeProvider,
    ):
        await tool.execute(prompt="x", duration=9, aspect_ratio="9:16")

    assert _FakeProvider.last_kwargs["duration"] == 9
    assert _FakeProvider.last_kwargs["aspect_ratio"] == "9:16"


@pytest.mark.asyncio
async def test_execute_reports_unknown_provider():
    tool = VideoGenerationTool(config=VideoGenerationToolConfig(provider="nope"))

    with patch(
        "nanobot.agent.tools.video_generation.get_video_gen_provider",
        return_value=None,
    ):
        result = await tool.execute(prompt="x")

    assert "nope" in result


@pytest.mark.asyncio
async def test_execute_reports_provider_failure():
    class _Failing(_FakeProvider):
        async def generate(self, **kwargs: Any) -> GeneratedVideoResponse:
            raise VideoGenerationError("quota exhausted")

    tool = VideoGenerationTool(config=VideoGenerationToolConfig(enabled=True))

    with patch(
        "nanobot.agent.tools.video_generation.get_video_gen_provider",
        return_value=_Failing,
    ):
        result = await tool.execute(prompt="x")

    assert "quota exhausted" in result
