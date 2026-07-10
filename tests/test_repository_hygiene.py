from __future__ import annotations

import plistlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIPPED_PARTS = {".git", ".venv", "__pycache__", "build", "dist"}
TEXT_SUFFIXES = {".md", ".py", ".swift", ".txt", ".yml", ".yaml", ".json", ".plist"}
PRIVATE_MARKERS = (
    "/" + "Users/",
    "/" + "Volumes/",
    "/opt/" + "anaconda",
    "Documents/" + "Codex",
    "MacBook" + "-Air.local",
)


def public_text_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in TEXT_SUFFIXES
        and not SKIPPED_PARTS.intersection(path.relative_to(ROOT).parts)
    ]


class RepositoryHygieneTests(unittest.TestCase):
    def test_public_files_do_not_contain_private_machine_paths(self) -> None:
        violations: list[str] = []
        for path in public_text_files():
            text = path.read_text(encoding="utf-8")
            for marker in PRIVATE_MARKERS:
                if marker in text:
                    violations.append(f"{path.relative_to(ROOT)} contains {marker!r}")
        self.assertEqual([], violations, "\n".join(violations))

    def test_native_app_locates_workers_relative_to_bundle(self) -> None:
        source = (ROOT / "app" / "Sources" / "TranslationTools.swift").read_text(encoding="utf-8")
        self.assertIn("Bundle.main.bundleURL.deletingLastPathComponent()", source)
        self.assertNotIn("/" + "Users/", source)

    def test_workflows_use_portable_home_directory(self) -> None:
        workflow_files = sorted((ROOT / "workflows").glob("*.workflow/Contents/document.wflow"))
        self.assertEqual(7, len(workflow_files))
        for workflow_file in workflow_files:
            with workflow_file.open("rb") as file:
                workflow = plistlib.load(file)
            command = workflow["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"]
            self.assertIn("$HOME/Library/Services/Service Tools/Service Tools.app", command)
            self.assertNotIn("/" + "Users/", command)


if __name__ == "__main__":
    unittest.main()
