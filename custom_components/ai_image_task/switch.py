"""Switch to enable/disable the automatic refresh of a slot."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import AiImageTaskCoordinator, SlotState
from .entity import AiImageTaskEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AiImageTaskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AiImageTaskEnabledSwitch(coordinator, slot) for slot in coordinator.slots
    )


class AiImageTaskEnabledSwitch(AiImageTaskEntity, SwitchEntity, RestoreEntity):
    """When off, the scheduled run skips this slot."""

    _attr_translation_key = "auto_update"
    _attr_icon = "mdi:autorenew"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AiImageTaskCoordinator, slot: SlotState) -> None:
        super().__init__(coordinator, slot, "auto_update")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self.coordinator.set_enabled(self._slot_index, last_state.state == "on")

    @property
    def is_on(self) -> bool:
        return self.slot.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.set_enabled(self._slot_index, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_enabled(self._slot_index, False)
        self.async_write_ha_state()
