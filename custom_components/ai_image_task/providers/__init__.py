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
from .cloudflare_workers_ai import CloudflareWorkersAIProvider
from .gemini import GeminiImageProvider
from .huggingface import HuggingFaceImageProvider
from .openai_compatible import OpenAICompatibleProvider
from .pollinations import PollinationsProvider

PROVIDERS: dict[str, type[ImageProvider]] = {
    PollinationsProvider.slug: PollinationsProvider,
    CloudflareWorkersAIProvider.slug: CloudflareWorkersAIProvider,
    GeminiImageProvider.slug: GeminiImageProvider,
    HuggingFaceImageProvider.slug: HuggingFaceImageProvider,
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
    account_id: str | None = None,
) -> ImageProvider:
    """Instantiate a provider."""
    return get_provider_class(slug)(
        session, base_url=base_url, api_key=api_key, account_id=account_id
    )


def provider_options(free_only: bool = False) -> list[dict[str, str]]:
    """Selector options for the config flow."""
    return [
        {"value": slug, "label": cls.title}
        for slug, cls in PROVIDERS.items()
        if not free_only or cls.is_free
    ]


def provider_field_key(slug: str, field: str) -> str:
    """Return the config-entry key for one provider-specific setting."""
    return f"provider_{slug}_{field}"


def provider_config(slug: str, data: dict) -> dict[str, str | None]:
    """Read one provider's credentials and endpoint from config data."""
    return {
        "api_key": data.get(provider_field_key(slug, "api_key")) or None,
        "account_id": data.get(provider_field_key(slug, "account")) or None,
        "base_url": data.get(provider_field_key(slug, "base_url")) or None,
    }


def configured_provider_slugs(data: dict, preferred: str) -> list[str]:
    """Return configured providers, preferring the selected provider first."""
    configured = [preferred]
    for slug, provider_cls in PROVIDERS.items():
        if slug == preferred:
            continue
        credentials = provider_config(slug, data)
        if provider_cls.requires_api_key and not credentials["api_key"]:
            continue
        if provider_cls.requires_account_id and not credentials["account_id"]:
            continue
        if slug == OpenAICompatibleProvider.slug and not credentials["base_url"]:
            continue
        if slug == PollinationsProvider.slug and not credentials["api_key"]:
            continue
        configured.append(slug)
    return configured
