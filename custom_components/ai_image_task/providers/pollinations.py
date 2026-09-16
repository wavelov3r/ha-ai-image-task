"""Pollinations.ai provider.

Docs: https://github.com/pollinations/pollinations/blob/main/APIDOCS.md

Two URL shapes are supported:

* ``https://gen.pollinations.ai``      -> ``GET /image/{prompt}``   (current API)
* ``https://image.pollinations.ai``    -> ``GET /prompt/{prompt}``  (legacy API)

An API key is optional.  Anonymous usage is rate limited (roughly one request
every 15 seconds), which is why the integration staggers the two slots.
"""

from __future__ import annotations

import asyncio
import json
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

#: Several upstream backends (zimage in particular) reject requests whose
#: shortest side is below this value with an HTTP 422.
MIN_SIDE = 512
#: Most diffusion backends want dimensions that are a multiple of 8.
DIM_STEP = 8
MAX_SIDE = 2048

#: Models that actually understand `quality` and `transparent`.
GPTIMAGE_MODELS = frozenset({"gptimage", "gptimage-large", "gpt-image-2"})
#: Models that accept a reference image.
IMG2IMG_MODELS = frozenset(
    {
        "kontext",
        "gptimage",
        "gptimage-large",
        "gpt-image-2",
        "seedream",
        "seedream5",
        "seedream-pro",
        "klein",
        "nanobanana",
        "nanobanana-2",
        "nanobanana-pro",
        "p-image-edit",
    }
)


def normalise_dimensions(width: int, height: int) -> tuple[int, int]:
    """Return API-safe dimensions preserving the requested aspect ratio.

    Sides shorter than :data:`MIN_SIDE` are scaled up (keeping the ratio) and
    every side is rounded to a multiple of :data:`DIM_STEP`, because backends
    such as ``zimage`` answer ``422 greater_than_equal`` otherwise.  The
    integration then resizes the result back to the exact size you asked for
    (see the "Resize to the exact size" slot option).
    """
    width = max(int(width), 1)
    height = max(int(height), 1)

    shortest = min(width, height)
    if shortest < MIN_SIDE:
        scale = MIN_SIDE / shortest
        width = int(round(width * scale))
        height = int(round(height * scale))

    longest = max(width, height)
    if longest > MAX_SIDE:
        scale = MAX_SIDE / longest
        width = int(round(width * scale))
        height = int(round(height * scale))

    def _round(value: int) -> int:
        value = int(round(value / DIM_STEP)) * DIM_STEP
        return max(min(value, MAX_SIDE), MIN_SIDE)

    return _round(width), _round(height)


def _extract_error(body: str) -> str:
    """Turn a Pollinations error envelope into something readable."""
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return body[:400]

    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return body[:400]

    message = str(error.get("message") or "")
    details = error.get("details") or {}
    upstream = details.get("upstreamBody")
    if upstream:
        message = f"{message} | upstream: {str(upstream)[:400]}"
        if "greater_than_equal" in str(upstream):
            message += (
                " -- the backend refused the image size; "
                f"use at least {MIN_SIDE}px on the shortest side"
            )
    return message[:600]


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
        "quality": "low | medium | high | hd. Only sent to gptimage-family models.",
        "transparent": "Transparent background. Only sent to gptimage-family models.",
        "safe": "Enable the provider content filter (may reject some prompts).",
        "nologo": "Legacy endpoint only: remove the Pollinations watermark.",
        "private": "Legacy endpoint only: keep the generation out of the public feed.",
        "enhance": "Legacy endpoint only: let the provider rewrite the prompt.",
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

    def _build_params(
        self, request: ImageRequest, seed: int, width: int, height: int
    ) -> dict[str, str]:
        opts = request.options or {}
        model = (request.model or "").strip()

        params: dict[str, str] = {
            "width": str(width),
            "height": str(height),
            "seed": str(seed),
        }
        if model:
            params["model"] = model

        if opts.get("safe"):
            params["safe"] = "true"

        if self._is_legacy:
            # These three only exist on the legacy endpoint.  Sending them to
            # gen.pollinations.ai is at best ignored, at worst rejected.
            if opts.get("nologo", True):
                params["nologo"] = "true"
            if opts.get("private", True):
                params["private"] = "true"
            if opts.get("enhance"):
                params["enhance"] = "true"
        elif model in GPTIMAGE_MODELS:
            quality = opts.get("quality")
            if quality:
                params["quality"] = str(quality)
            if opts.get("transparent"):
                params["transparent"] = "true"

        reference = str(opts.get("reference_image") or "").strip()
        if reference and (self._is_legacy or model in IMG2IMG_MODELS):
            # The docs recommend keeping `image=` last in the query string.
            params["image"] = reference
        elif reference:
            _LOGGER.debug(
                "Model '%s' does not accept a reference image; ignoring it", model
            )
        return params

    async def async_generate(self, request: ImageRequest) -> ImageResult:
        seed = request.seed
        if seed is None or seed < 0:
            seed = random.randint(0, 2_147_483_647)

        prompt = request.full_prompt
        if not prompt:
            raise ProviderError("Empty prompt")

        width, height = normalise_dimensions(request.width, request.height)
        if (width, height) != (int(request.width), int(request.height)):
            _LOGGER.debug(
                "Requesting %sx%s instead of %sx%s (backend limits)",
                width,
                height,
                request.width,
                request.height,
            )

        url = self._build_url(prompt)
        params = self._build_params(request, seed, width, height)
        headers = {"Accept": "image/*"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        timeout = aiohttp.ClientTimeout(total=request.timeout)
        try:
            async with self._session.get(
                url, params=params, headers=headers, timeout=timeout
            ) as resp:
                if resp.status == 401:
                    raise ProviderAuthError(
                        "Pollinations rejected the request (401). "
                        "Remove the API key or check it at enter.pollinations.ai"
                    )
                if resp.status == 402:
                    raise ProviderAuthError("Pollinations account budget exhausted (402)")
                if resp.status in (429, 503):
                    retry_after = resp.headers.get("Retry-After")
                    raise ProviderRateLimit(
                        f"Pollinations rate limited the request ({resp.status})",
                        retry_after=int(retry_after)
                        if retry_after and retry_after.isdigit()
                        else None,
                    )
                if resp.status >= 400:
                    body = await resp.text()
                    raise ProviderError(
                        f"HTTP {resp.status} from Pollinations "
                        f"(model={params.get('model')}, {width}x{height}): "
                        f"{_extract_error(body)}"
                    )

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
            snippet = data[:300].decode("utf-8", errors="replace")
            raise ProviderError(
                f"Provider returned '{content_type or 'unknown'}' instead of an image: {snippet}"
            )
        if len(data) < MIN_IMAGE_BYTES:
            raise ProviderError(
                f"Provider returned a suspiciously small image ({len(data)} bytes)"
            )

        return ImageResult(
            content=data,
            content_type=content_type,
            url=final_url,
            model=request.model,
            seed=seed,
            revised_prompt=prompt,
            width=width,
            height=height,
        )

    async def async_validate(self) -> None:
        """Check connectivity.

        The model catalogue is a public endpoint, so a 401/403 only means
        something is wrong when an API key was actually supplied.  Everything
        else short of a server error is ignored on purpose: setup should not
        fail because the free service is momentarily grumpy.
        """
        url = (
            f"{self._base_url}/models"
            if self._is_legacy
            else f"{self._base_url}/image/models"
        )
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with self._session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status in (401, 403) and self._api_key:
                    raise ProviderAuthError("Invalid API key")
                if resp.status >= 500:
                    raise ProviderError(f"Provider unavailable (HTTP {resp.status})")
        except aiohttp.ClientError as err:
            raise ProviderError(f"Cannot reach {url}: {err}") from err
        except asyncio.TimeoutError as err:
            raise ProviderError(f"Timeout contacting {url}") from err
