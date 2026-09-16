"""Sensors: status of each slot and last generation timestamp."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
    entities: list[SensorEntity] = []
    for slot in coordinator.slots:
        entities.append(AiImageTaskStatusSensor(coordinator, slot))
        entities.append(AiImageTaskLastUpdatedSensor(coordinator, slot))
        entities.append(AiImageTaskHistorySensor(coordinator, slot))
    async_add_entities(entities)


class AiImageTaskStatusSensor(AiImageTaskEntity, SensorEntity):
    """idle / generating / ok / error / disabled."""

    _attr_translation_key = "status"
    _attr_icon = "mdi:image-auto-adjust"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "generating", "ok", "error", "disabled"]

    def __init__(self, coordinator: AiImageTaskCoordinator, slot: SlotState) -> None:
        super().__init__(coordinator, slot, "status")

    @property
    def native_value(self) -> str:
        return self.slot.status

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        slot = self.slot
        return {
            "slot": slot.index + 1,
            "prompt": slot.prompt,
            "negative_prompt": slot.negative_prompt,
            "filename": slot.filename,
            "file_path": slot.last_path,
            "model": slot.last_model,
            "seed": slot.last_seed,
            "size_bytes": slot.last_bytes,
            "source_url": slot.last_url,
            "last_error": slot.last_error,
            "last_attempt": slot.last_attempt,
            "history_count": slot.history_count,
            "output_dir": self.coordinator.output_dir,
            "retention_mode": self.coordinator.retention_mode,
            "update_interval": str(self.coordinator.interval),
        }


class AiImageTaskLastUpdatedSensor(AiImageTaskEntity, SensorEntity):
    """Timestamp of the last successful generation."""

    _attr_translation_key = "last_generated"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: AiImageTaskCoordinator, slot: SlotState) -> None:
        super().__init__(coordinator, slot, "last_generated")

    @property
    def native_value(self) -> datetime | None:
        return self.slot.last_updated


class AiImageTaskHistorySensor(AiImageTaskEntity, SensorEntity):
    """How many archived copies are kept on disk."""

    _attr_translation_key = "history_count"
    _attr_icon = "mdi:folder-multiple-image"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "files"

    def __init__(self, coordinator: AiImageTaskCoordinator, slot: SlotState) -> None:
        super().__init__(coordinator, slot, "history_count")

    @property
    def native_value(self) -> int:
        return self.slot.history_count
