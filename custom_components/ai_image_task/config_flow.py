"""Config and options flow for AI Image Task."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import storage
from .image_utils import COLOR_MODES, FIT_MODES, OUTPUT_FORMATS
from .const import (
    CONF_API_KEY,
    CONF_ACCOUNT_ID,
    CONF_BASE_URL,
    CONF_FALLBACK_ACCOUNT_ID,
    CONF_FALLBACK_API_KEY,
    CONF_FALLBACK_PROVIDERS,
    CONF_GENERATE_ON_START,
    CONF_HISTORY_SUBDIR,
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
    CONF_KEEP_COUNT,
    CONF_KEEP_DAYS,
    CONF_NEGATIVE_TEMPLATE,
    CONF_OUTPUT_DIR,
    CONF_PROVIDER,
    CONF_RETENTION_MODE,
    CONF_RETRIES,
    CONF_SLOT_BW_LEVELS,
    CONF_SLOT_COLOR_MODE,
    CONF_SLOT_ENABLED,
    CONF_SLOT_EXACT_SIZE,
    CONF_SLOT_FILENAME,
    CONF_SLOT_FIT,
    CONF_SLOT_FORMAT,
    CONF_SLOT_HEIGHT,
    CONF_SLOT_MODEL,
    CONF_SLOT_NAME,
    CONF_SLOT_NEGATIVE,
    CONF_SLOT_PROMPT,
    CONF_SLOT_QUALITY,
    CONF_SLOT_REFERENCE_IMAGE,
    CONF_SLOT_SEED,
    CONF_SLOT_TRANSPARENT,
    CONF_SLOT_WIDTH,
    CONF_SLOTS,
    CONF_STAGGER,
    CONF_TIMEOUT,
    CONF_WRITE_METADATA,
    DEFAULT_BW_LEVELS,
    DEFAULT_COLOR_MODE,
    DEFAULT_EXACT_SIZE,
    DEFAULT_FIT,
    DEFAULT_FORMAT,
    DEFAULT_GENERATE_ON_START,
    DEFAULT_HEIGHT,
    DEFAULT_HISTORY_SUBDIR,
    DEFAULT_INTERVAL,
    DEFAULT_INTERVAL_UNIT,
    DEFAULT_KEEP_COUNT,
    DEFAULT_KEEP_DAYS,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_NEGATIVE_TEMPLATE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROVIDER,
    DEFAULT_QUALITY,
    DEFAULT_RETENTION_MODE,
    DEFAULT_RETRIES,
    DEFAULT_SEED,
    DEFAULT_SLOT_FILENAMES,
    DEFAULT_STAGGER,
    DEFAULT_TIMEOUT,
    DEFAULT_WIDTH,
    DEFAULT_WRITE_METADATA,
    DOMAIN,
    INTERVAL_UNITS,
    MAX_SLOTS,
    RETENTION_MODES,
)
from .providers import (
    PROVIDERS,
    ProviderAuthError,
    ProviderError,
    build_provider,
    configured_provider_slugs,
    get_provider_class,
    provider_config,
    provider_field_key,
    provider_options,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------
def _get(data: dict[str, Any], key: str, default: Any) -> Any:
    value = data.get(key, default)
    return default if value is None else value


def _provider_defaults(defaults: dict[str, Any]) -> dict[str, Any]:
    """Expose legacy single-provider credentials in the new per-provider form."""
    values = dict(defaults)
    legacy_slug = str(values.get(CONF_PROVIDER, DEFAULT_PROVIDER))
    if legacy_slug in PROVIDERS:
        legacy = {
            "api_key": values.get(CONF_API_KEY),
            "account": values.get(CONF_ACCOUNT_ID),
            "base_url": values.get(CONF_BASE_URL),
        }
        for field, value in legacy.items():
            key = provider_field_key(legacy_slug, field)
            if value and not values.get(key):
                values[key] = value

    fallback_providers = values.get(CONF_FALLBACK_PROVIDERS) or []
    if "cloudflare_workers_ai" in fallback_providers:
        for field, value in (
            ("api_key", values.get(CONF_FALLBACK_API_KEY)),
            ("account", values.get(CONF_FALLBACK_ACCOUNT_ID)),
        ):
            key = provider_field_key("cloudflare_workers_ai", field)
            if value and not values.get(key):
                values[key] = value
    return values


def general_schema(defaults: dict[str, Any], with_name: bool = True) -> vol.Schema:
    """Schema for the global settings."""
    defaults = _provider_defaults(defaults)
    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default=_get(defaults, CONF_NAME, DEFAULT_NAME))] = (
            selector.TextSelector()
        )

    fields.update(
        {
            vol.Required(
                CONF_PROVIDER, default=_get(defaults, CONF_PROVIDER, DEFAULT_PROVIDER)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=o["value"], label=o["label"])
                        for o in provider_options()
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_OUTPUT_DIR,
                default=_get(defaults, CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR),
            ): selector.TextSelector(),
            vol.Required(
                CONF_RETENTION_MODE,
                default=_get(defaults, CONF_RETENTION_MODE, DEFAULT_RETENTION_MODE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=RETENTION_MODES,
                    translation_key="retention_mode",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_KEEP_COUNT, default=_get(defaults, CONF_KEEP_COUNT, DEFAULT_KEEP_COUNT)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=1000, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_KEEP_DAYS, default=_get(defaults, CONF_KEEP_DAYS, DEFAULT_KEEP_DAYS)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=3650, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_HISTORY_SUBDIR,
                description={
                    "suggested_value": _get(
                        defaults, CONF_HISTORY_SUBDIR, DEFAULT_HISTORY_SUBDIR
                    )
                },
            ): selector.TextSelector(),
            vol.Required(
                CONF_TIMEOUT, default=_get(defaults, CONF_TIMEOUT, DEFAULT_TIMEOUT)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10, max=900, step=5, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_RETRIES, default=_get(defaults, CONF_RETRIES, DEFAULT_RETRIES)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=5, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_NEGATIVE_TEMPLATE,
                default=_get(
                    defaults, CONF_NEGATIVE_TEMPLATE, DEFAULT_NEGATIVE_TEMPLATE
                ),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Required(
                CONF_WRITE_METADATA,
                default=_get(defaults, CONF_WRITE_METADATA, DEFAULT_WRITE_METADATA),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_GENERATE_ON_START,
                default=_get(
                    defaults, CONF_GENERATE_ON_START, DEFAULT_GENERATE_ON_START
                ),
            ): selector.BooleanSelector(),
        }
    )
    provider_fields: dict[Any, Any] = {}
    for slug in PROVIDERS:
        prefix = provider_field_key(slug, "account")
        provider_fields[
            vol.Optional(
                prefix,
                description={"suggested_value": defaults.get(prefix, "")},
            )
        ] = selector.TextSelector()

        api_key = provider_field_key(slug, "api_key")
        provider_fields[
            vol.Optional(
                api_key,
                description={"suggested_value": defaults.get(api_key, "")},
            )
        ] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )

        if slug in ("pollinations", "openai_compatible"):
            base_url = provider_field_key(slug, "base_url")
            provider_fields[
                vol.Optional(
                    base_url,
                    description={"suggested_value": defaults.get(base_url, "")},
                )
            ] = selector.TextSelector()

        clear_key = provider_field_key(slug, "clear")
        provider_fields[
            vol.Optional(clear_key, default=False)
        ] = selector.BooleanSelector()
    field_items = list(fields.items())
    fields = dict(field_items[:1] + list(provider_fields.items()) + field_items[1:])
    return vol.Schema(fields)


def slot_schema(
    index: int, provider_slug: str, defaults: dict[str, Any]
) -> vol.Schema:
    """Schema for one image slot."""
    provider_cls = get_provider_class(provider_slug)
    extra = provider_cls.extra_options
    model_default = _get(defaults, CONF_SLOT_MODEL, DEFAULT_MODEL)
    if provider_slug in {
        "cloudflare_workers_ai",
        "google_gemini",
        "huggingface",
    } and model_default not in provider_cls.models:
        model_default = provider_cls.models[0]

    fields: dict[Any, Any] = {
        vol.Required(
            CONF_SLOT_NAME,
            default=_get(defaults, CONF_SLOT_NAME, f"Image {index + 1}"),
        ): selector.TextSelector(),
        vol.Required(
            CONF_SLOT_FILENAME,
            default=_get(
                defaults, CONF_SLOT_FILENAME, DEFAULT_SLOT_FILENAMES[index]
            ),
        ): selector.TextSelector(),
        vol.Required(
            CONF_SLOT_MODEL, default=model_default
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(provider_cls.models),
                custom_value=provider_slug != "cloudflare_workers_ai",
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_SLOT_WIDTH, default=_get(defaults, CONF_SLOT_WIDTH, DEFAULT_WIDTH)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=64, max=4096, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_SLOT_HEIGHT, default=_get(defaults, CONF_SLOT_HEIGHT, DEFAULT_HEIGHT)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=64, max=4096, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_SLOT_SEED, default=_get(defaults, CONF_SLOT_SEED, DEFAULT_SEED)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=-1, max=2147483647, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
    }

    fields[
        vol.Required(
            CONF_SLOT_EXACT_SIZE,
            default=_get(defaults, CONF_SLOT_EXACT_SIZE, DEFAULT_EXACT_SIZE),
        )
    ] = selector.BooleanSelector()
    fields[
        vol.Required(CONF_SLOT_FIT, default=_get(defaults, CONF_SLOT_FIT, DEFAULT_FIT))
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=FIT_MODES,
            translation_key="fit",
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )

    fields[
        vol.Required(
            CONF_SLOT_FORMAT, default=_get(defaults, CONF_SLOT_FORMAT, DEFAULT_FORMAT)
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=OUTPUT_FORMATS,
            translation_key="output_format",
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )
    fields[
        vol.Required(
            CONF_SLOT_COLOR_MODE,
            default=_get(defaults, CONF_SLOT_COLOR_MODE, DEFAULT_COLOR_MODE),
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=COLOR_MODES,
            translation_key="color_mode",
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )
    fields[
        vol.Required(
            CONF_SLOT_BW_LEVELS,
            default=_get(defaults, CONF_SLOT_BW_LEVELS, DEFAULT_BW_LEVELS),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=2, max=8, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )

    if "quality" in extra:
        fields[
            vol.Required(
                CONF_SLOT_QUALITY,
                default=_get(defaults, CONF_SLOT_QUALITY, DEFAULT_QUALITY),
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["low", "medium", "high", "hd"],
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    for key in ("transparent", "safe", "nologo", "private", "enhance"):
        if key in extra:
            const_key = CONF_SLOT_TRANSPARENT if key == "transparent" else key
            default = key in ("nologo", "private")
            fields[
                vol.Required(const_key, default=_get(defaults, const_key, default))
            ] = selector.BooleanSelector()
    if "reference_image" in extra:
        fields[
            vol.Optional(
                CONF_SLOT_REFERENCE_IMAGE,
                description={
                    "suggested_value": defaults.get(CONF_SLOT_REFERENCE_IMAGE, "")
                },
            )
        ] = selector.TextSelector()

    return vol.Schema(fields)


def normalise_general(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce numeric selector output to ints."""
    out = dict(data)
    for key in (
        CONF_KEEP_COUNT,
        CONF_KEEP_DAYS,
        CONF_TIMEOUT,
        CONF_RETRIES,
    ):
        if key in out and out[key] is not None:
            out[key] = int(float(out[key]))
    # Optional text fields are omitted from user_input entirely when the user
    # clears them in the UI; default them to "" so a later dict.update() on
    # the stored options actually clears the old value instead of keeping it.
    for slug in PROVIDERS:
        for field in ("account", "api_key"):
            key = provider_field_key(slug, field)
            out.setdefault(key, "")
        for field in ("base_url", "clear"):
            key = provider_field_key(slug, field)
            out.setdefault(key, "" if field == "base_url" else False)

        if out.pop(provider_field_key(slug, "clear"), False):
            out[provider_field_key(slug, "api_key")] = ""
            out[provider_field_key(slug, "account")] = ""
            out[provider_field_key(slug, "base_url")] = ""

    # Clear obsolete fields after migrating older entries to per-provider keys.
    for key in (
        CONF_BASE_URL,
        CONF_API_KEY,
        CONF_ACCOUNT_ID,
        CONF_FALLBACK_API_KEY,
        CONF_FALLBACK_ACCOUNT_ID,
        CONF_FALLBACK_PROVIDERS,
    ):
        out.pop(key, None)
    return out


def normalise_slot(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for key in (CONF_SLOT_WIDTH, CONF_SLOT_HEIGHT, CONF_SLOT_SEED, CONF_SLOT_BW_LEVELS):
        if key in out and out[key] is not None:
            out[key] = int(float(out[key]))
    if out.get(CONF_SLOT_FILENAME):
        out[CONF_SLOT_FILENAME] = storage.sanitize_filename(out[CONF_SLOT_FILENAME])
    return out


async def async_validate_general(hass, data: dict[str, Any]) -> dict[str, str]:
    """Validate the global step, returning form errors."""
    errors: dict[str, str] = {}
    try:
        await hass.async_add_executor_job(storage.check_directory, data[CONF_OUTPUT_DIR])
    except (OSError, PermissionError) as err:
        _LOGGER.error("Output directory problem: %s", err)
        errors[CONF_OUTPUT_DIR] = "invalid_directory"

    primary_slug = data[CONF_PROVIDER]
    primary_config = provider_config(primary_slug, data)
    if (
        primary_slug == "openai_compatible"
        and not primary_config["base_url"]
    ):
        errors[provider_field_key(primary_slug, "base_url")] = "invalid_provider_config"
    provider = build_provider(
        primary_slug,
        async_get_clientsession(hass),
        base_url=primary_config["base_url"],
        api_key=primary_config["api_key"],
        account_id=primary_config["account_id"],
    )
    try:
        await provider.async_validate()
    except ProviderAuthError as err:
        field_name = "account" if "account ID" in str(err) else "api_key"
        field = provider_field_key(primary_slug, field_name)
        errors[field] = "invalid_auth"
    except ProviderError:
        errors["base"] = "cannot_connect"
    return errors


# ---------------------------------------------------------------------------
# Config flow
# ---------------------------------------------------------------------------
class AiImageTaskConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._general: dict[str, Any] = {}
        self._slots: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = normalise_general(user_input)
            errors = await async_validate_general(self.hass, data)
            if not errors:
                self._general = data
                return await self.async_step_slot_1()
        return self.async_show_form(
            step_id="user",
            data_schema=general_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_slot_1(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            slots = [normalise_slot(user_input)]
            title = self._general.pop(CONF_NAME, DEFAULT_NAME)
            await self.async_set_unique_id(f"{DOMAIN}_{title.lower().strip()}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=title,
                data={},
                options={**self._general, CONF_SLOTS: slots},
            )
        return self.async_show_form(
            step_id="slot_1",
            data_schema=slot_schema(0, self._general[CONF_PROVIDER], {}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AiImageTaskOptionsFlow(config_entry)


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------
class AiImageTaskOptionsFlow(OptionsFlow):
    """Edit an existing entry."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._options: dict[str, Any] = {
            **config_entry.data,
            **config_entry.options,
        }
        self._options = _provider_defaults(self._options)
        slots = list(self._options.get(CONF_SLOTS) or [])
        while len(slots) < MAX_SLOTS:
            slots.append({})
        self._slots = slots

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["general", "slot_1"]
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = normalise_general(user_input)
            for slug in PROVIDERS:
                clear_key = provider_field_key(slug, "clear")
                if user_input.get(clear_key):
                    continue
                for field in ("api_key", "account", "base_url"):
                    config_key = provider_field_key(slug, field)
                    if (
                        config_key not in user_input
                        and self._options.get(config_key)
                    ):
                        data[config_key] = self._options[config_key]
            errors = await async_validate_general(self.hass, data)
            if not errors:
                self._options.update(data)
                for key in (
                    CONF_BASE_URL,
                    CONF_API_KEY,
                    CONF_ACCOUNT_ID,
                    CONF_FALLBACK_API_KEY,
                    CONF_FALLBACK_ACCOUNT_ID,
                    CONF_FALLBACK_PROVIDERS,
                ):
                    self._options.pop(key, None)
                return self._save()
        defaults = user_input or self._options
        return self.async_show_form(
            step_id="general",
            data_schema=general_schema(defaults, with_name=False),
            errors=errors,
        )

    async def async_step_slot_1(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_slot_step(0, "slot_1", user_input)

    async def _async_slot_step(
        self, index: int, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        if user_input is not None:
            slot = normalise_slot(user_input)
            for key in (CONF_SLOT_PROMPT, CONF_SLOT_NEGATIVE):
                if key not in slot and key in self._slots[index]:
                    slot[key] = self._slots[index][key]
            self._slots[index] = slot
            return self._save()
        return self.async_show_form(
            step_id=step_id,
            data_schema=slot_schema(
                index,
                self._options.get(CONF_PROVIDER, DEFAULT_PROVIDER),
                self._slots[index],
            ),
        )

    def _save(self) -> ConfigFlowResult:
        self._options[CONF_SLOTS] = self._slots
        return self.async_create_entry(title="", data=self._options)
