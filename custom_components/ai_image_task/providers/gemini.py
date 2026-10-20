"""Google Gemini API image generation provider."""

from __future__ import annotations

import asyncio
import base64
import binascii

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


class GeminiImageProvider(ImageProvider):
    """Generate images through Google's Gemini Interactions API."""

    slug = "google_gemini"
    title = "Google Gemini API / AI Studio (API key required; pricing varies)"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"
    requires_api_key = True
    is_free = False
    models = (
        "gemini-3.1-flash-lite-image",
        "gemini-nano-banana-2.1",
        "gemini-3.1-flash-image",
        "gemini-3-pro-image",
        "gemini-2.5-flash-image",
    )

    async def async_generate(self, request: ImageRequest) -> ImageResult:
        if not self._api_key:
            raise ProviderAuthError("Google Gemini requires a Gemini API key")
        model = request.model or self.models[0]
        url = f"{self._base_url}/interactions"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }
        payload = {
            "model": model,
            "input": [{"type": "text", "text": request.full_prompt}],
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
                        f"Google Gemini rejected the API key ({response.status})"
                    )
                if response.status in (429, 503):
                    retry_after = response.headers.get("Retry-After")
                    raise ProviderRateLimit(
                        f"Google Gemini rate limited the request ({response.status})",
                        retry_after=int(retry_after)
                        if retry_after and retry_after.isdigit()
                        else None,
                    )
                if response.status >= 400:
                    body = (await response.text())[:500]
                    raise ProviderError(
                        f"Google Gemini HTTP {response.status}: {body}"
                    )
                data = await response.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise ProviderError(
                f"Google Gemini timed out after {request.timeout}s"
            ) from err
        except aiohttp.ClientError as err:
            raise ProviderError(f"Google Gemini network error: {err}") from err

        image = self._find_image(data)
        if image is None:
            raise ProviderError(
                f"Google Gemini response contained no image: {str(data)[:400]}"
            )

        encoded, content_type = image
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, TypeError, ValueError) as err:
            raise ProviderError(
                f"Invalid Google Gemini image payload: {err}"
            ) from err
        if len(content) < MIN_IMAGE_BYTES:
            raise ProviderError(
                f"Google Gemini returned a suspiciously small image ({len(content)} bytes)"
            )

        return ImageResult(
            content=content,
            content_type=content_type or "image/png",
            url=url,
            model=model,
            revised_prompt=request.full_prompt,
        )

    @staticmethod
    def _find_image(data: dict) -> tuple[str, str | None] | None:
        """Extract image data from the Interactions API response."""
        candidates = []
        output_image = data.get("output_image")
        if isinstance(output_image, dict):
            candidates.append(output_image)
        output = data.get("output")
        if isinstance(output, list):
            candidates.extend(item for item in output if isinstance(item, dict))

        for item in candidates:
            if item.get("type") not in (None, "image"):
                continue
            encoded = item.get("data")
            if encoded:
                return encoded, item.get("mime_type") or item.get("mimeType")
        return None
