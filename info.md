# AI Image Task

[![hacs][hacs-badge]][hacs-url]

Custom integration per Home Assistant che genera **fino a 2 immagini AI** a intervalli regolari e le salva su disco con un nome stabile, pensata per cornici e-ink, dashboard, frigoriferi smart e simili.

Il provider predefinito è **[Pollinations.ai](https://pollinations.ai)**, utilizzabile gratuitamente e senza account. L'architettura è a provider: aggiungerne altri richiede una sola classe Python.

---

## Caratteristiche

- 2 slot immagine indipendenti (prompt, prompt negativo, modello, dimensioni, seed, nome file).
- Un solo intervallo di aggiornamento per entrambe, in **minuti oppure ore**.
- Cartella di output configurabile (default `/config/www/einkfrigo/images`).
- Il file corrente mantiene **sempre lo stesso nome** → l'URL `/local/...` non cambia mai.
- Tre politiche di conservazione:
  - **Sovrascrivi** — nessuno storico.
  - **Conserva le ultime N** — la versione precedente viene archiviata con timestamp, si tengono le N più recenti.
  - **Conserva per N giorni** — archivia ed elimina gli archivi più vecchi di N giorni.
- Scrittura atomica (`.tmp` + `os.replace`): nessun file troncato letto a metà da un e-ink.
- Sfasamento configurabile tra le due richieste, per rispettare il rate limit anonimo di Pollinations (≈1 richiesta ogni 15 s).
- Retry automatici con backoff su errori e `429`.
- Entità per slot: `image`, `sensor` (stato / ultima generazione / archivi), `button` (genera ora, svuota storico), `switch` (aggiornamento automatico), `text` (prompt e prompt negativo modificabili dalla dashboard).
- Servizi: `ai_image_task.generate`, `ai_image_task.set_prompt`, `ai_image_task.clear_history`.
- Interfaccia tradotta in italiano e inglese.

## Installazione via HACS

1. HACS → menu ⋮ → **Custom repositories**.
2. URL: `https://github.com/YOUR_GITHUB_USERNAME/ha-ai-image-task`, categoria **Integration**.
3. Installa "AI Image Task" e riavvia Home Assistant.
4. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → AI Image Task**.

### Installazione manuale

Copia la cartella `custom_components/ai_image_task` in `/config/custom_components/` e riavvia.

## Configurazione

### Passo 1 — Impostazioni generali

| Campo | Descrizione |
|---|---|
| Servizio | `Pollinations.ai (free)` oppure `OpenAI-compatible endpoint`. |
| URL base API | Vuoto = `https://gen.pollinations.ai`. Per l'endpoint legacy: `https://image.pollinations.ai`. |
| Chiave API | Facoltativa. Da [enter.pollinations.ai](https://enter.pollinations.ai); alza i limiti e sblocca i modelli premium. |
| Intervallo + unità | Ogni quanto rigenerare (minuti oppure ore). |
| Cartella di destinazione | Default `/config/www/einkfrigo/images`. Viene creata se non esiste. |
| Politica di conservazione | `Sovrascrivi`, `Conserva le ultime N`, `Conserva per N giorni`. |
| Sottocartella storico | Default `history`. Vuoto = archivia accanto al file corrente. |
| Attesa tra le due immagini | Default 20 s (rate limit anonimo Pollinations). |
| Timeout / Tentativi | Default 180 s, 2 tentativi. |
| Template prompt negativo | Default `{prompt}\n\nAvoid the following: {negative}.` |
| Metadati `.json` | Salva accanto all'immagine prompt, modello, seed, URL. |
| Genera all'avvio | Se attivo, genera subito dopo avvio/ricaricamento. |

### Passo 2 e 3 — Immagine 1 e Immagine 2

| Campo | Descrizione |
|---|---|
| Attiva | Disattiva lo slot 2 se ti serve una sola immagine. |
| Nome file | Es. `frigo_left.jpg`. Il file corrente mantiene sempre questo nome. |
| Prompt / Prompt negativo | Vedi nota sotto sui prompt negativi. |
| Modello | `zimage` (default), `flux`, `turbo`, `kontext`, `klein`, `nanobanana`, `seedream`, `qwen-image`, `wan-image`, `gptimage`, `p-image`. Si può digitare un modello non in elenco. |
| Larghezza / Altezza | In pixel (es. 800×480 per molti e-ink). |
| Seed | `-1` = casuale a ogni run; valore fisso = risultati riproducibili. |
| Qualità | `low/medium/high/hd`, solo per la famiglia `gptimage`. |
| Sfondo trasparente | Solo famiglia `gptimage`. |
| Modalità sicura / Rimuovi filigrana / Generazione privata / Migliora il prompt | Flag opzionali del provider. |
| URL immagine di riferimento | Per i modelli di editing/img2img (`kontext`, `nanobanana`, `seedream`, `klein`). |

> **Nota sui prompt negativi.** Le API HTTP di Pollinations non espongono un parametro `negative_prompt`. L'integrazione unisce le parole negative al prompt usando il template configurabile. Funziona bene con i modelli che seguono le istruzioni (`zimage`, `gptimage`) e meno con i modelli puramente diffusion.

Tutte le impostazioni sono modificabili in seguito da **Configura** sull'integrazione, con un menu a tre voci (Generale / Immagine 1 / Immagine 2).

## Come vengono organizzati i file

Con `Conserva le ultime 5` e nome file `frigo_left.jpg`:

```
/config/www/einkfrigo/images/
├── frigo_left.jpg                      ← sempre l'immagine corrente
├── frigo_left.json                     ← metadati (opzionale)
└── history/
    ├── frigo_left_20260916_080000.jpg
    ├── frigo_left_20260916_090000.jpg
    └── ...                             ← le più vecchie vengono eliminate
```

URL stabile per una cornice e-ink o una picture card: `http://homeassistant.local:8123/local/einkfrigo/images/frigo_left.jpg`

## Entità create (per slot)

| Entità | Esempio | Note |
|---|---|---|
| `image` | `image.ai_image_task_image_1` | Ultima immagine, utilizzabile in una Picture Entity card. |
| `sensor` stato | `sensor.ai_image_task_image_1_status` | `idle` / `generating` / `ok` / `error` / `disabled` + attributi (percorso, modello, seed, URL, ultimo errore). |
| `sensor` ultima generazione | `..._last_generated` | Timestamp. |
| `sensor` archivi | `..._archived_images` | Quante copie storiche ci sono. |
| `button` | `..._generate_now`, `..._clear_history` | |
| `switch` | `..._automatic_update` | Off = lo slot viene saltato dalla schedulazione. Stato ripristinato al riavvio. |
| `text` | `..._prompt`, `..._negative_prompt` | Modifica al volo (max 255 caratteri, limite di HA). |

## Servizi

```yaml
# Rigenera tutto subito
action: ai_image_task.generate
data:
  slot: all

# Cambia il prompt (nessun limite di lunghezza) e genera
action: ai_image_task.set_prompt
data:
  slot: 1
  prompt: >-
    Cozy scandinavian kitchen at sunrise, soft light, minimal,
    high contrast for e-ink display
  negative_prompt: text, watermark, people, blurry
  generate: true

# Svuota lo storico
action: ai_image_task.clear_history
data:
  slot: 2
```

### Esempio: prompt dinamico in base al meteo

```yaml
automation:
  - alias: Immagine frigo in base al meteo
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
```

## Limiti e note

- Uso anonimo di Pollinations: circa **1 richiesta ogni 15 secondi**. Tieni l'attesa tra le due immagini ≥ 15 s e non impostare intervalli troppo aggressivi.
- Il servizio è gratuito e "best effort": i fallimenti occasionali sono normali, per questo esistono i retry e l'ultima immagine valida resta sul disco.
- Le entità `text` sono limitate a 255 caratteri da Home Assistant; per prompt lunghi usa le opzioni dell'integrazione o `set_prompt`.
- Qualsiasi cosa dentro `/config/www` è servita da Home Assistant **senza autenticazione**: non generare immagini che contengano dati sensibili.

## Aggiungere un nuovo provider

1. Crea `custom_components/ai_image_task/providers/mio_provider.py` con una sottoclasse di `ImageProvider` che implementa `async_generate(request) -> ImageResult`.
2. Registrala in `providers/__init__.py` dentro `PROVIDERS`.
3. Dichiara i campi extra in `extra_options`: il config flow li mostra automaticamente.

## Licenza

MIT — vedi [LICENSE](LICENSE).

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
