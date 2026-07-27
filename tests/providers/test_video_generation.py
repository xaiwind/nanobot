from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nanobot.providers.video_generation import (
    GeneratedVideoResponse,
    VideoGenerationError,
    XAIGrokVideoGenerationClient,
    get_video_gen_provider,
)


class FakeVideoResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)
        self.request = httpx.Request("POST", "https://api.x.ai/v1/videos/generations")

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


class FakeVideoClient:
    def __init__(
        self,
        post_response: FakeVideoResponse,
        get_responses: list[FakeVideoResponse],
    ) -> None:
        self._post = post_response
        self._gets = iter(get_responses)
        self.post_calls: list[dict[str, Any]] = []
        self.get_calls: list[str] = []

    async def post(self, url: str, **kwargs: Any) -> FakeVideoResponse:
        self.post_calls.append({"url": url, **kwargs})
        return self._post

    async def get(self, url: str, **kwargs: Any) -> FakeVideoResponse:
        self.get_calls.append(url)
        return next(self._gets)


def test_xai_grok_registered():
    assert get_video_gen_provider("xai_grok") is XAIGrokVideoGenerationClient


@pytest.mark.asyncio
async def test_generate_submits_then_polls(tmp_path):
    fake_token = MagicMock(access="tok-xyz", account_id="acct-1")
    post_resp = FakeVideoResponse({"id": "req-123"})
    poll_pending = FakeVideoResponse({"id": "req-123", "status": "pending"})
    poll_done = FakeVideoResponse({
        "id": "req-123",
        "status": "done",
        "video": {"url": "https://cdn.x.ai/v.mp4"},
    })
    fake_client = FakeVideoClient(post_resp, [poll_pending, poll_done])

    async def fake_download(url: str, headers: dict) -> bytes:
        return b"FAKEMP4"

    with (
        patch("nanobot.providers.video_generation.get_xai_oauth_token", return_value=fake_token),
        patch("nanobot.providers.video_generation._download_bytes", new=fake_download),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = await XAIGrokVideoGenerationClient().generate(
            prompt="a sunset",
            model="grok-imagine-video",
            duration=5,
            aspect_ratio="16:9",
            resolution="720p",
            save_dir=str(tmp_path),
            client=fake_client,
        )

    assert result.model == "grok-imagine-video"
    assert result.duration == 5
    assert result.local_path.endswith(".mp4")

    post_body = fake_client.post_calls[0]["json"]
    assert post_body["model"] == "grok-imagine-video"
    assert post_body["prompt"] == "a sunset"
    assert post_body["duration"] == 5
    assert "Bearer tok-xyz" in fake_client.post_calls[0]["headers"]["Authorization"]
    assert len(fake_client.get_calls) == 2  # one pending, one done


@pytest.mark.asyncio
async def test_generate_falls_back_to_api_key(tmp_path):
    post_resp = FakeVideoResponse({"id": "req-999"})
    poll_done = FakeVideoResponse({
        "id": "req-999", "status": "done",
        "video": {"url": "https://cdn.x.ai/v.mp4"},
    })
    fake_client = FakeVideoClient(post_resp, [poll_done])

    async def fake_download(url, headers):
        return b"FAKEMP4"

    with (
        patch("nanobot.providers.video_generation.get_xai_oauth_token", side_effect=Exception("no token")),
        patch("nanobot.providers.video_generation._download_bytes", new=fake_download),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = await XAIGrokVideoGenerationClient(api_key="sk-fallback").generate(
            prompt="a sunset", model="grok-imagine-video",
            duration=5, aspect_ratio="16:9", resolution="720p",
            save_dir=str(tmp_path), client=fake_client,
        )

    assert result.local_path
    auth = fake_client.post_calls[0]["headers"]["Authorization"]
    assert auth == "Bearer sk-fallback"


@pytest.mark.asyncio
async def test_generate_raises_on_timeout(tmp_path):
    fake_token = MagicMock(access="tok-xyz", account_id="acct-1")
    post_resp = FakeVideoResponse({"id": "req-to"})
    always_pending = FakeVideoResponse({"id": "req-to", "status": "pending"})

    call_count = 0

    class InfiniteClient:
        post_calls: list = []
        get_calls: list = []

        async def post(self, url, **kw):
            self.post_calls.append(kw)
            return post_resp

        async def get(self, url, **kw):
            nonlocal call_count
            call_count += 1
            return always_pending

    with (
        patch("nanobot.providers.video_generation.get_xai_oauth_token", return_value=fake_token),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(VideoGenerationError, match="timed out"):
            await XAIGrokVideoGenerationClient(
                poll_timeout=6, poll_interval=3,
            ).generate(
                prompt="x", model="grok-imagine-video",
                duration=5, aspect_ratio="16:9", resolution="720p",
                save_dir=str(tmp_path), client=InfiniteClient(),
            )


@pytest.mark.asyncio
async def test_generate_raises_when_no_auth(tmp_path):
    with patch("nanobot.providers.video_generation.get_xai_oauth_token", side_effect=Exception("no")):
        with pytest.raises(VideoGenerationError, match="xAI Grok"):
            await XAIGrokVideoGenerationClient(api_key=None).generate(
                prompt="x", model="grok-imagine-video",
                duration=5, aspect_ratio="16:9", resolution="720p",
                save_dir=str(tmp_path),
            )
