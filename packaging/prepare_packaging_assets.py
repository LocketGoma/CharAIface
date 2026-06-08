from __future__ import annotations

import argparse
import shutil
from pathlib import Path

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare assets for PyInstaller packaging."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    target = args.target.resolve()

    if not source.exists():
        raise FileNotFoundError(f"Source asset directory not found: {source}")

    if target.exists():
        shutil.rmtree(target)

    shutil.copytree(source, target)

    print(f"[CharAIface] Prepared packaging assets: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
