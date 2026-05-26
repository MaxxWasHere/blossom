import argparse
import subprocess
import sys
from pathlib import Path

ASSET_NAME = "CoteabMacro.exe"
ROOT = Path(__file__).resolve().parent


def run_executable(exe_path: Path) -> None:
    subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))


def run_local_ui() -> int:
    from run_local_ui import main as launch_local_ui

    return launch_local_ui()


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch Coteab Macro or the local UI preview.")
    parser.add_argument(
        "--exe",
        action="store_true",
        help="Launch CoteabMacro.exe instead of the edited local UI preview.",
    )
    args = parser.parse_args()

    if not args.exe:
        print("Launching local UI preview from assets/index.html")
        print("Use --exe if you want the packaged CoteabMacro.exe instead.")
        return run_local_ui()

    output_path = ROOT / ASSET_NAME
    if not output_path.exists():
        print(f"{ASSET_NAME} was not found in {output_path.parent}")
        print(f"Put your existing {ASSET_NAME} in this folder, then run: py biome_activity_source.py --exe")
        return 1

    try:
        run_executable(output_path)
    except OSError as error:
        print(f"Failed to run {ASSET_NAME}: {error}")
        return 1

    print(f"Launched packaged app: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
