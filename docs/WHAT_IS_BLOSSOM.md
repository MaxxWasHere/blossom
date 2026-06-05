# What is Blossom?

Blossom runs Sol's RNG for you — biomes, auras, merchants, potions, fishing — while you're AFK.

Fork of the Noteab / Coteab macro with a new UI and updated modules.

## What it does

- Reads game logs for biome and aura detection (works well once calibrated)
- Auto merchant — OCR finds Mari / Jester / Rin, buys from your lists
- Auto potions in any biome, including GLITCHED, DREAMSPACE, CYBERSPACE
- Fishing mode — bite detect, reel minigame, walk to dock, optional sell
- Discord webhooks — optional pings when rare biomes or merchants show up
- Anti-AFK mouse activity and session stats in the side panel

## Get it

- **Stable:** [MaxxWasHere/blossom releases](https://github.com/MaxxWasHere/blossom/releases)
- **Beta:** [MaxxWasHere/blossombeta releases](https://github.com/MaxxWasHere/blossombeta/releases) (license key required)

Download `Blossom-{version}.exe`, extract, run. Or clone the repo and run `py run_local_ui.py`.

## Setup

1. Calibrate positions in **Macro Calibrations** (video: [youtube.com/watch?v=s2S7Bncx9ns](https://www.youtube.com/watch?v=s2S7Bncx9ns)).
2. Turn on the automations you want on the Macro tab.
3. Beta builds: enter your key on the activation screen.
4. Webhooks are optional — Webhook tab if you want Discord alerts.

Advanced: custom walk paths via `tools/blossom_path_recorder.py`.

## FAQ

**Virus?** No. Source is public; Windows Defender often flags packed exes.

**Black / white window?** Install [WebView2](https://developer.microsoft.com/microsoft-edge/webview2/).

**Misdetects items?** Recalibrate OCR failsafe or raise input delay to 1000–2000 ms.

**Macro idle?** Run as admin; keep exe and config in the same folder.

Licensed Apache 2.0.
