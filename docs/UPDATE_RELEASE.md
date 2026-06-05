# Releases and auto-update

Build overview: [`RELEASE_AND_BUILD.md`](RELEASE_AND_BUILD.md).

## Version numbers

Edit in [`src/blossom_updater.py`](../src/blossom_updater.py) and matching rows in [`scripts/build_all.py`](../scripts/build_all.py):

| Channel | Constant |
|---------|----------|
| Stable | `STABLE_VERSION` |
| Beta | `BETA_VERSION` |

## Build

Output is always `Blossom-{version}.exe`. Upload to GitHub as-is.

```powershell
py scripts/build_all.py all --stable-version 1.5.5 -o dist/1.5.5
```

Close running Blossom before building if PyInstaller hits PermissionError.

## GitHub releases

**Stable** — normal release on [MaxxWasHere/blossom](https://github.com/MaxxWasHere/blossom/releases), upload `Blossom-{version}.exe`.

**Beta** — pre-release on [MaxxWasHere/blossombeta](https://github.com/MaxxWasHere/blossombeta/releases), upload `Blossom-{version}.exe`.

Legacy `BlossomMacro.exe` still works as an updater fallback.

## Auto-update

Each exe checks only its own channel (`src/blossom_build_info.py` at build time).

- Stable → Blossom `/releases/latest`, newest `Blossom-*.exe` without `beta` in the name
- Beta → blossombeta `/releases/latest`, newest `Blossom-*beta*.exe`

User data in `%LOCALAPPDATA%\Blossom\` is untouched by updates.

## Dev mode

`py run_local_ui.py` uses `src/blossom_build_info.py` (default beta dev label in sidebar). To mimic stable locally, set `BUILD_CHANNEL = "stable"` and `APP_VERSION` there. Source runs open the releases page instead of auto-installing.
