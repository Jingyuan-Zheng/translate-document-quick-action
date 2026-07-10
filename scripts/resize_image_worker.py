#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


TOOL_PATHS = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
]

FORMAT_EXTENSIONS = {
    "original": None,
    "jpg": ".jpg",
    "jpeg": ".jpg",
    "png": ".png",
    "webp": ".webp",
    "avif": ".avif",
    "heic": ".heic",
    "tiff": ".tiff",
}

LOSSY_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".webp",
    ".heic",
    ".heif",
    ".avif",
}


def worker_env() -> dict[str, str]:
    env = os.environ.copy()
    existing_path = env.get("PATH", "")
    env["PATH"] = ":".join(TOOL_PATHS + ([existing_path] if existing_path else []))
    return env


def find_tool(name: str) -> str | None:
    return shutil.which(name, path=worker_env()["PATH"])


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def target_size(path: Path, args: argparse.Namespace) -> tuple[int, int] | None:
    original_width, original_height = image_size(path)

    if args.operation == "optimize":
        return None

    if args.mode == "percentage":
        percentage = float(args.percentage)
        if percentage <= 0:
            raise ValueError("Percentage must be greater than zero.")
        width = max(1, int(original_width * percentage / 100))
        height = max(1, int(original_height * percentage / 100))
        return width, height

    target_width = int(args.width)
    target_height = int(args.height)
    if target_width <= 0 or target_height <= 0:
        raise ValueError("Width and height must be greater than zero.")
    if args.preserve_aspect:
        scale = min(target_width / original_width, target_height / original_height)
        width = max(1, int(original_width * scale))
        height = max(1, int(original_height * scale))
    else:
        width = target_width
        height = target_height
    return width, height


def output_extension(path: Path, output_format: str) -> str:
    requested = output_format.lower()
    if requested == "original":
        return path.suffix
    if requested not in FORMAT_EXTENSIONS:
        raise ValueError(f"Unsupported output format: {output_format}")
    return FORMAT_EXTENSIONS[requested] or path.suffix


def output_path(path: Path, args: argparse.Namespace, size: tuple[int, int] | None) -> Path:
    extension = output_extension(path, args.format)
    format_label = args.format.lower()
    is_original_format = format_label == "original"
    if is_original_format:
        format_label = path.suffix.lstrip(".").lower() or "image"

    if args.operation == "optimize":
        base = f"{path.stem}_optimized"
    elif size is not None:
        width, height = size
        base = f"{path.stem}_{width}x{height}"
    else:
        base = f"{path.stem}_converted"

    if not is_original_format:
        base = f"{base}_{format_label}"

    candidate = path.with_name(f"{base}{extension}")
    suffix = 2
    while candidate.exists():
        candidate = path.with_name(f"{base}_{suffix}{extension}")
        suffix += 1
    return candidate


def magick_format_prefix(path: Path) -> str:
    extension = path.suffix.lower().lstrip(".")
    if extension == "jpg":
        return "jpeg"
    return extension


def effective_quality(args: argparse.Namespace) -> int:
    if args.quality is not None:
        return int(args.quality)
    return 85 if args.operation == "optimize" else 92


def run_magick(magick: str, path: Path, destination: Path, args: argparse.Namespace, size: tuple[int, int] | None) -> None:
    command = [magick, str(path)]
    destination_extension = destination.suffix.lower()

    if args.auto_orient:
        command += ["-auto-orient"]

    if destination_extension in {".jpg", ".jpeg"}:
        command += ["-background", "white", "-alpha", "remove", "-alpha", "off"]

    if size is not None:
        width, height = size
        if args.preserve_aspect:
            command += ["-resize", f"{width}x{height}"]
        else:
            command += ["-resize", f"{width}x{height}!"]

    command += ["-strip"]

    if destination_extension in LOSSY_EXTENSIONS:
        quality = effective_quality(args)
        if not (1 <= quality <= 100):
            raise ValueError("Quality must be between 1 and 100.")
        command += ["-quality", str(quality)]
    elif destination_extension == ".png":
        command += [
            "-define", "png:compression-level=9",
            "-define", "png:compression-strategy=1",
        ]

    output = str(destination)
    if args.format.lower() != "original":
        output = f"{magick_format_prefix(destination)}:{destination}"
    command.append(output)

    print("Running command: " + " ".join(command), flush=True)
    subprocess.run(command, check=True, env=worker_env())


def process_one(magick: str, path: Path, args: argparse.Namespace) -> Path:
    size = target_size(path, args)
    destination = output_path(path, args, size)
    run_magick(magick, path, destination, args, size)
    return destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resize or optimize images with ImageMagick.")
    parser.add_argument("--operation", choices=["resize", "optimize"], default="resize")
    parser.add_argument("--mode", choices=["percentage", "custom"], default="percentage")
    parser.add_argument("--percentage", default="50")
    parser.add_argument("--width", default="1024")
    parser.add_argument("--height", default="1024")
    parser.add_argument("--preserve-aspect", action="store_true")
    parser.add_argument("--format", choices=sorted(FORMAT_EXTENSIONS), default="original")
    parser.add_argument("--quality", type=int, default=None)
    parser.add_argument("--auto-orient", action="store_true", default=True)
    parser.add_argument("files", nargs="+")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    magick = find_tool("magick")
    if not magick:
        print("ImageMagick was not found. Install it with Homebrew: brew install imagemagick", flush=True)
        return 1

    failures: list[tuple[str, str]] = []
    outputs: list[Path] = []

    for file_name in args.files:
        path = Path(file_name)
        try:
            action = "Optimizing" if args.operation == "optimize" else "Resizing"
            print(f"{action}: {path}", flush=True)
            output = process_one(magick, path, args)
            outputs.append(output)
            print(f"Created: {output}", flush=True)
        except subprocess.CalledProcessError as exc:
            failures.append((file_name, f"ImageMagick failed with exit code {exc.returncode}"))
            print(f"Failed: {file_name}: ImageMagick failed with exit code {exc.returncode}", flush=True)
        except Exception as exc:
            failures.append((file_name, str(exc)))
            print(f"Failed: {file_name}: {exc}", flush=True)

    print("\nResize Summary:", flush=True)
    for output in outputs:
        print(f"  OK: {output.name}", flush=True)
    for file_name, reason in failures:
        print(f"  Failed: {os.path.basename(file_name)} - {reason}", flush=True)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
