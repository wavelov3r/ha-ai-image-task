"""The AI Image Task integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_GENERATE,
    ATTR_NEGATIVE_PROMPT,
    ATTR_PROMPT,
    ATTR_SLOT,
    DOMAIN,
    MAX_SLOTS,
    PLATFORMS,
    SERVICE_CLEAR_HISTORY,
    SERVICE_GENERATE,
    SERVICE_SET_PROMPT,
)
from .coordinator import AiImageTaskCoordinator

_LOGGER = logging.getLogger(__name__)

_SLOT_SELECTOR = vol.Any("all", vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_SLOTS)))

SERVICE_GENERATE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_SLOT, default="all"): _SLOT_SELECTOR,
    }
)

SERVICE_SET_PROMPT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_SLOT): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_SLOTS)),
        vol.Optional(ATTR_PROMPT): cv.string,
        vol.Optional(ATTR_NEGATIVE_PROMPT): cv.string,
        vol.Optional(ATTR_GENERATE, default=False): cv.boolean,
    }
)

SERVICE_CLEAR_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_SLOT, default="all"): _SLOT_SELECTOR,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AI Image Task from a config entry."""
    coordinator = AiImageTaskCoordinator(hass, entry)
    await coordinator.async_prepare()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)

    if coordinator.generate_on_start:
        entry.async_create_background_task(
            hass, coordinator.async_refresh(), f"{DOMAIN}_initial_generation"
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
            for service in (SERVICE_GENERATE, SERVICE_SET_PROMPT, SERVICE_CLEAR_HISTORY):
                hass.services.async_remove(DOMAIN, service)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _coordinators(hass: HomeAssistant, entry_id: str | None) -> list[AiImageTaskCoordinator]:
    data: dict[str, AiImageTaskCoordinator] = hass.data.get(DOMAIN, {})
    if entry_id:
        coordinator = data.get(entry_id)
        if coordinator is None:
            raise ServiceValidationError(
                f"No AI Image Task config entry with id '{entry_id}'"
            )
        return [coordinator]
    return list(data.values())


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_GENERATE):
        return

    async def async_generate(call: ServiceCall) -> None:
        slot = call.data.get(ATTR_SLOT, "all")
        for coordinator in _coordinators(hass, call.data.get(ATTR_CONFIG_ENTRY_ID)):
            if slot == "all":
                await coordinator.async_generate_all(source="service")
            else:
                await coordinator.async_generate_slot(int(slot) - 1, source="service")

    async def async_set_prompt(call: ServiceCall) -> None:
        index = int(call.data[ATTR_SLOT]) - 1
        prompt = call.data.get(ATTR_PROMPT)
        negative = call.data.get(ATTR_NEGATIVE_PROMPT)
        for coordinator in _coordinators(hass, call.data.get(ATTR_CONFIG_ENTRY_ID)):
            coordinator.set_prompt(index, prompt, negative)
            if call.data.get(ATTR_GENERATE):
                await coordinator.async_generate_slot(index, source="service")

    async def async_clear_history(call: ServiceCall) -> None:
        slot = call.data.get(ATTR_SLOT, "all")
        for coordinator in _coordinators(hass, call.data.get(ATTR_CONFIG_ENTRY_ID)):
            await coordinator.async_clear_history(
                None if slot == "all" else int(slot) - 1
            )

    hass.services.async_register(
        DOMAIN, SERVICE_GENERATE, async_generate, schema=SERVICE_GENERATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_PROMPT, async_set_prompt, schema=SERVICE_SET_PROMPT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_HISTORY,
        async_clear_history,
        schema=SERVICE_CLEAR_HISTORY_SCHEMA,
    )
