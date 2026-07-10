#!/usr/bin/env python3
from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT / "app"
SOURCE = APP_ROOT / "Sources" / "TranslationTools.swift"
SCRIPTS = ROOT / "scripts"
BUILD_DIR = ROOT / "build"
OUTPUTS = ROOT / "dist"
WORKFLOW_SOURCES = ROOT / "workflows"
APP_BUNDLE = OUTPUTS / "Service Tools.app"
WORKERS_OUTPUT = OUTPUTS / "Service Tools" / "Workers"
EXECUTABLE_NAME = "TranslationTools"

SERVICES_DIR = Path.home() / "Library" / "Services"
SERVICE_TOOLS_DIR = SERVICES_DIR / "Service Tools"
SERVICES_APP_SHELL_PATH = "$HOME/Library/Services/Service Tools/Service Tools.app"


WORKFLOWS = [
    {
        "bundle": "Translate PDF...",
        "menu": "Translate PDF...",
        "types": ["com.adobe.pdf"],
        "icon": "NSTouchBarGlobe",
        "tool": "pdf",
    },
    {
        "bundle": "Translate Document...",
        "menu": "Translate Document...",
        "types": ["txt", "md", "markdown", "docx"],
        "icon": "NSTouchBarGlobe",
        "tool": "document",
    },
    {
        "bundle": "Translate Image...",
        "menu": "Translate Image...",
        "types": ["public.image"],
        "icon": "NSTouchBarGlobe",
        "tool": "image",
    },
    {
        "bundle": "Transcribe Audio...",
        "menu": "Transcribe Audio...",
        "types": ["public.audio", "public.movie"],
        "icon": "NSTouchBarAudioInput",
        "tool": "audio",
    },
    {
        "bundle": "Resize Image",
        "menu": "Resize Image",
        "types": ["public.image"],
        "icon": "NSTouchBarCrop",
        "tool": "resize",
        "input_type": "com.apple.Automator.fileSystemObject.image",
    },
    {
        "bundle": "OCR PDF...",
        "menu": "OCR PDF...",
        "types": ["com.adobe.pdf"],
        "icon": "NSTouchBarTextBox",
        "tool": "ocr",
        "input_type": "com.apple.Automator.fileSystemObject.PDF",
    },
    {
        "bundle": "OCR Image...",
        "menu": "OCR Image...",
        "types": ["public.image"],
        "icon": "NSTouchBarTextBox",
        "tool": "ocr",
        "input_type": "com.apple.Automator.fileSystemObject.image",
    },
]


def run_shell_action(command: str, input_type: str, icon: str) -> dict:
    return {
        "actions": [
            {
                "action": {
                    "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
                    "ActionName": "Run Shell Script",
                    "ActionParameters": {
                        "CheckedForUserDefaultShell": True,
                        "COMMAND_STRING": command,
                        "inputMethod": 1,
                        "shell": "/bin/zsh",
                        "source": "",
                    },
                    "AMAccepts": {
                        "Container": "List",
                        "Optional": True,
                        "Types": ["com.apple.cocoa.string"],
                    },
                    "AMActionVersion": "2.0.3",
                    "AMApplication": ["Automator"],
                    "AMParameterProperties": {
                        "CheckedForUserDefaultShell": {},
                        "COMMAND_STRING": {},
                        "inputMethod": {},
                        "shell": {},
                        "source": {},
                    },
                    "AMProvides": {
                        "Container": "List",
                        "Types": ["com.apple.cocoa.string"],
                    },
                    "arguments": {
                        "0": {"default value": 0, "name": "inputMethod", "required": "0", "type": "0", "uuid": "0"},
                        "1": {"default value": False, "name": "CheckedForUserDefaultShell", "required": "0", "type": "0", "uuid": "1"},
                        "2": {"default value": "", "name": "source", "required": "0", "type": "0", "uuid": "2"},
                        "3": {"default value": "", "name": "COMMAND_STRING", "required": "0", "type": "0", "uuid": "3"},
                        "4": {"default value": "/bin/sh", "name": "shell", "required": "0", "type": "0", "uuid": "4"},
                    },
                    "BundleIdentifier": "com.apple.RunShellScript",
                    "CanShowSelectedItemsWhenRun": False,
                    "CanShowWhenRun": True,
                    "Category": ["AMCategoryUtilities"],
                    "CFBundleVersion": "2.0.3",
                    "Class Name": "RunShellScriptAction",
                    "isViewVisible": 1,
                    "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
                    "location": "720.000000:305.000000",
                    "nibPath": "/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib",
                    "UnlocalizedApplications": ["Automator"],
                },
                "isViewVisible": 1,
            }
        ],
        "AMApplicationBuild": "528",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleID": "com.apple.finder",
            "applicationBundleIDsByPath": {"/System/Library/CoreServices/Finder.app": "com.apple.finder"},
            "applicationPath": "/System/Library/CoreServices/Finder.app",
            "applicationPaths": ["/System/Library/CoreServices/Finder.app"],
            "inputTypeIdentifier": input_type,
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "processesInput": False,
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
            "serviceInputTypeIdentifier": input_type,
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": False,
            "systemImageName": icon,
            "useAutomaticInputType": False,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }


def info_plist(menu_name: str, types: list[str], icon: str) -> dict:
    return {
        "NSServices": [
            {
                "NSBackgroundColorName": "background",
                "NSIconName": icon,
                "NSMenuItem": {"default": menu_name},
                "NSMessage": "runWorkflowAsService",
                "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
                "NSSendFileTypes": types,
            }
        ]
    }


def build_app() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    (BUILD_DIR / "module-cache").mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    binary = BUILD_DIR / EXECUTABLE_NAME
    subprocess.run(
        [
            "swiftc",
            "-O",
            "-module-cache-path",
            str(BUILD_DIR / "module-cache"),
            "-framework",
            "AppKit",
            str(SOURCE),
            "-o",
            str(binary),
        ],
        check=True,
    )

    if APP_BUNDLE.exists():
        shutil.rmtree(APP_BUNDLE)
    macos_dir = APP_BUNDLE / "Contents" / "MacOS"
    resources_dir = APP_BUNDLE / "Contents" / "Resources"
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)
    shutil.copy2(binary, macos_dir / EXECUTABLE_NAME)

    info = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleExecutable": EXECUTABLE_NAME,
        "CFBundleIdentifier": "io.github.translate-document-quick-action.service-tools",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "Service Tools",
        "CFBundleDisplayName": "Service Tools",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    }
    with (APP_BUNDLE / "Contents" / "Info.plist").open("wb") as file:
        plistlib.dump(info, file, sort_keys=False)


def build_workflows() -> None:
    for workflow in WORKFLOWS:
        bundle = OUTPUTS / f"{workflow['bundle']}.workflow"
        contents = bundle / "Contents"
        if bundle.exists():
            shutil.rmtree(bundle)
        contents.mkdir(parents=True)

        command = f'/usr/bin/open -n "{SERVICES_APP_SHELL_PATH}" --args --tool {workflow["tool"]} -- "$@"'
        input_type = {
            "pdf": "com.apple.Automator.fileSystemObject.PDF",
            "document": "com.apple.Automator.fileSystemObject",
            "image": "com.apple.Automator.fileSystemObject.image",
            "audio": "com.apple.Automator.fileSystemObject",
            "resize": "com.apple.Automator.fileSystemObject.image",
            "ocr": "com.apple.Automator.fileSystemObject",
        }[workflow["tool"]]
        input_type = workflow.get("input_type", input_type)

        with (contents / "Info.plist").open("wb") as file:
            plistlib.dump(info_plist(workflow["menu"], workflow["types"], workflow["icon"]), file, sort_keys=False)
        with (contents / "document.wflow").open("wb") as file:
            plistlib.dump(run_shell_action(command, input_type, workflow["icon"]), file, sort_keys=False)


def build() -> None:
    build_app()
    if WORKERS_OUTPUT.exists():
        shutil.rmtree(WORKERS_OUTPUT)
    WORKERS_OUTPUT.mkdir(parents=True)
    for script in SCRIPTS.glob("*.py"):
        shutil.copy2(script, WORKERS_OUTPUT / script.name)
    build_workflows()


def replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def install() -> None:
    SERVICE_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    replace_tree(APP_BUNDLE, SERVICE_TOOLS_DIR / APP_BUNDLE.name)
    replace_tree(WORKERS_OUTPUT, SERVICE_TOOLS_DIR / "Workers")
    for workflow in WORKFLOWS:
        name = f"{workflow['bundle']}.workflow"
        replace_tree(OUTPUTS / name, SERVICES_DIR / name)


def export_workflows() -> None:
    WORKFLOW_SOURCES.mkdir(parents=True, exist_ok=True)
    for workflow in WORKFLOWS:
        name = f"{workflow['bundle']}.workflow"
        destination = WORKFLOW_SOURCES / name
        replace_tree(OUTPUTS / name, destination)
        for plist_path in (destination / "Contents" / "Info.plist", destination / "Contents" / "document.wflow"):
            with plist_path.open("rb") as file:
                value = plistlib.load(file)
            with plist_path.open("wb") as file:
                plistlib.dump(value, file, fmt=plistlib.FMT_XML, sort_keys=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Service Tools app and Finder Quick Actions.")
    parser.add_argument(
        "--install",
        action="store_true",
        help="install the generated app, workers, and Quick Actions into ~/Library/Services",
    )
    parser.add_argument(
        "--export-workflows",
        action="store_true",
        help="refresh the reviewable XML workflow bundles stored under workflows/",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build()
    print(f"Built Service Tools in {OUTPUTS}")
    if args.export_workflows:
        export_workflows()
        print(f"Exported reviewable workflows to {WORKFLOW_SOURCES}")
    if args.install:
        install()
        print(f"Installed Service Tools in {SERVICES_DIR}")


if __name__ == "__main__":
    main()
