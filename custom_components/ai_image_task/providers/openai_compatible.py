"""Generic OpenAI-compatible image provider.

Works with any endpoint exposing ``POST {base_url}/v1/images/generations`` with
the OpenAI schema, including:

* ``https://gen.pollinations.ai``      (Pollinations, key optional/free tier)
* self-hosted gateways (LiteLLM, one-api, ...)
* OpenAI itself (paid)

This provider exists mostly to show how easy it is to plug another backend in.
"""

from __future__ import annotations

import asyncio
import base64
import logging

import aiohttp

from ..const import MIN_IMAGE_BYTES
from .pollinations import normalise_dimensions
from .base import (
    ImageProvider,
    ImageRequest,
    ImageResult,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimit,
)

_LOGGER = logging.getLogger(__name__)


class OpenAICompatibleProvider(ImageProvider):
    """Text-to-image through an OpenAI-compatible /v1/images/generations API."""

    slug = "openai_compatible"
    title = "OpenAI-compatible endpoint"
    default_base_url = "https://gen.pollinations.ai"
    requires_api_key = False
    models = ("flux", "zimage", "gptimage", "gpt-image-1", "dall-e-3")
    extra_options = {
        "quality": "standard | hd | low | medium | high (backend dependent).",
        "safe": "Forwarded as the `safe` flag when the backend supports it.",
    }

    async def async_generate(self, request: ImageRequest) -> ImageResult:
        url = f"{self._base_url}/v1/images/generations"
        width, height = normalise_dimensions(request.width, request.height)
        payload: dict = {
            "prompt": request.full_prompt,
            "n": 1,
            "size": f"{width}x{height}",
            "response_format": "b64_json",
        }
        if request.model:
            payload["model"] = request.model
        opts = request.options or {}
        if opts.get("quality"):
            payload["quality"] = opts["quality"]
        if opts.get("safe"):
            payload["safe"] = True

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        timeout = aiohttp.ClientTimeout(total=request.timeout)
        try:
            async with self._session.post(
                url, json=payload, headers=headers, timeout=timeout
            ) as resp:
                if resp.status in (401, 403):
                    raise ProviderAuthError(
                        f"Endpoint rejected the request ({resp.status}). "
                        "Check the API key, or remove it if the endpoint is free."
                    )
                if resp.status in (429, 503):
                    retry_after = resp.headers.get("Retry-After")
                    raise ProviderRateLimit(
                        f"Rate limited ({resp.status})",
                        retry_after=int(retry_after) if retry_after and retry_after.isdigit() else None,
                    )
                if resp.status >= 400:
                    body = (await resp.text())[:300]
                    raise ProviderError(f"HTTP {resp.status}: {body}")
                data = await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise ProviderError(f"Timeout after {request.timeout}s") from err
        except aiohttp.ClientError as err:
            raise ProviderError(f"Network error: {err}") from err

        items = (data or {}).get("data") or []
        if not items:
            raise ProviderError(f"Empty response: {str(data)[:200]}")
        item = items[0]

        content: bytes | None = None
        image_url = item.get("url")
        if item.get("b64_json"):
            try:
                content = base64.b64decode(item["b64_json"])
            except (ValueError, TypeError) as err:
                raise ProviderError(f"Invalid base64 payload: {err}") from err
        elif image_url:
            try:
                async with self._session.get(image_url, timeout=timeout) as resp:
                    if resp.status >= 400:
                        raise ProviderError(f"Cannot download image: HTTP {resp.status}")
                    content = await resp.read()
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise ProviderError(f"Cannot download image: {err}") from err

        if not content or len(content) < MIN_IMAGE_BYTES:
            raise ProviderError("Provider returned no usable image data")

        content_type = "image/png" if content[:8].startswith(b"\x89PNG") else "image/jpeg"
        return ImageResult(
            content=content,
            content_type=content_type,
            url=image_url,
            model=request.model,
            seed=request.seed if request.seed >= 0 else None,
            revised_prompt=item.get("revised_prompt") or request.full_prompt,
            width=width,
            height=height,
        )
