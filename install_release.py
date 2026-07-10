#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
SOURCE_SUPPORT = PACKAGE_ROOT / "Service Tools"
SOURCE_WORKFLOWS = PACKAGE_ROOT / "Workflows"
SERVICES_DIR = Path.home() / "Library" / "Services"


def replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def main() -> int:
    if sys.platform != "darwin":
        print("Service Tools can only be installed on macOS.", file=sys.stderr)
        return 1
    if not SOURCE_SUPPORT.is_dir() or not SOURCE_WORKFLOWS.is_dir():
        print("The release package is incomplete.", file=sys.stderr)
        return 1

    SERVICES_DIR.mkdir(parents=True, exist_ok=True)
    replace_tree(SOURCE_SUPPORT, SERVICES_DIR / "Service Tools")
    for workflow in sorted(SOURCE_WORKFLOWS.glob("*.workflow")):
        replace_tree(workflow, SERVICES_DIR / workflow.name)

    print(f"Installed Service Tools and Finder Quick Actions in {SERVICES_DIR}")
    print("If Finder does not show the actions immediately, relaunch Finder or enable them in System Settings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
