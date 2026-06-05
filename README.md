# Blossom

Macro for **Sol's RNG** — biomes, auras, merchants, potions, fishing. Fork of Noteab / Coteab; free on stable releases.

## Download

| Channel | Get it |
|---------|--------|
| **Stable** | [github.com/MaxxWasHere/blossom/releases](https://github.com/MaxxWasHere/blossom/releases) — download `Blossom-{version}.exe`, extract, run. No license key. |
| **Beta** | [github.com/MaxxWasHere/blossombeta/releases](https://github.com/MaxxWasHere/blossombeta/releases) — same exe name; you need a beta key on first launch. |

Windows only. If the window is blank, install [WebView2](https://developer.microsoft.com/microsoft-edge/webview2/).

## First run

1. Run the exe (or from source: `py run_local_ui.py` after `pip install -r requirements.txt`).
2. Calibrate — Macro Calibrations tab, or follow [this tutorial](https://youtu.be/s2S7Bncx9ns).
3. Beta only: paste your license key when prompted.
4. Optional: add a Discord webhook on the Webhook tab for biome / merchant pings.

More detail: [`docs/WHAT_IS_BLOSSOM.md`](docs/WHAT_IS_BLOSSOM.md).

## Common fixes

**Won't start?** Extract to a folder with your config. Try running as administrator.

**Uses rare potions / OCR wrong?** Set mouse delay 1000–2000 ms, or recalibrate OCR failsafe. Arial or Rubik font helps.

**False virus warning?** Open-source code; Windows often flags PyInstaller exes. Scan on VirusTotal or run in a VM if you want.

**Still stuck?** Full reinstall, then ask in the community Discord.

## Developers

Build and release notes: [`docs/RELEASE_AND_BUILD.md`](docs/RELEASE_AND_BUILD.md), [`docs/UPDATE_RELEASE.md`](docs/UPDATE_RELEASE.md).

License worker (beta keys): [`license-server/README.md`](license-server/README.md).

Apache 2.0 — see [`LICENSE.txt`](LICENSE.txt).
