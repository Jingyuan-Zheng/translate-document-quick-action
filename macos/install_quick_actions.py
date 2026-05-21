#!/usr/bin/env python3
import os
import plistlib
import shutil
import sys
import uuid
from pathlib import Path
from typing import List, Union


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_SOURCE_DIR = REPO_ROOT / "scripts"
APP_DIR = Path.home() / "Library" / "Application Support" / "TranslateDocumentQuickAction"
SERVICES_DIR = Path.home() / "Library" / "Services"


def copy_scripts() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    for script_name in [
        "translate_document_worker.py",
        "translate_document_gui.py",
        "translate_pdf_gui.py",
        "translate_image_worker.py",
        "translate_image_gui.py",
        "translate_audio_worker.py",
        "translate_audio_gui.py",
    ]:
        shutil.copy2(SCRIPT_SOURCE_DIR / script_name, APP_DIR / script_name)


def workflow_document(command: str, input_type: str) -> dict:
    input_uuid = str(uuid.uuid4()).upper()
    output_uuid = str(uuid.uuid4()).upper()
    action_uuid = str(uuid.uuid4()).upper()
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
                    "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.string"]},
                    "AMActionVersion": "2.0.3",
                    "AMApplication": ["Automator"],
                    "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
                    "BundleIdentifier": "com.apple.RunShellScript",
                    "CanShowSelectedItemsWhenRun": False,
                    "CanShowWhenRun": True,
                    "Category": ["AMCategoryUtilities"],
                    "CFBundleVersion": "2.0.3",
                    "Class Name": "RunShellScriptAction",
                    "InputUUID": input_uuid,
                    "OutputUUID": output_uuid,
                    "UUID": action_uuid,
                    "isViewVisible": 1,
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
            "applicationPath": "/System/Library/CoreServices/Finder.app",
            "inputTypeIdentifier": input_type,
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "processesInput": False,
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
            "serviceInputTypeIdentifier": input_type,
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": False,
            "systemImageName": "NSTouchBarGlobe",
            "useAutomaticInputType": False,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }


def normalize_send_file_types(send_file_types: Union[str, List[str]]) -> List[str]:
    if isinstance(send_file_types, str):
        return [send_file_types]
    return send_file_types


def info_plist(menu_name: str, send_file_types: Union[str, List[str]]) -> dict:
    return {
        "NSServices": [
            {
                "NSBackgroundColorName": "background",
                "NSIconName": "NSTouchBarGlobe",
                "NSMenuItem": {"default": menu_name},
                "NSMessage": "runWorkflowAsService",
                "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
                "NSSendFileTypes": normalize_send_file_types(send_file_types),
            }
        ]
    }


def write_workflow(name: str, menu_name: str, send_file_types: Union[str, List[str]], input_type: str, command: str) -> None:
    contents_dir = SERVICES_DIR / f"{name}.workflow" / "Contents"
    contents_dir.mkdir(parents=True, exist_ok=True)
    with (contents_dir / "Info.plist").open("wb") as handle:
        plistlib.dump(info_plist(menu_name, send_file_types), handle)
    with (contents_dir / "document.wflow").open("wb") as handle:
        plistlib.dump(workflow_document(command, input_type), handle)


def main() -> int:
    if sys.platform != "darwin":
        print("macOS Quick Actions can only be installed on macOS.", file=sys.stderr)
        return 1

    copy_scripts()
    SERVICES_DIR.mkdir(parents=True, exist_ok=True)

    gui_python = os.environ.get("TRANSLATE_DOCUMENT_GUI_PYTHON", sys.executable)
    app_dir = str(APP_DIR)

    document_command = (
        f'APP_DIR="{app_dir}"\n'
        f'PYTHON_BIN="${{TRANSLATE_DOCUMENT_GUI_PYTHON:-{gui_python}}}"\n'
        '"$PYTHON_BIN" "$APP_DIR/translate_document_gui.py" "$@"'
    )
    pdf_command = (
        f'APP_DIR="{app_dir}"\n'
        f'PYTHON_BIN="${{TRANSLATE_DOCUMENT_GUI_PYTHON:-{gui_python}}}"\n'
        '"$PYTHON_BIN" "$APP_DIR/translate_pdf_gui.py" "$@"'
    )
    image_command = (
        f'APP_DIR="{app_dir}"\n'
        f'PYTHON_BIN="${{TRANSLATE_DOCUMENT_GUI_PYTHON:-{gui_python}}}"\n'
        '"$PYTHON_BIN" "$APP_DIR/translate_image_gui.py" "$@"'
    )
    audio_command = (
        f'APP_DIR="{app_dir}"\n'
        f'PYTHON_BIN="${{TRANSLATE_DOCUMENT_GUI_PYTHON:-{gui_python}}}"\n'
        '"$PYTHON_BIN" "$APP_DIR/translate_audio_gui.py" "$@"'
    )

    write_workflow(
        "Translate Document...",
        "Translate Document...",
        ["txt", "md", "markdown", "docx"],
        "com.apple.Automator.fileSystemObject",
        document_command,
    )
    write_workflow(
        "Translate PDF...",
        "Translate PDF...",
        "com.adobe.pdf",
        "com.apple.Automator.fileSystemObject.PDF",
        pdf_command,
    )
    write_workflow(
        "Translate Image...",
        "Translate Image...",
        "public.image",
        "public.image",
        image_command,
    )
    write_workflow(
        "Transcribe Audio...",
        "Transcribe Audio...",
        ["public.audio", "public.movie"],
        "com.apple.Automator.fileSystemObject",
        audio_command,
    )

    print(f"Installed scripts to: {APP_DIR}")
    print(f"Installed Quick Actions to: {SERVICES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
