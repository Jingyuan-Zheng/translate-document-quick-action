#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import platform
import tempfile
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
APP_BUNDLE = OUTPUTS / "Service Tools" / "Service Tools.app"
WORKERS_OUTPUT = OUTPUTS / "Service Tools" / "Workers"
EXECUTABLE_NAME = "TranslationTools"
VERSION = "2.1.0"
BUILD_NUMBER = "3"
RELEASE_INSTALLER = ROOT / "install_release.py"

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
            "-target", f"{platform.machine()}-apple-macos13.0",
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
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": BUILD_NUMBER,
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    }
    with (APP_BUNDLE / "Contents" / "Info.plist").open("wb") as file:
        plistlib.dump(info, file, sort_keys=False)


def sign_app(bundle: Path) -> None:
    # Sign outside File Provider folders, which can re-add Finder metadata while
    # codesign is running. ZIP archives carry the signed bytes, not those attrs.
    with tempfile.TemporaryDirectory(prefix="service-tools-sign-") as directory:
        staged = Path(directory) / bundle.name
        shutil.copytree(bundle, staged)
        subprocess.run(["xattr", "-cr", str(staged)], check=True)
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(staged)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(staged)], check=True)
        shutil.copytree(staged, bundle, dirs_exist_ok=True)


def build_apple_helper() -> None:
    bundle = APP_BUNDLE / "Contents" / "Helpers" / "Apple PDF Translator.app"
    macos = bundle / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    subprocess.run([
        "swiftc", "-O", "-target", f"{platform.machine()}-apple-macos15.0", "-module-cache-path", str(BUILD_DIR / "module-cache"),
        "-framework", "AppKit", "-framework", "SwiftUI", "-framework", "Translation",
        str(APP_ROOT / "Sources" / "ApplePDFTranslator.swift"),
        "-o", str(macos / "ApplePDFTranslator"),
    ], check=True)
    info = {
        "CFBundleExecutable": "ApplePDFTranslator",
        "CFBundleIdentifier": "io.github.translate-document-quick-action.service-tools.apple-pdf-translator",
        "CFBundleName": "Apple PDF Translator",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": VERSION, "CFBundleVersion": BUILD_NUMBER,
        "LSMinimumSystemVersion": "15.0", "LSUIElement": True,
        "NSPrincipalClass": "NSApplication",
    }
    with (bundle / "Contents" / "Info.plist").open("wb") as file:
        plistlib.dump(info, file)
    subprocess.run(["xattr", "-cr", str(APP_BUNDLE)], check=True)
    sign_app(APP_BUNDLE)


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
    build_apple_helper()
    if WORKERS_OUTPUT.exists():
        shutil.rmtree(WORKERS_OUTPUT)
    WORKERS_OUTPUT.mkdir(parents=True)
    shutil.copytree(SCRIPTS, WORKERS_OUTPUT, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    build_workflows()


def replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def install() -> None:
    from install_release import install_support
    backup = install_support(APP_BUNDLE, WORKERS_OUTPUT,
                             [OUTPUTS / f"{workflow['bundle']}.workflow" for workflow in WORKFLOWS],
                             SERVICES_DIR)
    if backup:
        print(f"Previous installation backed up in {backup}")


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_release(release_root: Path) -> tuple[Path, Path]:
    package_name = f"Translate-Document-Quick-Action-v{VERSION}"
    package_dir = release_root / package_name
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)

    support_dir = package_dir / "Service Tools"
    support_dir.mkdir()
    shutil.copytree(APP_BUNDLE, support_dir / APP_BUNDLE.name)
    shutil.copytree(WORKERS_OUTPUT, support_dir / "Workers")

    workflow_dir = package_dir / "Workflows"
    workflow_dir.mkdir()
    for workflow in WORKFLOWS:
        name = f"{workflow['bundle']}.workflow"
        shutil.copytree(OUTPUTS / name, workflow_dir / name)

    shutil.copy2(RELEASE_INSTALLER, package_dir / "install.py")
    (package_dir / "README.txt").write_text(
        f"Translate Document Quick Action v{VERSION}\n\n"
        "Run `python3 install.py` from this folder to install Service Tools and all Finder Quick Actions.\n\n"
        "This binary release is ad-hoc signed, not Apple-notarized. If macOS blocks the app after download, "
        "review the source and build locally, or remove quarantine from the installed Service Tools.app.\n"
        "External dependencies are not bundled. See the project README for requirements.\n",
        encoding="utf-8",
    )

    packaged_app = support_dir / APP_BUNDLE.name
    if shutil.which("codesign"):
        sign_app(packaged_app)
        subprocess.run(["xattr", "-cr", str(packaged_app)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(packaged_app)], check=True)

    archive_base = release_root / package_name
    archive_path = Path(
        shutil.make_archive(str(archive_base), "zip", root_dir=release_root, base_dir=package_name)
    )
    checksum_path = release_root / "SHA256SUMS.txt"
    checksum_path.write_text(f"{sha256(archive_path)}  {archive_path.name}\n", encoding="utf-8")
    return archive_path, checksum_path


def package_release() -> tuple[Path, Path]:
    release_root = OUTPUTS / "releases"
    release_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="service-tools-package-") as directory:
        archive, checksum = _package_release(Path(directory))
        paths = (release_root / archive.name, release_root / checksum.name)
        shutil.copyfile(archive, paths[0])
        shutil.copyfile(checksum, paths[1])
    return paths


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
    parser.add_argument(
        "--package-release",
        action="store_true",
        help="create a versioned, ad-hoc-signed release archive and SHA-256 checksum",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build()
    print(f"Built Service Tools in {OUTPUTS}")
    if args.export_workflows:
        export_workflows()
        print(f"Exported reviewable workflows to {WORKFLOW_SOURCES}")
    if args.package_release:
        archive, checksum = package_release()
        print(f"Packaged release archive: {archive}")
        print(f"Wrote release checksum: {checksum}")
    if args.install:
        install()
        print(f"Installed Service Tools in {SERVICES_DIR}")


if __name__ == "__main__":
    main()
