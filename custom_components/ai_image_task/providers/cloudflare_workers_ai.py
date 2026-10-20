"""Cloudflare Workers AI provider using its free daily allocation."""

from __future__ import annotations

import asyncio
import base64
import binascii
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


class CloudflareWorkersAIProvider(ImageProvider):
    """Generate images through Cloudflare's hosted FLUX.1 [schnell] model."""

    slug = "cloudflare_workers_ai"
    title = (
        "Cloudflare Workers AI (free daily quota; API token + account ID required)"
    )
    default_base_url = "https://api.cloudflare.com/client/v4"
    requires_api_key = True
    requires_account_id = True
    is_free = True
    models = ("@cf/black-forest-labs/flux-1-schnell",)

    async def async_generate(self, request: ImageRequest) -> ImageResult:
        if not self._api_key or not self._account_id:
            raise ProviderAuthError("Cloudflare requires an API token and account ID")
        if len(request.full_prompt) > 2048:
            raise ProviderError("Cloudflare prompt exceeds the 2048-character limit")

        model = self.models[0]
        url = (
            f"{self._base_url}/accounts/{quote(self._account_id, safe='')}"
            f"/ai/run/{model}"
        )
        headers = {"Content-Type": "application/json"}
        if self.authorization_header:
            headers["Authorization"] = self.authorization_header

        try:
            async with self._session.post(
                url,
                json={"prompt": request.full_prompt},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=request.timeout),
            ) as response:
                if response.status in (401, 403):
                    raise ProviderAuthError(
                        f"Cloudflare rejected the token or account ({response.status})"
                    )
                if response.status in (429, 503):
                    retry_after = response.headers.get("Retry-After")
                    raise ProviderRateLimit(
                        f"Cloudflare rate limited the request ({response.status})",
                        retry_after=int(retry_after)
                        if retry_after and retry_after.isdigit()
                        else None,
                    )
                if response.status >= 400:
                    body = (await response.text())[:400]
                    raise ProviderError(f"Cloudflare HTTP {response.status}: {body}")
                data = await response.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise ProviderError(f"Timeout after {request.timeout}s") from err
        except aiohttp.ClientError as err:
            raise ProviderError(f"Cloudflare network error: {err}") from err

        result_data = (data or {}).get("result")
        image_data = (
            result_data.get("image") if isinstance(result_data, dict) else None
        )
        if not image_data:
            errors = (data or {}).get("errors") or []
            message = "; ".join(
                str(error.get("message", error) if isinstance(error, dict) else error)
                for error in errors
            )
            raise ProviderError(
                f"Cloudflare returned no image{': ' + message if message else ''}"
            )
        try:
            content = base64.b64decode(image_data, validate=True)
        except (binascii.Error, TypeError, ValueError) as err:
            raise ProviderError(f"Invalid Cloudflare image payload: {err}") from err
        if len(content) < MIN_IMAGE_BYTES:
            raise ProviderError(
                f"Cloudflare returned a suspiciously small image ({len(content)} bytes)"
            )

        return ImageResult(
            content=content,
            content_type="image/jpeg",
            url=url,
            model=model,
            revised_prompt=request.full_prompt,
        )
