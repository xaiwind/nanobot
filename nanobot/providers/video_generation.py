"""xAI Grok video generation provider."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

# Import at module level for test patching (lazy import inside methods avoids circular imports at runtime)
from nanobot.providers.xai_oauth import get_xai_oauth_token  # noqa: F401

_VIDEO_GEN_PROVIDERS: dict[str, type[VideoGenerationProvider]] = {}


def register_video_gen_provider(cls: type[VideoGenerationProvider]) -> None:
    _VIDEO_GEN_PROVIDERS[cls.provider_name] = cls


def get_video_gen_provider(name: str) -> type[VideoGenerationProvider] | None:
    return _VIDEO_GEN_PROVIDERS.get(name)


class VideoGenerationError(RuntimeError):
    pass


@dataclass
class GeneratedVideoResponse:
    local_path: str
    duration: float
    model: str


class VideoGenerationProvider(ABC):
    provider_name: str = ""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        poll_timeout: int = 300,
        poll_interval: int = 3,
    ) -> None:
        self.api_key = api_key
        self.api_base = (api_base or self._default_base_url()).rstrip("/")
        self.poll_timeout = poll_timeout
        self.poll_interval = poll_interval

    def _default_base_url(self) -> str:
        return ""

    @abstractmethod
    async def generate(
        self,
        *,
        prompt: str,
        model: str,
        duration: int,
        aspect_ratio: str,
        resolution: str,
        save_dir: str,
        client: Any | None = None,
    ) -> GeneratedVideoResponse: ...


async def _download_bytes(url: str, headers: dict[str, str]) -> bytes:
    async with httpx.AsyncClient(timeout=120) as c:
        resp = await c.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content


class XAIGrokVideoGenerationClient(VideoGenerationProvider):
    """xAI Grok text-to-video via OAuth or API key.

    Submits to api.x.ai/v1/videos/generations, polls until done, downloads.
    """

    provider_name = "xai_grok"

    def _default_base_url(self) -> str:
        return "https://api.x.ai/v1"

    async def _get_bearer(self) -> str:
        try:
            token = await asyncio.to_thread(get_xai_oauth_token)
            if token and token.access:
                return token.access
        except Exception:
            pass
        if self.api_key:
            return self.api_key
        raise VideoGenerationError("xAI Grok: re-login or set an API Key in Grok settings")

    async def generate(
        self,
        *,
        prompt: str,
        model: str,
        duration: int,
        aspect_ratio: str,
        resolution: str,
        save_dir: str,
        client: Any | None = None,
    ) -> GeneratedVideoResponse:
        bearer = await self._get_bearer()
        headers = {
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }

        logger.info(
            "xAI Grok video generation: POST {}/videos/generations model={} duration={}s",
            self.api_base, model, duration,
        )

        _client = client or httpx.AsyncClient(timeout=60)
        try:
            post_resp = await _client.post(
                f"{self.api_base}/videos/generations",
                json=body,
                headers=headers,
            )
        finally:
            if client is None and hasattr(_client, "aclose"):
                await _client.aclose()

        try:
            post_resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VideoGenerationError(
                f"xAI Grok video submit failed (HTTP {post_resp.status_code}): {post_resp.text[:500]}"
            ) from exc

        request_id = post_resp.json()["id"]
        logger.info("xAI Grok video generation submitted: request_id={}", request_id)

        # Poll
        poll_url = f"{self.api_base}/videos/{request_id}"
        deadline = time.monotonic() + self.poll_timeout
        _poll_client = client or httpx.AsyncClient(timeout=30)
        try:
            while True:
                if time.monotonic() > deadline:
                    raise VideoGenerationError(
                        f"xAI Grok video generation timed out after {self.poll_timeout}s"
                    )
                await asyncio.sleep(self.poll_interval)
                poll_resp = await _poll_client.get(poll_url, headers=headers)
                poll_resp.raise_for_status()
                data = poll_resp.json()
                status = data.get("status")
                logger.debug("xAI Grok video poll: request_id={} status={}", request_id, status)
                if status == "done":
                    video_url = data["video"]["url"]
                    break
                if status not in {"pending", "processing"}:
                    raise VideoGenerationError(
                        f"xAI Grok video generation failed with status: {status}"
                    )
        finally:
            if client is None and hasattr(_poll_client, "aclose"):
                await _poll_client.aclose()

        logger.info("xAI Grok video ready, downloading from {}", video_url)
        video_bytes = await _download_bytes(video_url, headers={"Authorization": f"Bearer {bearer}"})

        save_path = Path(save_dir).expanduser()
        save_path.mkdir(parents=True, exist_ok=True)
        out_file = save_path / f"{request_id}.mp4"
        out_file.write_bytes(video_bytes)

        return GeneratedVideoResponse(
            local_path=str(out_file),
            duration=float(duration),
            model=model,
        )


register_video_gen_provider(XAIGrokVideoGenerationClient)
