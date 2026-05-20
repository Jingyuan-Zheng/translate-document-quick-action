from __future__ import annotations

import argparse
import importlib.util
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from statistics import median
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
VISION_LANG_CODES = {
    "auto": ["zh-Hans", "zh-Hant", "en-US", "ja-JP", "ko-KR"],
    "zh": ["zh-Hans", "zh-Hant"],
    "zh-cn": ["zh-Hans"],
    "zh-hans": ["zh-Hans"],
    "zh-tw": ["zh-Hant"],
    "zh-hant": ["zh-Hant"],
    "cn": ["zh-Hans"],
    "en": ["en-US"],
    "ja": ["ja-JP"],
    "jp": ["ja-JP"],
    "ko": ["ko-KR"],
    "de": ["de-DE"],
    "fr": ["fr-FR"],
    "es": ["es-ES"],
    "it": ["it-IT"],
    "pt": ["pt-BR", "pt-PT"],
    "ru": ["ru-RU"],
}


def output_lang_code(lang: str) -> str:
    normalized = (lang or "auto").strip().lower().replace("_", "-")
    return LANGUAGE_OUTPUT_CODES.get(normalized, normalized.split("-")[0].upper())


def manga_translator_lang_code(lang: str) -> str:
    normalized = (lang or "zh").strip().lower().replace("_", "-")
    return MANGA_TRANSLATOR_LANG_CODES.get(normalized, normalized.upper())


def vision_lang_codes(lang: str) -> List[str]:
    normalized = (lang or "auto").strip().lower().replace("_", "-")
    return VISION_LANG_CODES.get(normalized, [])


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


def image_output_paths(input_path: str, source_code: str, target_code: str, ext: str) -> tuple[str, str]:
    directory = os.path.dirname(input_path) or "."
    base = os.path.splitext(os.path.basename(input_path))[0]
    source_suffix = f"_{source_code}"
    if source_code != "AUTO" and base.upper().endswith(source_suffix):
        base = base[: -len(source_suffix)]
    mono_input = os.path.join(directory, base + ext)
    return output_path(mono_input, f"_{target_code}", ext), output_path(mono_input, f"_{source_code}_{target_code}", ext)


def load_document_worker_module():
    script_dir = Path(__file__).resolve().parent
    candidates = [
        os.environ.get("TRANSLATE_DOCUMENT_WORKER_SCRIPT"),
        str(script_dir / "translate_document_worker.py"),
        str(script_dir / ".translate_document_worker.py"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            spec = importlib.util.spec_from_file_location("translate_document_worker_for_image", candidate)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
    raise RuntimeError("translate_document_worker.py was not found; cannot load text translation backends.")


def get_text_translator(engine: str):
    return load_document_worker_module().get_translator(engine)


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


def recognize_text_macos_vision(input_path: str, source_lang: str) -> List[dict]:
    if sys.platform != "darwin":
        raise RuntimeError("simple-macos image OCR is only available on macOS.")

    try:
        import Quartz
        import Vision
        from Foundation import NSURL
    except ImportError as exc:
        raise RuntimeError(
            "simple-macos requires PyObjC Vision bindings. Install "
            "pyobjc-framework-Vision pyobjc-framework-Quartz pyobjc-framework-AppKit."
        ) from exc

    observations: List[dict] = []

    def completion_handler(request, error):
        if error is not None:
            raise RuntimeError(error)
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if not candidates:
                continue
            candidate = candidates[0]
            text = str(candidate.string()).strip()
            if not text:
                continue
            box = observation.boundingBox()
            observations.append(
                {
                    "text": text,
                    "confidence": float(candidate.confidence()),
                    "box": (float(box.origin.x), float(box.origin.y), float(box.size.width), float(box.size.height)),
                }
            )

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(completion_handler)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    languages = vision_lang_codes(source_lang)
    if languages:
        request.setRecognitionLanguages_(languages)

    url = NSURL.fileURLWithPath_(os.path.abspath(input_path))
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(error or "Vision OCR failed")
    return observations


def normalized_box_to_pixels(box: tuple[float, float, float, float], width: int, height: int, padding: int = 4) -> tuple[int, int, int, int]:
    x, y, box_width, box_height = box
    left = round(x * width) - padding
    top = round((1 - y - box_height) * height) - padding
    right = round((x + box_width) * width) + padding
    bottom = round((1 - y) * height) + padding
    return max(0, left), max(0, top), min(width, right), min(height, bottom)


def median_background_color(image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    try:
        import numpy as np
    except ImportError:
        return (255, 255, 255)

    left, top, right, bottom = box
    width, height = image.size
    pad = max(3, round(min(width, height) * 0.005))
    sample_box = (
        max(0, left - pad),
        max(0, top - pad),
        min(width, right + pad),
        min(height, bottom + pad),
    )
    crop = np.asarray(image.crop(sample_box).convert("RGB"))
    if crop.size == 0:
        return (255, 255, 255)
    pixels = crop.reshape(-1, 3)
    color = [int(median(int(value) for value in pixels[:, channel])) for channel in range(3)]
    return tuple(color)


def contrasting_text_color(background: tuple[int, int, int]) -> tuple[int, int, int]:
    brightness = (background[0] * 299 + background[1] * 587 + background[2] * 114) / 1000
    return (0, 0, 0) if brightness > 145 else (255, 255, 255)


def find_font_path() -> str | None:
    configured = os.environ.get("TRANSLATE_IMAGE_FONT")
    candidates = [
        configured,
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def wrapped_lines(draw, text: str, font, max_width: int) -> List[str]:
    words = re.split(r"(\s+)", text)
    if len(words) == 1:
        words = list(text)
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = current + word
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
            continue
        lines.append(current.rstrip())
        current = word.lstrip()
    if current:
        lines.append(current.rstrip())
    return lines


def fit_text(draw, text: str, box: tuple[int, int, int, int], font_path: str | None):
    from PIL import ImageFont

    left, top, right, bottom = box
    max_width = max(12, right - left - 8)
    max_height = max(12, bottom - top - 8)
    start_size = min(max(12, round(max_height * 0.65)), 42)
    min_size = 8
    for size in range(start_size, min_size - 1, -1):
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        lines = wrapped_lines(draw, text, font, max_width)
        line_heights = [draw.textbbox((0, 0), line or " ", font=font)[3] for line in lines]
        total_height = sum(line_heights) + max(0, len(lines) - 1) * round(size * 0.25)
        if total_height <= max_height:
            return font, lines, total_height
    font = ImageFont.truetype(font_path, min_size) if font_path else ImageFont.load_default()
    lines = wrapped_lines(draw, text, font, max_width)[: max(1, max_height // min_size)]
    total_height = len(lines) * min_size
    return font, lines, total_height


def draw_translated_regions(input_path: str, output_path_value: str, regions: List[dict], translator, target_lang: str) -> int:
    from PIL import Image, ImageDraw

    with Image.open(input_path) as image:
        canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font_path = find_font_path()
    cache = {}
    updated_count = 0
    for region in regions:
        original = region["text"]
        if original not in cache:
            cache[original] = translator.translate_with_retry(original, "auto", target_lang)
        translated = html.unescape(cache[original]).strip()
        if not translated:
            continue
        box = normalized_box_to_pixels(region["box"], canvas.width, canvas.height)
        background = median_background_color(canvas, box)
        text_color = contrasting_text_color(background)
        draw.rounded_rectangle(box, radius=4, fill=background)
        font, lines, total_height = fit_text(draw, translated, box, font_path)
        left, top, right, bottom = box
        y = top + max(2, ((bottom - top) - total_height) // 2)
        for line in lines:
            text_box = draw.textbbox((0, 0), line, font=font)
            x = left + max(3, ((right - left) - (text_box[2] - text_box[0])) // 2)
            draw.text((x, y), line, fill=text_color, font=font)
            y += (text_box[3] - text_box[1]) + max(2, round(getattr(font, "size", 12) * 0.25))
        updated_count += 1

    output_ext = os.path.splitext(output_path_value)[1].lower()
    save_kwargs = {"quality": 95} if output_ext in {".jpg", ".jpeg", ".webp"} else {}
    canvas.save(output_path_value, **save_kwargs)
    return updated_count


def run_simple_macos_translator(
    input_path: str,
    translated_output: str,
    source_lang: str,
    target_lang: str,
    text_engine: str,
) -> None:
    translator = get_text_translator(text_engine)
    regions = recognize_text_macos_vision(input_path, source_lang)
    if not regions:
        shutil.copy2(input_path, translated_output)
        print("No OCR text found; copied original image.")
        return
    updated_count = draw_translated_regions(input_path, translated_output, regions, translator, target_lang)
    print(f"simple-macos translated {updated_count} OCR region(s).")


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
    image_engine: str,
    text_engine: str,
    manga_translator_name: str,
    use_gpu: bool,
    extra_args: List[str],
) -> List[str]:
    ext = os.path.splitext(input_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image type: {input_path}")

    generated: List[str] = []
    target_code = output_lang_code(target_lang)
    source_code = output_lang_code(source_lang)
    mono_output, dual_output = image_output_paths(input_path, source_code, target_code, ext)

    if mode in {"mono", "both"}:
        translated_output = mono_output
    else:
        temp_dir = tempfile.mkdtemp(prefix="translate-image-")
        translated_output = os.path.join(temp_dir, f"{Path(input_path).stem}_{target_code}{ext}")

    try:
        if image_engine == "simple-macos":
            run_simple_macos_translator(input_path, translated_output, source_lang, target_lang, text_engine)
        elif image_engine == "manga":
            run_manga_translator(input_path, translated_output, target_lang, manga_translator_name, use_gpu, extra_args)
        else:
            raise ValueError(f"Unsupported image engine: {image_engine}")
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
    parser = argparse.ArgumentParser(description="Translate images with macOS Vision OCR or manga-image-translator.")
    parser.add_argument("--lang-in", default="auto")
    parser.add_argument("--lang-out", default="zh")
    parser.add_argument("--mode", choices=["dual", "mono", "both"], default="both")
    parser.add_argument("--image-engine", choices=["simple-macos", "manga"], default=os.environ.get("TRANSLATE_IMAGE_ENGINE", "simple-macos"))
    parser.add_argument("--text-engine", choices=["google", "bing", "ollama"], default=os.environ.get("TRANSLATE_IMAGE_TEXT_ENGINE", "google"))
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
                args.image_engine,
                args.text_engine,
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
