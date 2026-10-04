#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
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


def install_support(app: Path, workers: Path, workflows: list[Path], services: Path) -> Path | None:
    support = services / "Service Tools"
    owned = [(app, support / app.name), (workers, support / "Workers")]
    owned.extend((workflow, services / workflow.name) for workflow in workflows)
    existing = [(source, destination) for source, destination in owned if destination.exists()]
    backup = None
    if existing:
        backup = services / "Service Tools Backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        for source, destination in existing:
            relative = destination.relative_to(services)
            shutil.copytree(destination, backup / relative)
    services.mkdir(parents=True, exist_ok=True)
    replace_tree(app, support / app.name)
    # Preserve companion helpers and user-added workers that aren't in this release.
    shutil.copytree(workers, support / "Workers", dirs_exist_ok=True)
    for workflow in workflows:
        replace_tree(workflow, services / workflow.name)
    installed_app = support / app.name
    for attribute in ("com.apple.FinderInfo", "com.apple.ResourceFork"):
        subprocess.run(["xattr", "-dr", attribute, str(installed_app)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(installed_app)], check=True)
    return backup


def main() -> int:
    if sys.platform != "darwin":
        print("Service Tools can only be installed on macOS.", file=sys.stderr)
        return 1
    if not SOURCE_SUPPORT.is_dir() or not SOURCE_WORKFLOWS.is_dir():
        print("The release package is incomplete.", file=sys.stderr)
        return 1

    SERVICES_DIR.mkdir(parents=True, exist_ok=True)
    backup = install_support(SOURCE_SUPPORT / "Service Tools.app", SOURCE_SUPPORT / "Workers",
                             sorted(SOURCE_WORKFLOWS.glob("*.workflow")), SERVICES_DIR)
    if backup:
        print(f"Previous installation backed up in {backup}")

    print(f"Installed Service Tools and Finder Quick Actions in {SERVICES_DIR}")
    print("If Finder does not show the actions immediately, relaunch Finder or enable them in System Settings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
