"""Provider registry for AI Image Task."""

from __future__ import annotations

from aiohttp import ClientSession

from .base import (  # noqa: F401
    ImageProvider,
    ImageRequest,
    ImageResult,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimit,
)
from .openai_compatible import OpenAICompatibleProvider
from .pollinations import PollinationsProvider

PROVIDERS: dict[str, type[ImageProvider]] = {
    PollinationsProvider.slug: PollinationsProvider,
    OpenAICompatibleProvider.slug: OpenAICompatibleProvider,
}


def get_provider_class(slug: str) -> type[ImageProvider]:
    """Return the provider class for ``slug``."""
    try:
        return PROVIDERS[slug]
    except KeyError as err:
        raise ProviderError(f"Unknown provider '{slug}'") from err


def build_provider(
    slug: str,
    session: ClientSession,
    base_url: str | None = None,
    api_key: str | None = None,
) -> ImageProvider:
    """Instantiate a provider."""
    return get_provider_class(slug)(session, base_url=base_url, api_key=api_key)


def provider_options() -> list[dict[str, str]]:
    """Selector options for the config flow."""
    return [
        {"value": slug, "label": cls.title} for slug, cls in PROVIDERS.items()
    ]
