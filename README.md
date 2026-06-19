# Blossom

Macro for **Sol's RNG** — biomes, auras, merchants, potions, fishing. Free on stable releases.

Based on the **Coteab** macro by Vapure (xVapure), which itself grew out of the original Noteab biome macro. Blossom keeps that core and adds its own UI and backend.

## Download

| Channel | Get it |
|---------|--------|
| **Stable** | [github.com/MaxxWasHere/blossom/releases](https://github.com/MaxxWasHere/blossom/releases) — download **`Blossom.exe`**, run it once. The launcher syncs the full app to `%LOCALAPPDATA%\Blossom\`. No license key. |
| **Beta** | [github.com/MaxxWasHere/blossombeta/releases](https://github.com/MaxxWasHere/blossombeta/releases) — download **`Blossom-beta.exe`**; same bootstrap install. You need a beta key on first launch. |

Windows only. If the window is blank, install [WebView2](https://developer.microsoft.com/microsoft-edge/webview2/).

## First run

1. Run **`Blossom.exe`** (stable) or **`Blossom-beta.exe`** (beta). First launch downloads the app payload and any optional runtime components into AppData, then opens Blossom.
2. Calibrate — Macro Calibrations tab, or follow [this tutorial](https://youtu.be/s2S7Bncx9ns).
3. Beta only: paste your license key when prompted.
4. Optional: add a Discord webhook on the Webhook tab for biome / merchant pings.

Keep the same launcher shortcut — it checks for updates on each run.

More detail: [What is Blossom?](https://maxxwashere.github.io/blossom.github.io/what-is-blossom.html).

## Documentation

Full guides and credits live on **GitHub Pages**: [maxxwashere.github.io/blossom.github.io](https://maxxwashere.github.io/blossom.github.io/)

- [Getting Started](https://maxxwashere.github.io/blossom.github.io/getting-started.html) — install, calibrate, run
- [Calibrations](https://maxxwashere.github.io/blossom.github.io/calibrations.html) · [Theming](https://maxxwashere.github.io/blossom.github.io/theming.html) · [Troubleshooting](https://maxxwashere.github.io/blossom.github.io/troubleshooting.html)
- [Credits](https://maxxwashere.github.io/blossom.github.io/credits.html) — authors, upstream lineage, third-party licenses

## Common fixes

**Won't start?** Extract to a folder with your config. Try running as administrator.

**Uses rare potions / OCR wrong?** Set mouse delay 1000–2000 ms, or recalibrate OCR failsafe. Arial or Rubik font helps.

**False virus warning?** Open-source code; Windows often flags PyInstaller exes. Scan on VirusTotal or run in a VM if you want.

**Still stuck?** Full reinstall, then ask in the community Discord.

## Developers

Build and release notes: [Release & build](https://maxxwashere.github.io/blossom.github.io/dev.html) (also on [blossom.github.io](https://github.com/MaxxWasHere/blossom.github.io)).

License worker (beta keys): [`license-server/README.md`](license-server/README.md).

Apache 2.0 — see [`LICENSE.txt`](LICENSE.txt).
