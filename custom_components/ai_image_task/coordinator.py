"""Coordinator: schedules and performs the image generations."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import image_utils, storage
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
    CONF_SLOT_ENABLED,
    CONF_SLOT_EXACT_SIZE,
    CONF_SLOT_FILENAME,
    CONF_SLOT_FIT,
    CONF_SLOT_HEIGHT,
    CONF_SLOT_MODEL,
    CONF_SLOT_NAME,
    CONF_SLOT_NEGATIVE,
    CONF_SLOT_PROMPT,
    CONF_SLOT_SEED,
    CONF_SLOT_WIDTH,
    CONF_SLOTS,
    CONF_STAGGER,
    CONF_TIMEOUT,
    CONF_WRITE_METADATA,
    DEFAULT_EXACT_SIZE,
    DEFAULT_FIT,
    DEFAULT_GENERATE_ON_START,
    DEFAULT_HEIGHT,
    DEFAULT_HISTORY_SUBDIR,
    DEFAULT_INTERVAL,
    DEFAULT_INTERVAL_UNIT,
    DEFAULT_KEEP_COUNT,
    DEFAULT_KEEP_DAYS,
    DEFAULT_MODEL,
    DEFAULT_NEGATIVE_TEMPLATE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROVIDER,
    DEFAULT_RETENTION_MODE,
    DEFAULT_RETRIES,
    DEFAULT_SEED,
    DEFAULT_SLOT_FILENAMES,
    DEFAULT_STAGGER,
    DEFAULT_TIMEOUT,
    DEFAULT_WIDTH,
    DEFAULT_WRITE_METADATA,
    DOMAIN,
    MAX_SLOTS,
    RETENTION_OVERWRITE,
    UNIT_HOURS,
)
from .providers import ImageRequest, ProviderError, ProviderRateLimit, build_provider

_LOGGER = logging.getLogger(__name__)

# Per-slot keys that are *not* forwarded as provider options.
_CORE_SLOT_KEYS = {
    CONF_SLOT_ENABLED,
    CONF_SLOT_NAME,
    CONF_SLOT_FILENAME,
    CONF_SLOT_PROMPT,
    CONF_SLOT_NEGATIVE,
    CONF_SLOT_MODEL,
    CONF_SLOT_WIDTH,
    CONF_SLOT_HEIGHT,
    CONF_SLOT_SEED,
    CONF_SLOT_EXACT_SIZE,
    CONF_SLOT_FIT,
}


@dataclass
class SlotState:
    """Runtime state of one image slot."""

    index: int
    name: str
    enabled: bool
    filename: str
    prompt: str
    negative_prompt: str
    config: dict[str, Any] = field(default_factory=dict)

    last_updated: datetime | None = None
    last_attempt: datetime | None = None
    last_path: str | None = None
    last_url: str | None = None
    last_seed: int | None = None
    last_model: str | None = None
    last_error: str | None = None
    last_bytes: int | None = None
    history_count: int = 0
    generating: bool = False
    image_data: bytes | None = None

    @property
    def status(self) -> str:
        if self.generating:
            return "generating"
        if not self.enabled:
            return "disabled"
        if self.last_error:
            return "error"
        if self.last_updated:
            return "ok"
        return "idle"


class AiImageTaskCoordinator(DataUpdateCoordinator[dict[int, SlotState]]):
    """Owns the timer, the provider and the slots."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.options = {**entry.data, **entry.options}
        self.slots: list[SlotState] = []
        self._lock = asyncio.Lock()
        self._build_slots()

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.title}",
            update_interval=self.interval,
        )

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    def _opt(self, key: str, default: Any) -> Any:
        value = self.options.get(key, default)
        return default if value is None else value

    @property
    def interval(self) -> timedelta:
        amount = int(self._opt(CONF_INTERVAL, DEFAULT_INTERVAL) or DEFAULT_INTERVAL)
        amount = max(amount, 1)
        unit = self._opt(CONF_INTERVAL_UNIT, DEFAULT_INTERVAL_UNIT)
        if unit == UNIT_HOURS:
            return timedelta(hours=amount)
        return timedelta(minutes=amount)

    @property
    def output_dir(self) -> str:
        return str(self._opt(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR))

    @property
    def retention_mode(self) -> str:
        return str(self._opt(CONF_RETENTION_MODE, DEFAULT_RETENTION_MODE))

    @property
    def history_subdir(self) -> str | None:
        value = self._opt(CONF_HISTORY_SUBDIR, DEFAULT_HISTORY_SUBDIR)
        return str(value) if value else None

    @property
    def generate_on_start(self) -> bool:
        return bool(self._opt(CONF_GENERATE_ON_START, DEFAULT_GENERATE_ON_START))

    def _build_slots(self) -> None:
        """(Re)build slot runtime state from the entry configuration."""
        raw_slots = self.options.get(CONF_SLOTS) or []
        previous = {slot.index: slot for slot in self.slots}
        slots: list[SlotState] = []

        for index in range(MAX_SLOTS):
            raw = raw_slots[index] if index < len(raw_slots) else {}
            if not raw:
                continue
            old = previous.get(index)
            slot = SlotState(
                index=index,
                name=str(raw.get(CONF_SLOT_NAME) or f"Image {index + 1}"),
                enabled=bool(raw.get(CONF_SLOT_ENABLED, index == 0)),
                filename=storage.sanitize_filename(
                    raw.get(CONF_SLOT_FILENAME) or DEFAULT_SLOT_FILENAMES[index]
                ),
                prompt=str(raw.get(CONF_SLOT_PROMPT) or ""),
                negative_prompt=str(raw.get(CONF_SLOT_NEGATIVE) or ""),
                config=dict(raw),
            )
            if old is not None:
                # keep runtime info across reloads
                slot.last_updated = old.last_updated
                slot.last_path = old.last_path
                slot.last_url = old.last_url
                slot.last_seed = old.last_seed
                slot.last_model = old.last_model
                slot.last_error = old.last_error
                slot.history_count = old.history_count
                slot.image_data = old.image_data
            slots.append(slot)
        self.slots = slots

    def get_slot(self, index: int) -> SlotState | None:
        for slot in self.slots:
            if slot.index == index:
                return slot
        return None

    def _provider_options(self, slot: SlotState) -> dict[str, Any]:
        return {
            key: value
            for key, value in slot.config.items()
            if key not in _CORE_SLOT_KEYS and value not in (None, "")
        }

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> dict[int, SlotState]:
        """Scheduled run: generate every enabled slot, staggered."""
        await self.async_generate_all(source="schedule")
        return {slot.index: slot for slot in self.slots}

    async def async_generate_all(self, source: str = "manual") -> None:
        stagger = int(self._opt(CONF_STAGGER, DEFAULT_STAGGER))
        enabled = [slot for slot in self.slots if slot.enabled]
        for position, slot in enumerate(enabled):
            await self.async_generate_slot(slot.index, source=source)
            if position < len(enabled) - 1 and stagger > 0:
                _LOGGER.debug("Waiting %ss before the next slot (rate limit)", stagger)
                await asyncio.sleep(stagger)

    async def async_generate_slot(self, index: int, source: str = "manual") -> bool:
        """Generate and persist one image. Returns True on success."""
        slot = self.get_slot(index)
        if slot is None:
            _LOGGER.warning("Slot %s is not configured", index + 1)
            return False
        if not slot.prompt.strip():
            slot.last_error = "Empty prompt"
            self.async_update_listeners()
            return False

        async with self._lock:
            slot.generating = True
            slot.last_attempt = dt_util.utcnow()
            self.async_update_listeners()
            try:
                return await self._async_run_slot(slot, source)
            finally:
                slot.generating = False
                self.async_update_listeners()

    async def _async_run_slot(self, slot: SlotState, source: str) -> bool:
        session = async_get_clientsession(self.hass)
        provider = build_provider(
            str(self._opt(CONF_PROVIDER, DEFAULT_PROVIDER)),
            session,
            base_url=self.options.get(CONF_BASE_URL) or None,
            api_key=self.options.get(CONF_API_KEY) or None,
        )
        request = ImageRequest(
            prompt=slot.prompt,
            negative_prompt=slot.negative_prompt,
            negative_template=str(
                self._opt(CONF_NEGATIVE_TEMPLATE, DEFAULT_NEGATIVE_TEMPLATE)
            ),
            model=slot.config.get(CONF_SLOT_MODEL) or DEFAULT_MODEL,
            width=int(slot.config.get(CONF_SLOT_WIDTH) or DEFAULT_WIDTH),
            height=int(slot.config.get(CONF_SLOT_HEIGHT) or DEFAULT_HEIGHT),
            seed=int(slot.config.get(CONF_SLOT_SEED, DEFAULT_SEED)),
            timeout=int(self._opt(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
            options=self._provider_options(slot),
        )

        retries = max(int(self._opt(CONF_RETRIES, DEFAULT_RETRIES)), 0)
        result = None
        last_error: str | None = None

        for attempt in range(retries + 1):
            try:
                result = await provider.async_generate(request)
                break
            except ProviderRateLimit as err:
                last_error = str(err)
                delay = err.retry_after or (15 * (attempt + 1))
                if attempt < retries:
                    _LOGGER.warning(
                        "%s rate limited, retrying in %ss", slot.name, delay
                    )
                    await asyncio.sleep(min(delay, 120))
            except ProviderError as err:
                last_error = str(err)
                if attempt < retries:
                    await asyncio.sleep(5 * (attempt + 1))
            except Exception as err:  # noqa: BLE001 - never kill the timer
                last_error = f"Unexpected error: {err}"
                _LOGGER.exception("Unexpected error generating %s", slot.name)
                break

        if result is None:
            slot.last_error = last_error or "Unknown error"
            _LOGGER.error("Generation failed for %s: %s", slot.name, slot.last_error)
            return False

        target_w = int(slot.config.get(CONF_SLOT_WIDTH) or DEFAULT_WIDTH)
        target_h = int(slot.config.get(CONF_SLOT_HEIGHT) or DEFAULT_HEIGHT)
        resized = False
        if bool(slot.config.get(CONF_SLOT_EXACT_SIZE, DEFAULT_EXACT_SIZE)) and (
            result.width != target_w or result.height != target_h
        ):
            new_bytes, new_type = await self.hass.async_add_executor_job(
                image_utils.fit_image,
                result.content,
                target_w,
                target_h,
                str(slot.config.get(CONF_SLOT_FIT) or DEFAULT_FIT),
            )
            if new_bytes is not result.content:
                resized = len(new_bytes) != len(result.content)
                result.content = new_bytes
                if new_type:
                    result.content_type = new_type

        metadata = None
        if bool(self._opt(CONF_WRITE_METADATA, DEFAULT_WRITE_METADATA)):
            metadata = {
                "generated_at": dt_util.utcnow().isoformat(),
                "source": source,
                "provider": str(self._opt(CONF_PROVIDER, DEFAULT_PROVIDER)),
                "model": result.model,
                "seed": result.seed,
                "prompt": slot.prompt,
                "negative_prompt": slot.negative_prompt,
                "final_prompt": result.revised_prompt,
                "width": target_w,
                "height": target_h,
                "requested_width": result.width,
                "requested_height": result.height,
                "resized": resized,
                "url": result.url,
            }

        try:
            save = await self.hass.async_add_executor_job(
                lambda: storage.save_image(
                    result.content,
                    self.output_dir,
                    slot.filename,
                    self.retention_mode,
                    int(self._opt(CONF_KEEP_COUNT, DEFAULT_KEEP_COUNT)),
                    int(self._opt(CONF_KEEP_DAYS, DEFAULT_KEEP_DAYS)),
                    self.history_subdir,
                    metadata,
                )
            )
        except OSError as err:
            slot.last_error = f"Cannot write file: {err}"
            _LOGGER.error("Cannot save image for %s: %s", slot.name, err)
            return False

        slot.image_data = result.content
        slot.last_updated = dt_util.utcnow()
        slot.last_path = save.path
        slot.last_url = result.url
        slot.last_seed = result.seed
        slot.last_model = result.model
        slot.last_bytes = len(result.content)
        slot.history_count = save.history_count
        slot.last_error = None
        _LOGGER.info(
            "%s: saved %s (%s bytes, model=%s, seed=%s, history=%s)",
            slot.name,
            save.path,
            len(result.content),
            result.model,
            result.seed,
            save.history_count,
        )
        return True

    # ------------------------------------------------------------------
    # Misc helpers used by entities and services
    # ------------------------------------------------------------------
    async def async_prepare(self) -> None:
        """Create the output directory and read the current history counts."""
        try:
            await self.hass.async_add_executor_job(
                storage.ensure_directory, self.output_dir
            )
        except OSError as err:
            _LOGGER.error("Output directory '%s' unusable: %s", self.output_dir, err)

        for slot in self.slots:
            try:
                slot.history_count = await self.hass.async_add_executor_job(
                    storage.count_history,
                    self.output_dir,
                    slot.filename,
                    self.history_subdir,
                )
            except OSError:
                slot.history_count = 0
        self.data = {slot.index: slot for slot in self.slots}

    async def async_image_bytes(self, index: int) -> bytes | None:
        """Bytes of the current image, falling back to the file on disk."""
        slot = self.get_slot(index)
        if slot is None:
            return None
        if slot.image_data:
            return slot.image_data
        path = slot.last_path or f"{self.output_dir.rstrip('/')}/{slot.filename}"
        data = await self.hass.async_add_executor_job(storage.read_file, path)
        if data:
            slot.image_data = data
            if slot.last_updated is None:
                slot.last_updated = dt_util.utcnow()
        return data

    async def async_clear_history(self, index: int | None = None) -> int:
        targets = self.slots if index is None else [s for s in self.slots if s.index == index]
        removed = 0
        for slot in targets:
            removed += await self.hass.async_add_executor_job(
                storage.clear_history, self.output_dir, slot.filename, self.history_subdir
            )
            slot.history_count = 0
        self.async_update_listeners()
        return removed

    def set_prompt(
        self, index: int, prompt: str | None, negative_prompt: str | None
    ) -> None:
        slot = self.get_slot(index)
        if slot is None:
            return
        if prompt is not None:
            slot.prompt = prompt
        if negative_prompt is not None:
            slot.negative_prompt = negative_prompt
        self.async_update_listeners()

    def set_enabled(self, index: int, enabled: bool) -> None:
        slot = self.get_slot(index)
        if slot is None:
            return
        slot.enabled = enabled
        self.async_update_listeners()

    @property
    def keeps_history(self) -> bool:
        return self.retention_mode != RETENTION_OVERWRITE
