"""Copy blossom artwork and build Windows .ico for the app and PyInstaller."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "_blossom_source.png"

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Source image missing: {SOURCE}")

    img = Image.open(SOURCE).convert("RGBA")
    ASSETS.mkdir(parents=True, exist_ok=True)

    for name in ("blossom.png", "icon.png"):
        dest = ASSETS / name
        img.save(dest, format="PNG", optimize=True)
        print(f"wrote {dest}")

    ico_path = ASSETS / "icon.ico"
    master = img.resize((256, 256), Image.Resampling.LANCZOS)
    master.save(
        ico_path,
        format="ICO",
        sizes=[(size, size) for size in ICO_SIZES],
    )
    print(f"wrote {ico_path} ({ico_path.stat().st_size} bytes)")

    # Root + legacy names (PyInstaller spec uses ROOT/icon.ico for the .exe)
    for dest in (ROOT / "icon.ico", ASSETS / "blossom_icon.ico"):
        shutil.copy2(ico_path, dest)
        print(f"wrote {dest}")


if __name__ == "__main__":
    main()
