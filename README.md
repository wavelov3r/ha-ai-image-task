# AI Image Task

[![hacs][hacs-badge]][hacs-url]

Custom integration for Home Assistant that generates **up to 2 AI images** at regular intervals and saves them to disk with a stable filename, designed for e-ink frames, dashboards, smart refrigerators, and similar use cases.

The default provider is **[Pollinations.ai](https://pollinations.ai)**, available for free and without an account. The architecture is provider-based: adding others requires only a single Python class.

---

## Features

- 2 independent image slots (prompt, negative prompt, model, dimensions, seed, filename).
- A single update interval for both, in **minutes or hours**.
- Configurable output folder (default `/config/www/einkfrigo/images`).
- The current file **always keeps the same name** → the `/local/...` URL never changes.
- Three retention policies:
  - **Overwrite** — no history.
  - **Keep last N** — the previous version is archived with a timestamp, keeping the N most recent.
  - **Keep for N days** — archives are stored and those older than N days are deleted.
- Atomic writing (`.tmp` + `os.replace`): no truncated file can be read halfway through by an e-ink display.
- Configurable delay between the two requests, to respect Pollinations' anonymous rate limit (≈1 request every 15 s).
- Automatic retries with backoff on errors and `429`.
- Entities per slot: `image`, `sensor` (status / last generation / archives), `button` (generate now, clear history), `switch` (automatic update), `text` (prompt and negative prompt editable from the dashboard).
- Services: `ai_image_task.generate`, `ai_image_task.set_prompt`, `ai_image_task.clear_history`.
- Interface translated into Italian and English.

## Installation via HACS

1. HACS → ⋮ menu → **Custom repositories**.
2. URL: `https://github.com/wavelov3r/ha-ai-image-task`, category **Integration**.
3. Install "AI Image Task" and restart Home Assistant.
4. **Settings → Devices & services → Add integration → AI Image Task**.

### Manual installation

Copy the `custom_components/ai_image_task` folder into `/config/custom_components/` and restart.

## Configuration

### Step 1 — General settings

| Field | Description |
|---|---|
| Service | `Pollinations.ai (free)` or `OpenAI-compatible endpoint`. |
| API base URL | Empty = `https://gen.pollinations.ai`. For the legacy endpoint: `https://image.pollinations.ai`. |
| API key | Optional. From [enter.pollinations.ai](https://enter.pollinations.ai); raises limits and unlocks premium models. |
| Interval + unit | How often to regenerate (minutes or hours). |
| Destination folder | Default `/config/www/einkfrigo/images`. Created if it does not exist. |
| Retention policy | `Overwrite`, `Keep last N`, `Keep for N days`. |
| History subfolder | Default `history`. Empty = archive alongside the current file. |
| Delay between the two images | Default 20 s (Pollinations anonymous rate limit). |
| Timeout / Attempts | Default 180 s, 2 attempts. |
| Negative prompt template | Default `{prompt}\n\nAvoid the following: {negative}.` |
| `.json` metadata | Saves prompt, model, seed, URL alongside the image. |
| Generate on startup | If enabled, generates immediately after startup/reload. |

### Step 2 and 3 — Image 1 and Image 2

| Field | Description |
|---|---|
| Enable | Disable slot 2 if you only need one image. |
| Filename | E.g. `fridge_left.jpg`. The current file always keeps this name. |
| Prompt / Negative prompt | See note below about negative prompts. |
| Model | `zimage` (default), `flux`, `turbo`, `kontext`, `klein`, `nanobanana`, `seedream`, `qwen-image`, `wan-image`, `gptimage`, `p-image`. A model not in the list can be entered manually. |
| Width / Height | Final size in pixels (e.g. 800×480 for many e-ink displays). |
| Resize to exact size | Backends reject sides below 512 px: the integration requests a larger size with the same aspect ratio and then resizes the file to the exact requested dimensions. |
| Fit mode | `cover` (crop to fill), `contain` (white borders), `stretch` (distort). |
| Seed | `-1` = random on every run; fixed value = reproducible results. |
| Quality | `low/medium/high/hd`, only for the `gptimage` family. |
| Transparent background | Only for the `gptimage` family. |
| Safe mode / Remove watermark / Private generation / Enhance prompt | Optional provider flags. |
| Reference image URL | For editing/img2img models (`kontext`, `nanobanana`, `seedream`, `klein`). |

> **Note about negative prompts.** Pollinations' HTTP APIs do not expose a `negative_prompt` parameter. The integration combines the negative words with the prompt using the configurable template. This works well with instruction-following models (`zimage`, `gptimage`) and less well with purely diffusion-based models.

All settings can be modified later through **Configure** on the integration, with a three-item menu (General / Image 1 / Image 2).


Stable URL for an e-ink frame or picture card: `http://homeassistant.local:8123/local/einkfrigo/images/fridge_left.jpg`

## Created entities (per slot)

| Entity | Example | Notes |
|---|---|---|
| `image` | `image.ai_image_task_image_1` | Latest image, usable in a Picture Entity card. |
| `sensor` status | `sensor.ai_image_task_image_1_status` | `idle` / `generating` / `ok` / `error` / `disabled` + attributes (path, model, seed, URL, last error). |
| `sensor` last generation | `..._last_generated` | Timestamp. |
| `sensor` archives | `..._archived_images` | Number of historical copies. |
| `button` | `..._generate_now`, `..._clear_history` | |
| `switch` | `..._automatic_update` | Off = the slot is skipped by scheduling. State restored after restart. |
| `text` | `..._prompt`, `..._negative_prompt` | Edit on the fly (max 255 characters, HA limit). |

## Services

```yaml
# Regenerate everything immediately
action: ai_image_task.generate
data:
  slot: all

# Change the prompt (no length limit) and generate
action: ai_image_task.set_prompt
data:
  slot: 1
  prompt: >-
    Cozy scandinavian kitchen at sunrise, soft light, minimal,
    high contrast for e-ink display
  negative_prompt: text, watermark, people, blurry
  generate: true

# Clear history
action: ai_image_task.clear_history
data:
  slot: 2


Example: dynamic prompt based on weather
automation:
  - alias: Fridge image based on weather
    triggers:
      - trigger: time_pattern
        hours: "/3"
    actions:
      - action: ai_image_task.set_prompt
        data:
          slot: 1
          prompt: >-
            A minimal illustration of {{ states('weather.home') }} weather,
            {{ now().strftime('%B') }}, flat colors, high contrast, no text
          generate: true
