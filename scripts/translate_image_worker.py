from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
LANGUAGE_OUTPUT_CODES = {
    "auto": "AUTO",
    "zh": "CN",
    "zh-cn": "CN",
    "zh-hans": "CN",
    "zh-tw": "TW",
    "zh-hant": "TW",
    "cn": "CN",
    "en": "EN",
    "ja": "JA",
    "jp": "JA",
    "ko": "KO",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "it": "IT",
    "pt": "PT",
    "ru": "RU",
}
MANGA_TRANSLATOR_LANG_CODES = {
    "zh": "CHS",
    "zh-cn": "CHS",
    "zh-hans": "CHS",
    "zh-tw": "CHT",
    "zh-hant": "CHT",
    "cn": "CHS",
    "en": "ENG",
    "ja": "JPN",
    "jp": "JPN",
    "ko": "KOR",
    "de": "DEU",
    "fr": "FRA",
    "es": "ESP",
    "it": "ITA",
    "pt": "PTB",
    "ru": "RUS",
}


def output_lang_code(lang: str) -> str:
    normalized = (lang or "auto").strip().lower().replace("_", "-")
    return LANGUAGE_OUTPUT_CODES.get(normalized, normalized.split("-")[0].upper())


def manga_translator_lang_code(lang: str) -> str:
    normalized = (lang or "zh").strip().lower().replace("_", "-")
    return MANGA_TRANSLATOR_LANG_CODES.get(normalized, normalized.upper())


def output_path(input_path: str, suffix: str, ext: str | None = None) -> str:
    directory = os.path.dirname(input_path) or "."
    base, original_ext = os.path.splitext(os.path.basename(input_path))
    ext = ext or original_ext
    candidate = os.path.join(directory, f"{base}{suffix}{ext}")
    if not os.path.exists(candidate):
        return candidate
    index = 1
    while True:
        candidate = os.path.join(directory, f"{base}{suffix}.{index}{ext}")
        if not os.path.exists(candidate):
            return candidate
        index += 1


def resolve_manga_translator_python() -> str:
    return os.environ.get("MANGA_TRANSLATOR_PYTHON", sys.executable)


def verify_manga_translator_available(python_bin: str) -> None:
    process = subprocess.run(
        [python_bin, "-m", "manga_translator", "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode != 0:
        raise RuntimeError(
            "manga-image-translator is not available in this Python environment. "
            "Install it separately and set MANGA_TRANSLATOR_PYTHON to its venv Python."
        )


def run_manga_translator(
    input_path: str,
    translated_output: str,
    target_lang: str,
    translator_name: str,
    use_gpu: bool,
    extra_args: List[str],
) -> None:
    python_bin = resolve_manga_translator_python()
    verify_manga_translator_available(python_bin)
    output_ext = os.path.splitext(translated_output)[1].lstrip(".").lower()
    cmd = [
        python_bin,
        "-m",
        "manga_translator",
        "local",
        "-v",
        "-i",
        input_path,
        "-o",
        translated_output,
        "-f",
        output_ext,
        "--overwrite",
        "--translator",
        translator_name,
        "--target-lang",
        manga_translator_lang_code(target_lang),
        *extra_args,
    ]
    if use_gpu:
        cmd.insert(3, "--use-gpu")
    print("Running command:", " ".join(cmd))
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(process.stdout)
    if process.returncode != 0:
        raise RuntimeError(f"manga-image-translator failed with code {process.returncode}")
    if not os.path.exists(translated_output):
        raise RuntimeError(f"manga-image-translator did not create expected output: {translated_output}")


def make_side_by_side(original_path: str, translated_path: str, output_path_value: str) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for image bilingual side-by-side output. Install requirements.txt.") from exc

    with Image.open(original_path) as original_image, Image.open(translated_path) as translated_image:
        original = original_image.convert("RGB")
        translated = translated_image.convert("RGB")
        target_height = max(original.height, translated.height)

        def resize_to_height(image: Image.Image) -> Image.Image:
            if image.height == target_height:
                return image
            width = round(image.width * target_height / image.height)
            return image.resize((width, target_height), Image.Resampling.LANCZOS)

        original = resize_to_height(original)
        translated = resize_to_height(translated)
        gap = max(16, round(target_height * 0.02))
        canvas = Image.new("RGB", (original.width + gap + translated.width, target_height), "white")
        canvas.paste(original, (0, 0))
        canvas.paste(translated, (original.width + gap, 0))
        output_ext = os.path.splitext(output_path_value)[1].lower()
        save_kwargs = {"quality": 95} if output_ext in {".jpg", ".jpeg", ".webp"} else {}
        canvas.save(output_path_value, **save_kwargs)


def translate_image(
    input_path: str,
    target_lang: str,
    source_lang: str,
    mode: str,
    translator_name: str,
    use_gpu: bool,
    extra_args: List[str],
) -> List[str]:
    ext = os.path.splitext(input_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image type: {input_path}")

    generated: List[str] = []
    target_code = output_lang_code(target_lang)
    source_code = output_lang_code(source_lang)
    mono_output = output_path(input_path, f"_{target_code}", ext)
    dual_output = output_path(input_path, f"_{source_code}_{target_code}", ext)

    if mode in {"mono", "both"}:
        translated_output = mono_output
    else:
        temp_dir = tempfile.mkdtemp(prefix="translate-image-")
        translated_output = os.path.join(temp_dir, f"{Path(input_path).stem}_{target_code}{ext}")

    try:
        run_manga_translator(input_path, translated_output, target_lang, translator_name, use_gpu, extra_args)
        if mode in {"mono", "both"}:
            generated.append(mono_output)
        if mode in {"dual", "both"}:
            make_side_by_side(input_path, translated_output, dual_output)
            generated.append(dual_output)
    finally:
        if mode == "dual":
            shutil.rmtree(os.path.dirname(translated_output), ignore_errors=True)
    return generated


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Translate images through manga-image-translator.")
    parser.add_argument("--lang-in", default="auto")
    parser.add_argument("--lang-out", default="zh")
    parser.add_argument("--mode", choices=["dual", "mono", "both"], default="both")
    parser.add_argument("--mit-translator", default=os.environ.get("MANGA_TRANSLATOR_BACKEND", "offline"))
    parser.add_argument("--use-gpu", action="store_true")
    parser.add_argument("--mit-arg", action="append", default=[], help="Extra argument passed to manga_translator.")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    failed = []
    succeeded = []
    for file_path in args.files:
        print(f"\nTranslating image: {file_path}")
        if not os.path.exists(file_path):
            print(f"Error: file does not exist: {file_path}")
            failed.append(file_path)
            continue
        try:
            generated = translate_image(
                file_path,
                args.lang_out,
                args.lang_in,
                args.mode,
                args.mit_translator,
                args.use_gpu,
                args.mit_arg,
            )
            succeeded.append((file_path, generated))
            print(f"Success: generated {len(generated)} file(s):")
            for path in generated:
                print(f"  - {path}")
        except Exception as exc:
            failed.append(file_path)
            print(f"Error translating {file_path}: {exc}")

    print("\nTranslation Summary:")
    for file_path, generated in succeeded:
        print(f"  OK: {os.path.basename(file_path)}")
        for path in generated:
            print(f"      {os.path.basename(path)}")
    for file_path in failed:
        print(f"  FAILED: {os.path.basename(file_path)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
