"""Provider abstraction for AI Image Task.

Adding a new provider only requires subclassing :class:`ImageProvider` and
registering it in ``providers/__init__.py``.  Nothing else in the integration
needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from aiohttp import ClientSession


class ProviderError(Exception):
    """Generic provider failure."""


class ProviderRateLimit(ProviderError):
    """The provider asked us to slow down."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderAuthError(ProviderError):
    """Invalid or missing API key."""


@dataclass(slots=True)
class ImageRequest:
    """A single image generation request."""

    prompt: str
    negative_prompt: str = ""
    negative_template: str = "{prompt}\n\nAvoid the following: {negative}."
    model: str | None = None
    width: int = 1024
    height: int = 1024
    seed: int = -1
    timeout: int = 180
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def full_prompt(self) -> str:
        """Prompt with the negative prompt folded in.

        Most free text-to-image HTTP APIs (Pollinations included) have no
        dedicated ``negative_prompt`` parameter, so the negative words are
        appended to the prompt using a configurable template.
        """
        prompt = (self.prompt or "").strip()
        negative = (self.negative_prompt or "").strip()
        if not negative:
            return prompt
        return self.negative_template.format(prompt=prompt, negative=negative)


@dataclass(slots=True)
class ImageResult:
    """The outcome of a successful generation."""

    content: bytes
    content_type: str
    url: str | None = None
    model: str | None = None
    seed: int | None = None
    revised_prompt: str | None = None
    #: dimensions actually requested to the backend (may differ from the ones
    #: asked by the user when the backend has minimum-size constraints)
    width: int | None = None
    height: int | None = None

    @property
    def extension(self) -> str:
        """Best guess file extension for the returned bytes."""
        if "png" in self.content_type:
            return ".png"
        if "webp" in self.content_type:
            return ".webp"
        return ".jpg"


class ImageProvider(ABC):
    """Base class every provider implements."""

    #: machine id used in the config entry
    slug: str = "base"
    #: human readable name shown in the config flow
    title: str = "Base"
    #: default API base url
    default_base_url: str = ""
    #: whether an API key is mandatory
    requires_api_key: bool = False
    #: models offered in the UI (free text is still allowed)
    models: tuple[str, ...] = ()
    #: optional per-slot settings this provider understands, with a short
    #: description used by the config flow / documentation
    extra_options: dict[str, str] = {}

    def __init__(
        self,
        session: ClientSession,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._session = session
        self._base_url = (base_url or self.default_base_url).rstrip("/")
        self._api_key = api_key or None

    @property
    def base_url(self) -> str:
        return self._base_url

    @abstractmethod
    async def async_generate(self, request: ImageRequest) -> ImageResult:
        """Generate one image or raise a :class:`ProviderError`."""

    async def async_validate(self) -> None:
        """Optional lightweight connectivity/credential check."""
        return None
