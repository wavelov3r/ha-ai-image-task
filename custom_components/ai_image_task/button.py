"""Buttons to force a generation or clear the history."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AiImageTaskCoordinator, SlotState
from .entity import AiImageTaskEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AiImageTaskCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = []
    for slot in coordinator.slots:
        entities.append(AiImageTaskGenerateButton(coordinator, slot))
        entities.append(AiImageTaskClearHistoryButton(coordinator, slot))
    async_add_entities(entities)


class AiImageTaskGenerateButton(AiImageTaskEntity, ButtonEntity):
    """Generate this slot right now."""

    _attr_translation_key = "generate_now"
    _attr_icon = "mdi:image-refresh"

    def __init__(self, coordinator: AiImageTaskCoordinator, slot: SlotState) -> None:
        super().__init__(coordinator, slot, "generate_now")

    async def async_press(self) -> None:
        await self.coordinator.async_generate_slot(self._slot_index, source="button")


class AiImageTaskClearHistoryButton(AiImageTaskEntity, ButtonEntity):
    """Delete every archived copy of this slot."""

    _attr_translation_key = "clear_history"
    _attr_icon = "mdi:delete-sweep"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AiImageTaskCoordinator, slot: SlotState) -> None:
        super().__init__(coordinator, slot, "clear_history")

    async def async_press(self) -> None:
        await self.coordinator.async_clear_history(self._slot_index)
