# Blossom 2.3.6

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
- Stable **2.3.6** — the built-in updater on the stable channel offers this release; beta builds stay on their own track.
