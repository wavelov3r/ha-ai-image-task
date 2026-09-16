"""Shared entity plumbing."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import AiImageTaskCoordinator, SlotState


class AiImageTaskEntity(CoordinatorEntity[AiImageTaskCoordinator]):
    """Base entity bound to one slot of a config entry."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AiImageTaskCoordinator,
        slot: SlotState,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._slot_index = slot.index
        self._last_slot = slot
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{slot.index}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{slot.index}")},
            name=f"{coordinator.entry.title} - {slot.name}",
            manufacturer=MANUFACTURER,
            model=str(coordinator.options.get("provider", "")),
            configuration_url="https://github.com/pollinations/pollinations",
        )

    @property
    def slot(self) -> SlotState:
        """Current slot state (re-read every time, survives reloads)."""
        slot = self.coordinator.get_slot(self._slot_index)
        if slot is not None:
            self._last_slot = slot
        return slot or self._last_slot

    @property
    def available(self) -> bool:
        return self.coordinator.get_slot(self._slot_index) is not None
