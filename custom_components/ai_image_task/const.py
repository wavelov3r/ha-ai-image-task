"""Constants for the AI Image Task integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ai_image_task"
MANUFACTURER: Final = "AI Image Task"

PLATFORMS: Final = ["image", "sensor", "button", "switch", "text"]

# Maximum number of image slots handled by a single config entry.
MAX_SLOTS: Final = 2

# ---------------------------------------------------------------------------
# Global (entry level) configuration keys
# ---------------------------------------------------------------------------
CONF_PROVIDER: Final = "provider"
CONF_API_KEY: Final = "api_key"
CONF_BASE_URL: Final = "base_url"
CONF_INTERVAL: Final = "update_interval"
CONF_INTERVAL_UNIT: Final = "update_interval_unit"
CONF_OUTPUT_DIR: Final = "output_dir"
CONF_RETENTION_MODE: Final = "retention_mode"
CONF_KEEP_COUNT: Final = "keep_count"
CONF_KEEP_DAYS: Final = "keep_days"
CONF_HISTORY_SUBDIR: Final = "history_subdir"
CONF_STAGGER: Final = "stagger_seconds"
CONF_TIMEOUT: Final = "timeout"
CONF_RETRIES: Final = "retries"
CONF_WRITE_METADATA: Final = "write_metadata"
CONF_NEGATIVE_TEMPLATE: Final = "negative_template"
CONF_GENERATE_ON_START: Final = "generate_on_start"
CONF_SLOTS: Final = "slots"

# ---------------------------------------------------------------------------
# Per slot configuration keys
# ---------------------------------------------------------------------------
CONF_SLOT_ENABLED: Final = "enabled"
CONF_SLOT_NAME: Final = "name"
CONF_SLOT_FILENAME: Final = "filename"
CONF_SLOT_PROMPT: Final = "prompt"
CONF_SLOT_NEGATIVE: Final = "negative_prompt"
CONF_SLOT_MODEL: Final = "model"
CONF_SLOT_WIDTH: Final = "width"
CONF_SLOT_HEIGHT: Final = "height"
CONF_SLOT_SEED: Final = "seed"
CONF_SLOT_ENHANCE: Final = "enhance"
CONF_SLOT_NOLOGO: Final = "nologo"
CONF_SLOT_PRIVATE: Final = "private"
CONF_SLOT_SAFE: Final = "safe"
CONF_SLOT_QUALITY: Final = "quality"
CONF_SLOT_TRANSPARENT: Final = "transparent"
CONF_SLOT_REFERENCE_IMAGE: Final = "reference_image"
CONF_SLOT_EXACT_SIZE: Final = "exact_size"
CONF_SLOT_FIT: Final = "fit"
CONF_SLOT_FORMAT: Final = "output_format"
CONF_SLOT_COLOR_MODE: Final = "color_mode"
CONF_SLOT_BW_LEVELS: Final = "bw_levels"

# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
RETENTION_OVERWRITE: Final = "overwrite"
RETENTION_KEEP_LAST: Final = "keep_last"
RETENTION_KEEP_DAYS: Final = "keep_days"
RETENTION_MODES: Final = [RETENTION_OVERWRITE, RETENTION_KEEP_LAST, RETENTION_KEEP_DAYS]

# ---------------------------------------------------------------------------
# Interval units
# ---------------------------------------------------------------------------
UNIT_MINUTES: Final = "minutes"
UNIT_HOURS: Final = "hours"
INTERVAL_UNITS: Final = [UNIT_MINUTES, UNIT_HOURS]

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_NAME: Final = "AI Image Task"
DEFAULT_PROVIDER: Final = "pollinations"
DEFAULT_OUTPUT_DIR: Final = "/config/www/einkfrigo/images"
DEFAULT_INTERVAL: Final = 60
DEFAULT_INTERVAL_UNIT: Final = UNIT_MINUTES
DEFAULT_RETENTION_MODE: Final = RETENTION_OVERWRITE
DEFAULT_KEEP_COUNT: Final = 10
DEFAULT_KEEP_DAYS: Final = 7
DEFAULT_HISTORY_SUBDIR: Final = "history"
DEFAULT_STAGGER: Final = 20
DEFAULT_TIMEOUT: Final = 180
DEFAULT_RETRIES: Final = 2
DEFAULT_WRITE_METADATA: Final = False
DEFAULT_GENERATE_ON_START: Final = True
DEFAULT_NEGATIVE_TEMPLATE: Final = "{prompt}\n\nAvoid the following: {negative}."

DEFAULT_WIDTH: Final = 1024
DEFAULT_HEIGHT: Final = 1024
DEFAULT_SEED: Final = -1  # -1 -> random seed on every run
DEFAULT_MODEL: Final = "zimage"
DEFAULT_QUALITY: Final = "medium"
DEFAULT_EXACT_SIZE: Final = True
DEFAULT_FIT: Final = "cover"
DEFAULT_FORMAT: Final = "auto"
DEFAULT_COLOR_MODE: Final = "color"
DEFAULT_BW_LEVELS: Final = 2  # 2-8 gray levels, dithered with Floyd-Steinberg

DEFAULT_SLOT_FILENAMES: Final = ["image_1.jpg", "image_2.jpg"]

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
SERVICE_GENERATE: Final = "generate"
SERVICE_SET_PROMPT: Final = "set_prompt"
SERVICE_CLEAR_HISTORY: Final = "clear_history"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_SLOT: Final = "slot"
ATTR_PROMPT: Final = "prompt"
ATTR_NEGATIVE_PROMPT: Final = "negative_prompt"
ATTR_GENERATE: Final = "generate"

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
MIN_IMAGE_BYTES: Final = 1024
STORAGE_VERSION: Final = 1
