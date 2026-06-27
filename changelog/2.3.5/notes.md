# Blossom 2.3.5

## New
- Music player — open it from the new **Music** sidebar category, which shows the player as a full in-app page (everything fits inside: now-playing, transport, seek/volume/speed, a scrolling playlist and the add-track section). Add tracks by pasting a web URL or browsing a local audio file (mp3, wav, ogg, m4a, flac…), then play/pause, seek, skip, shuffle and repeat. Adjust volume, mute, and playback speed (0.5×–2×), reorder or remove tracks. The page opens/closes with spring scale/fade motion, the sidebar selection animates like the other categories, and the player closes when you pick another category (audio keeps playing in the background). Closed by default on launch; your playlist, volume, speed, loop, shuffle and last track save to your config and restore when you reopen the player (no auto-play on launch; local files keep their path in config, not a data URL).
- Animated background — Appearance has a new **Animated background** card with live wallpaper presets (Aurora, Mesh, Stars, Bubbles), plus a **Custom media** preset that uses your own video, gif or image — paste a web URL or **Browse** a local file (local media is streamed back through the app's server, so large videos work without base64). Opacity, blur, dim and speed sliders tune the look; speed controls video playback rate. The background sits behind cards, the toolbar, inputs and sidebar items, so most surfaces stay solid and text stays readable; it freezes to a static frame (and videos pause) when Reduce motion is on. Off by default.

## UI
- Expressive motion everywhere — inputs, selects, checkboxes, chips, badges, secondary buttons, titlebar controls, list/table rows, links and code now share the same Material 3 Expressive easing: hover lifts, press springs, focus glows, and a checked pop. Dialogs, toasts, the command palette and the license gate get container-transform entrances; injected Blossom panels (Appearance, Animated background, Fishing, Merchant, Biome webhooks) fade-rise on mount. All gated on Appearance → Reduce motion.

## Fixed
- Aura and reconnect detection: loosened the Roblox log regexes to the original's robust capture, so equipped-aura and reconnect-success events aren't missed when the RPC field order differs or `smallImage` is absent.
- Biome Selector (WIP): the OCR-engine prompt now says "Windows OCR" instead of "Tesseract", and a dead confirm/cancel OCR guard was removed.
- Core: removed unreachable dead code in the interruptible sleep helper.

## Macro
- Fishing + merchant teleporter: when the teleporter fires mid fishing cycle, the macro now walks back to the dock and resumes fishing instead of clicking the fish button while still in Limbo and eventually force-rejoining.
- Merchant auto-buy: restored the original ~3.35s post-purchase dialogue hold so multi-item buys finish before the next slot is clicked.
- Merchant pre-scan: name detection is again an 8-click + 4.25s dialogue hold instead of 16 rapid clicks.
- Merchant cooldown: a failed/no-shop OCR no longer triggers the full merchant cooldown, so the next eligible cycle retries promptly.
- Glitched buff auto-pop: each potion is now used once (not 3×); priority potions (Xyz → Warp → Heavenly II → Oblivion) pop first; Heavenly/Oblivion keep the original per-potion settle wait (shortened when a Warp is queued).
- Fishing counter: catch and sell counters now increment only when the minigame bar was actually present, eliminating empty sell walks from false bites.

## Discord
- Merchant shop-ping dedup restored — per-merchant shop notifications no longer spam.

## Licensing & updates
- Stable **2.3.5** — the built-in updater on the stable channel offers this release; beta builds stay on their own track.
