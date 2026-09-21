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
    CONF_BASE_URL,
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
    ProviderAuthError,
    ProviderError,
    build_provider,
    get_provider_class,
    provider_options,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------
def _get(data: dict[str, Any], key: str, default: Any) -> Any:
    value = data.get(key, default)
    return default if value is None else value


def general_schema(defaults: dict[str, Any], with_name: bool = True) -> vol.Schema:
    """Schema for the global settings."""
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
            vol.Optional(
                CONF_BASE_URL,
                description={"suggested_value": defaults.get(CONF_BASE_URL, "")},
            ): selector.TextSelector(),
            vol.Optional(
                CONF_API_KEY,
                description={"suggested_value": defaults.get(CONF_API_KEY, "")},
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_INTERVAL, default=_get(defaults, CONF_INTERVAL, DEFAULT_INTERVAL)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=10000, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_INTERVAL_UNIT,
                default=_get(defaults, CONF_INTERVAL_UNIT, DEFAULT_INTERVAL_UNIT),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=INTERVAL_UNITS,
                    translation_key="interval_unit",
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
                CONF_STAGGER, default=_get(defaults, CONF_STAGGER, DEFAULT_STAGGER)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=600, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
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
    return vol.Schema(fields)


def slot_schema(
    index: int, provider_slug: str, defaults: dict[str, Any]
) -> vol.Schema:
    """Schema for one image slot."""
    provider_cls = get_provider_class(provider_slug)
    extra = provider_cls.extra_options

    fields: dict[Any, Any] = {
        vol.Required(
            CONF_SLOT_ENABLED,
            default=_get(defaults, CONF_SLOT_ENABLED, index == 0),
        ): selector.BooleanSelector(),
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
        vol.Optional(
            CONF_SLOT_PROMPT,
            description={"suggested_value": defaults.get(CONF_SLOT_PROMPT, "")},
        ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        vol.Optional(
            CONF_SLOT_NEGATIVE,
            description={"suggested_value": defaults.get(CONF_SLOT_NEGATIVE, "")},
        ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        vol.Required(
            CONF_SLOT_MODEL, default=_get(defaults, CONF_SLOT_MODEL, DEFAULT_MODEL)
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(provider_cls.models),
                custom_value=True,
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
        CONF_INTERVAL,
        CONF_KEEP_COUNT,
        CONF_KEEP_DAYS,
        CONF_STAGGER,
        CONF_TIMEOUT,
        CONF_RETRIES,
    ):
        if key in out and out[key] is not None:
            out[key] = int(float(out[key]))
    # Optional text fields are omitted from user_input entirely when the user
    # clears them in the UI; default them to "" so a later dict.update() on
    # the stored options actually clears the old value instead of keeping it.
    for key in (CONF_BASE_URL, CONF_API_KEY):
        out.setdefault(key, "")
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

    provider = build_provider(
        data[CONF_PROVIDER],
        async_get_clientsession(hass),
        base_url=data.get(CONF_BASE_URL) or None,
        api_key=data.get(CONF_API_KEY) or None,
    )
    try:
        await provider.async_validate()
    except ProviderAuthError:
        errors[CONF_API_KEY] = "invalid_auth"
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
            self._slots = [normalise_slot(user_input)]
            return await self.async_step_slot_2()
        return self.async_show_form(
            step_id="slot_1",
            data_schema=slot_schema(0, self._general[CONF_PROVIDER], {}),
        )

    async def async_step_slot_2(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._slots.append(normalise_slot(user_input))
            title = self._general.pop(CONF_NAME, DEFAULT_NAME)
            await self.async_set_unique_id(f"{DOMAIN}_{title.lower().strip()}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=title,
                data={},
                options={**self._general, CONF_SLOTS: self._slots},
            )
        return self.async_show_form(
            step_id="slot_2",
            data_schema=slot_schema(
                1,
                self._general[CONF_PROVIDER],
                {CONF_SLOT_ENABLED: False},
            ),
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
        slots = list(self._options.get(CONF_SLOTS) or [])
        while len(slots) < MAX_SLOTS:
            slots.append({})
        self._slots = slots

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["general", "slot_1", "slot_2"]
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = normalise_general(user_input)
            errors = await async_validate_general(self.hass, data)
            if not errors:
                self._options.update(data)
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

    async def async_step_slot_2(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_slot_step(1, "slot_2", user_input)

    async def _async_slot_step(
        self, index: int, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._slots[index] = normalise_slot(user_input)
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
