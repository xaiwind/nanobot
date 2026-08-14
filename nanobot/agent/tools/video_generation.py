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
    from nanobot.config.schema import ProviderConfig


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
    """Generate short video clips through the configured video provider."""

    config_key = "video_generation"

    @classmethod
    def config_cls(cls) -> type[VideoGenerationToolConfig]:
        return VideoGenerationToolConfig

    @classmethod
    def enabled(cls, ctx: ToolContext) -> bool:
        return ctx.config.video_generation.enabled

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        # xAI video and image generation both read providers.xai_grok, so the
        # image provider configs already carry the credential this tool needs.
        return cls(
            config=ctx.config.video_generation,
            provider_configs=ctx.image_generation_provider_configs,
        )

    def __init__(
        self,
        *,
        config: VideoGenerationToolConfig,
        provider_configs: dict[str, ProviderConfig] | None = None,
    ) -> None:
        self.config = config
        self.provider_configs = dict(provider_configs or {})

    @property
    def name(self) -> str:
        return "generate_video"

    @property
    def description(self) -> str:
        return "Generate a short video clip from a text prompt using xAI Grok."

    async def execute(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        prompt: str,
        duration: int | None = None,
        aspect_ratio: str | None = None,
        **kwargs: Any,
    ) -> str:
        provider_cls = get_video_gen_provider(self.config.provider)
        if provider_cls is None:
            return ToolResult.error(
                f"Unknown video generation provider: {self.config.provider!r}"
            )

        provider_config = self.provider_configs.get(self.config.provider)
        provider = provider_cls(
            api_key=provider_config.api_key if provider_config else None,
            api_base=provider_config.api_base if provider_config else None,
        )
        save_dir = str(get_media_dir() / self.config.save_dir)

        try:
            result = await provider.generate(
                prompt=prompt,
                model=self.config.model,
                duration=duration or self.config.default_duration,
                aspect_ratio=aspect_ratio or self.config.default_aspect_ratio,
                resolution=self.config.default_resolution,
                save_dir=save_dir,
            )
        except (VideoGenerationError, OSError) as exc:
            return ToolResult.error(f"Error: {exc}")

        logger.info("Video generated: {}", result.local_path)
        return (
            f"Video saved to `{result.local_path}` "
            f"({result.duration}s, model: {result.model})"
        )
