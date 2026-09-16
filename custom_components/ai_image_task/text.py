"""Text entities allowing the prompts to be edited from a dashboard.

Home Assistant text entities are limited to 255 characters. Use the
``ai_image_task.set_prompt`` service for longer prompts.
"""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
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
    entities: list[TextEntity] = []
    for slot in coordinator.slots:
        entities.append(AiImageTaskPromptText(coordinator, slot, negative=False))
        entities.append(AiImageTaskPromptText(coordinator, slot, negative=True))
    async_add_entities(entities)


class AiImageTaskPromptText(AiImageTaskEntity, TextEntity, RestoreEntity):
    """Live editable prompt / negative prompt."""

    _attr_mode = TextMode.TEXT
    _attr_native_max = 255
    _attr_native_min = 0
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AiImageTaskCoordinator,
        slot: SlotState,
        negative: bool,
    ) -> None:
        key = "negative_prompt" if negative else "prompt"
        super().__init__(coordinator, slot, key)
        self._negative = negative
        self._attr_translation_key = key
        self._attr_icon = "mdi:comment-remove" if negative else "mdi:comment-text"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in (
            None,
            "unknown",
            "unavailable",
            "",
        ):
            self._apply(last_state.state)

    def _apply(self, value: str) -> None:
        if self._negative:
            self.coordinator.set_prompt(self._slot_index, None, value)
        else:
            self.coordinator.set_prompt(self._slot_index, value, None)

    @property
    def native_value(self) -> str:
        slot = self.slot
        value = slot.negative_prompt if self._negative else slot.prompt
        return value[:255]

    async def async_set_value(self, value: str) -> None:
        self._apply(value)
        self.async_write_ha_state()
