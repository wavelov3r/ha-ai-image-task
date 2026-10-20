"""Hugging Face Inference Providers text-to-image provider."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

import aiohttp

from ..const import MIN_IMAGE_BYTES
from .base import (
    ImageProvider,
    ImageRequest,
    ImageResult,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimit,
)


class HuggingFaceImageProvider(ImageProvider):
    """Generate images through the Hugging Face Inference Providers router."""

    slug = "huggingface"
    title = "Hugging Face Inference Providers (token required; paid usage)"
    default_base_url = "https://router.huggingface.co/hf-inference"
    requires_api_key = True
    is_free = False
    models = ("stabilityai/stable-diffusion-3-medium-diffusers",)

    async def async_generate(self, request: ImageRequest) -> ImageResult:
        if not self._api_key:
            raise ProviderAuthError("Hugging Face requires an Inference Providers token")
        model = request.model or self.models[0]
        url = f"{self._base_url}/models/{quote(model, safe='/')}"
        payload: dict[str, Any] = {
            "inputs": request.prompt,
            "parameters": {
                "width": request.width,
                "height": request.height,
            },
        }
        if request.negative_prompt:
            payload["parameters"]["negative_prompt"] = request.negative_prompt
        if request.seed >= 0:
            payload["parameters"]["seed"] = request.seed
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "image/*",
        }
        try:
            async with self._session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=request.timeout),
            ) as response:
                if response.status in (401, 403):
                    raise ProviderAuthError(
                        f"Hugging Face rejected the token ({response.status})"
                    )
                if response.status == 402:
                    raise ProviderAuthError(
                        "Hugging Face inference credits are unavailable or exhausted"
                    )
                if response.status in (429, 503):
                    retry_after = response.headers.get("Retry-After")
                    raise ProviderRateLimit(
                        f"Hugging Face rate limited the request ({response.status})",
                        retry_after=int(retry_after)
                        if retry_after and retry_after.isdigit()
                        else None,
                    )
                if response.status >= 400:
                    body = (await response.text())[:500]
                    raise ProviderError(f"Hugging Face HTTP {response.status}: {body}")
                content_type = (response.headers.get("Content-Type") or "").split(
                    ";", maxsplit=1
                )[0]
                if not content_type.startswith("image/"):
                    body = (await response.text())[:400]
                    try:
                        message = json.loads(body)
                    except (json.JSONDecodeError, TypeError):
                        message = body
                    raise ProviderError(
                        f"Hugging Face returned no image: {message}"
                    )
                content = await response.read()
        except asyncio.TimeoutError as err:
            raise ProviderError(
                f"Hugging Face timed out after {request.timeout}s"
            ) from err
        except aiohttp.ClientError as err:
            raise ProviderError(f"Hugging Face network error: {err}") from err

        if len(content) < MIN_IMAGE_BYTES:
            raise ProviderError(
                f"Hugging Face returned a suspiciously small image ({len(content)} bytes)"
            )

        return ImageResult(
            content=content,
            content_type=content_type,
            url=url,
            model=model,
            seed=request.seed if request.seed >= 0 else None,
            revised_prompt=request.full_prompt,
            width=request.width,
            height=request.height,
        )
