"""Image entities exposing the last generated picture."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AiImageTaskCoordinator, SlotState
from .entity import AiImageTaskEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AiImageTaskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AiImageTaskImage(hass, coordinator, slot) for slot in coordinator.slots
    )


class AiImageTaskImage(AiImageTaskEntity, ImageEntity):
    """The current image of a slot."""

    _attr_translation_key = "generated_image"
    _attr_name = None

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: AiImageTaskCoordinator,
        slot: SlotState,
    ) -> None:
        AiImageTaskEntity.__init__(self, coordinator, slot, "image")
        ImageEntity.__init__(self, hass)
        self._attr_content_type = "image/jpeg"
        self._attr_image_last_updated = slot.last_updated

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Load whatever is already on disk so the card is not empty at startup.
        await self.coordinator.async_image_bytes(self._slot_index)
        self._attr_image_last_updated = self.slot.last_updated
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        slot = self.slot
        if slot.last_updated != self._attr_image_last_updated:
            self._attr_image_last_updated = slot.last_updated
            self._cached_image = None
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        return await self.coordinator.async_image_bytes(self._slot_index)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        slot = self.slot
        return {
            "slot": slot.index + 1,
            "file_path": slot.last_path,
            "prompt": slot.prompt,
            "negative_prompt": slot.negative_prompt,
            "model": slot.last_model,
            "seed": slot.last_seed,
            "source_url": slot.last_url,
            "status": slot.status,
        }
