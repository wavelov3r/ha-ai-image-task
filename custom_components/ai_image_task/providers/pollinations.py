"""Pollinations.ai provider.

Docs: https://github.com/pollinations/pollinations/blob/main/APIDOCS.md

Two URL shapes are supported:

* ``https://gen.pollinations.ai``      -> ``GET /image/{prompt}``   (current API)
* ``https://image.pollinations.ai``    -> ``GET /prompt/{prompt}``  (legacy API,
  still widely used and usable without any account)

An API key is optional.  Anonymous usage is rate limited (roughly one request
every 15 seconds), which is why the integration staggers the two slots.
"""

from __future__ import annotations

import asyncio
import logging
import random
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

_LOGGER = logging.getLogger(__name__)

GEN_BASE = "https://gen.pollinations.ai"
LEGACY_BASE = "https://image.pollinations.ai"


class PollinationsProvider(ImageProvider):
    """Free text-to-image generation through pollinations.ai."""

    slug = "pollinations"
    title = "Pollinations.ai (free)"
    default_base_url = GEN_BASE
    requires_api_key = False
    models = (
        "zimage",
        "flux",
        "turbo",
        "kontext",
        "klein",
        "nanobanana",
        "seedream",
        "qwen-image",
        "wan-image",
        "gptimage",
        "p-image",
    )
    extra_options = {
        "quality": "low | medium | high | hd. Only honoured by gptimage-family models.",
        "transparent": "Transparent background. Only honoured by gptimage-family models.",
        "safe": "Enable the provider content filter (may reject some prompts).",
        "nologo": "Legacy endpoint only: remove the Pollinations watermark.",
        "private": "Keep the generation out of the public feed.",
        "enhance": "Let the provider rewrite/expand the prompt with an LLM.",
        "reference_image": "URL of a reference image (img2img / editing models).",
    }

    @property
    def _is_legacy(self) -> bool:
        return "image.pollinations.ai" in self._base_url

    def _build_url(self, prompt: str) -> str:
        encoded = quote(prompt, safe="")
        if self._is_legacy:
            return f"{self._base_url}/prompt/{encoded}"
        return f"{self._base_url}/image/{encoded}"

    def _build_params(self, request: ImageRequest, seed: int) -> dict[str, str]:
        opts = request.options or {}
        params: dict[str, str] = {
            "width": str(int(request.width)),
            "height": str(int(request.height)),
            "seed": str(seed),
        }
        if request.model:
            params["model"] = request.model

        if opts.get("safe"):
            params["safe"] = "true"
        if opts.get("private", True):
            params["private"] = "true"
        if opts.get("enhance"):
            params["enhance"] = "true"
        if opts.get("nologo", True):
            params["nologo"] = "true"

        if not self._is_legacy:
            quality = opts.get("quality")
            if quality:
                params["quality"] = str(quality)
            if opts.get("transparent"):
                params["transparent"] = "true"

        reference = (opts.get("reference_image") or "").strip()
        if reference:
            # The docs recommend keeping `image=` last in the query string.
            params["image"] = reference
        return params

    async def async_generate(self, request: ImageRequest) -> ImageResult:
        seed = request.seed
        if seed is None or seed < 0:
            seed = random.randint(0, 2_147_483_647)

        prompt = request.full_prompt
        if not prompt:
            raise ProviderError("Empty prompt")

        url = self._build_url(prompt)
        params = self._build_params(request, seed)
        headers = {"Accept": "image/*"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        timeout = aiohttp.ClientTimeout(total=request.timeout)
        try:
            async with self._session.get(
                url, params=params, headers=headers, timeout=timeout
            ) as resp:
                if resp.status == 401:
                    raise ProviderAuthError("Pollinations rejected the API key (401)")
                if resp.status == 402:
                    raise ProviderAuthError(
                        "Pollinations account budget exhausted (402)"
                    )
                if resp.status in (429, 503):
                    retry_after = resp.headers.get("Retry-After")
                    raise ProviderRateLimit(
                        f"Pollinations rate limited the request ({resp.status})",
                        retry_after=int(retry_after) if retry_after and retry_after.isdigit() else None,
                    )
                if resp.status >= 400:
                    body = (await resp.text())[:300]
                    raise ProviderError(f"HTTP {resp.status} from Pollinations: {body}")

                content_type = (resp.headers.get("Content-Type") or "").lower()
                data = await resp.read()
                final_url = str(resp.url)
        except asyncio.TimeoutError as err:
            raise ProviderError(
                f"Timeout after {request.timeout}s while generating the image"
            ) from err
        except aiohttp.ClientError as err:
            raise ProviderError(f"Network error: {err}") from err

        if not content_type.startswith("image/"):
            snippet = data[:200].decode("utf-8", errors="replace")
            raise ProviderError(
                f"Provider returned '{content_type or 'unknown'}' instead of an image: {snippet}"
            )
        if len(data) < MIN_IMAGE_BYTES:
            raise ProviderError(f"Provider returned a suspiciously small image ({len(data)} bytes)")

        return ImageResult(
            content=data,
            content_type=content_type,
            url=final_url,
            model=request.model,
            seed=seed,
            revised_prompt=prompt,
        )

    async def async_validate(self) -> None:
        """Check that the model catalogue endpoint answers."""
        url = f"{self._base_url}/image/models" if not self._is_legacy else f"{self._base_url}/models"
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with self._session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status == 401:
                    raise ProviderAuthError("Invalid API key")
                if resp.status >= 500:
                    raise ProviderError(f"Provider unavailable (HTTP {resp.status})")
        except aiohttp.ClientError as err:
            raise ProviderError(f"Cannot reach {url}: {err}") from err
        except asyncio.TimeoutError as err:
            raise ProviderError(f"Timeout contacting {url}") from err
