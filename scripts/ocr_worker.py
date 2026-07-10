#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
TOOL_PATHS = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
]


def worker_env() -> dict[str, str]:
    env = os.environ.copy()
    existing_path = env.get("PATH", "")
    env["PATH"] = ":".join(TOOL_PATHS + ([existing_path] if existing_path else []))
    return env


def find_tool(name: str) -> str | None:
    return shutil.which(name, path=worker_env()["PATH"])


def output_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_OCR.pdf")


def detect_image_dpi(path: Path) -> int:
    try:
        with Image.open(path) as image:
            dpi = image.info.get("dpi", (0, 0))
            if dpi[0] >= 72:
                return int(dpi[0])
            width, height = image.size
            if max(width, height) > 2000:
                return 300
            if max(width, height) > 1000:
                return 200
            return 150
    except Exception:
        return 300


def image_needs_rgb_copy(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            return image.mode in {"RGBA", "LA"} or "transparency" in image.info
    except Exception:
        return False


def make_rgb_image_copy(path: Path, temp_dir: Path) -> Path:
    output = temp_dir / f"{path.stem}_rgb.png"
    with Image.open(path) as image:
        dpi = image.info.get("dpi")
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            background.alpha_composite(rgba)
            rgb = background.convert("RGB")
        else:
            rgb = image.convert("RGB")

        save_kwargs = {}
        if dpi:
            save_kwargs["dpi"] = dpi
        rgb.save(output, **save_kwargs)
    return output


def run_ocr(ocrmypdf: str, path: Path, env: dict[str, str]) -> int:
    destination = output_path(path)
    temp_context = None
    ocr_input = path
    if path.suffix.lower() in IMAGE_EXTENSIONS and image_needs_rgb_copy(path):
        temp_context = tempfile.TemporaryDirectory(prefix="ocr-image-rgb-")
        ocr_input = make_rgb_image_copy(path, Path(temp_context.name))
        print(f"Converted alpha image to RGB temporary input: {ocr_input}", flush=True)

    command = [ocrmypdf, "--force-ocr"]
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        command += ["--image-dpi", str(detect_image_dpi(path))]
    command += [str(ocr_input), str(destination)]

    print(f"OCR: {path}", flush=True)
    print("Running command: " + " ".join(command), flush=True)
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line.rstrip(), flush=True)
        return process.wait()
    finally:
        if temp_context is not None:
            temp_context.cleanup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OCRmyPDF and save *_OCR.pdf files.")
    parser.add_argument("files", nargs="+")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = worker_env()
    ocrmypdf = find_tool("ocrmypdf")
    if not ocrmypdf:
        print("ocrmypdf was not found. Install it with Homebrew first.", flush=True)
        return 1
    if not find_tool("tesseract"):
        print("tesseract was not found. Install it with Homebrew first: brew install tesseract", flush=True)
        return 1

    failures = 0
    for file_name in args.files:
        status = run_ocr(ocrmypdf, Path(file_name), env)
        if status != 0:
            failures += 1
            print(f"Failed with exit code {status}: {file_name}", flush=True)
        else:
            print(f"Created: {output_path(Path(file_name))}", flush=True)

    print("\nOCR Summary:", flush=True)
    print(f"  OK: {len(args.files) - failures}", flush=True)
    print(f"  Failed: {failures}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
