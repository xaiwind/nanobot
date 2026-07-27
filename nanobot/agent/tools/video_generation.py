"""Video generation tool (xAI Grok text-to-video)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import Field

from nanobot.agent.tools.base import Tool, ToolResult, tool_parameters
from nanobot.agent.tools.schema import IntegerSchema, StringSchema, tool_parameters_schema
from nanobot.config.paths import get_media_dir
from nanobot.config_base import Base
from nanobot.providers.video_generation import (
    VideoGenerationError,
    get_video_gen_provider,
)

if TYPE_CHECKING:
    from nanobot.agent.tools.context import ToolContext


class VideoGenerationToolConfig(Base):
    """Video generation tool configuration."""

    enabled: bool = False
    provider: str = "xai_grok"
    model: str = "grok-imagine-video"
    default_duration: int = Field(default=5, ge=1, le=15)
    default_aspect_ratio: str = "16:9"
    default_resolution: str = "720p"
    save_dir: str = "generated"


@tool_parameters(
    tool_parameters_schema(
        prompt=StringSchema(
            "Detailed description of the video to generate, including scene, motion, style, and mood.",
            min_length=1,
        ),
        duration=IntegerSchema(
            description="Duration in seconds (1–15). Defaults to the configured default.",
            minimum=1,
            maximum=15,
        ),
        aspect_ratio=StringSchema(
            "Output aspect ratio: 16:9, 1:1, or 9:16.",
        ),
        required=["prompt"],
    )
)
class VideoGenerationTool(Tool):
    name = "generate_video"
    description = "Generate a short video clip from a text prompt using xAI Grok."
    config_key = "video_generation"

    @classmethod
    def config_class(cls) -> type[VideoGenerationToolConfig]:
        return VideoGenerationToolConfig

    def is_enabled(self, ctx: ToolContext) -> bool:
        return ctx.config.video_generation.enabled

    async def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        config = ctx.config.video_generation
        provider_cls = get_video_gen_provider(config.provider)
        if provider_cls is None:
            return ToolResult.error(f"Unknown video generation provider: {config.provider!r}")

        prompt: str = kwargs["prompt"]
        duration: int = kwargs.get("duration") or config.default_duration
        aspect_ratio: str = kwargs.get("aspect_ratio") or config.default_aspect_ratio

        xai_config = ctx.config.providers.xai_grok
        provider = provider_cls(api_key=xai_config.api_key)

        save_dir = str(get_media_dir(ctx.config) / config.save_dir)

        try:
            result = await provider.generate(
                prompt=prompt,
                model=config.model,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=config.default_resolution,
                save_dir=save_dir,
            )
        except VideoGenerationError as exc:
            return ToolResult.error(str(exc))

        logger.info("Video generated: {}", result.local_path)
        return ToolResult.text(
            f"Video saved to `{result.local_path}` ({result.duration}s, model: {result.model})"
        )
