from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from typing import Iterable


LANGUAGE_OUTPUT_CODES = {
    "auto": "AUTO",
    "zh": "CN",
    "zh-cn": "CN",
    "zh-hans": "CN",
    "zh-tw": "TW",
    "zh-hant": "TW",
    "cn": "CN",
    "en": "EN",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "it": "IT",
    "pt": "PT",
    "ja": "JA",
    "jp": "JA",
    "ko": "KO",
    "kr": "KO",
    "ru": "RU",
}

LATIN_LANGUAGE_HINTS = {
    "DE": {"der", "die", "das", "und", "ist", "nicht", "ein", "eine", "mit", "für", "auf", "ich", "sie", "wir"},
    "FR": {"le", "la", "les", "des", "est", "une", "avec", "pour", "dans", "pas", "nous", "vous", "être"},
    "ES": {"el", "la", "los", "las", "que", "para", "con", "una", "por", "como", "esta", "este", "pero"},
    "IT": {"il", "lo", "la", "gli", "che", "per", "con", "una", "sono", "come", "questo", "questa", "non"},
    "PT": {"que", "para", "com", "uma", "não", "como", "esta", "este", "por", "são", "mais", "foi"},
    "EN": {"the", "and", "that", "with", "this", "for", "you", "are", "not", "have", "will", "from", "they", "was"},
}


def is_pdf2zh_next_compatible(candidate: str) -> bool:
    if not os.path.isfile(candidate) or not os.access(candidate, os.X_OK):
        return False
    if os.path.basename(candidate) == "pdf2zh_next":
        return True
    try:
        process = subprocess.run(
            [candidate, "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return False
    output = process.stdout
    return all(
        option in output
        for option in [
            "--translate-table-text",
            "--skip-scanned-detection",
            "--enhance-compatibility",
        ]
    )


def resolve_pdf2zh_bin() -> str | None:
    configured = os.environ.get("PDF2ZH_NEXT_BIN")
    candidates = [
        configured,
        os.path.expanduser("~/.local/bin/pdf2zh_next"),
        os.path.expanduser("~/.local/share/uv/tools/pdf2zh-next/bin/pdf2zh_next"),
        shutil.which("pdf2zh_next"),
        os.path.expanduser("~/.local/share/uv/tools/pdf2zh-next/bin/pdf2zh"),
        os.path.expanduser("~/.local/bin/pdf2zh"),
        shutil.which("pdf2zh"),
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if is_pdf2zh_next_compatible(candidate):
            return candidate
    return None


def output_lang_code(lang: str) -> str:
    normalized = (lang or "auto").strip().lower().replace("_", "-")
    return LANGUAGE_OUTPUT_CODES.get(normalized, normalized.split("-")[0].upper())


def detect_source_lang_code(text: str) -> str:
    sample = text[:20000]
    if not sample.strip():
        return "AUTO"
    counts = {
        "CN": len(re.findall(r"[\u4e00-\u9fff]", sample)),
        "JA": len(re.findall(r"[\u3040-\u30ff]", sample)),
        "KO": len(re.findall(r"[\uac00-\ud7af]", sample)),
        "RU": len(re.findall(r"[\u0400-\u04ff]", sample)),
    }
    lang, count = max(counts.items(), key=lambda item: item[1])
    if count >= 5:
        return lang
    words = re.findall(r"[a-zA-ZÀ-ÿ]+", sample.lower())
    if not words:
        return "AUTO"
    word_counts = {code: sum(1 for word in words if word in hints) for code, hints in LATIN_LANGUAGE_HINTS.items()}
    lang, count = max(word_counts.items(), key=lambda item: item[1])
    if count > 0:
        return lang
    return "EN"


def extract_pdf_text(file_path: str) -> str:
    try:
        import fitz

        text_parts: list[str] = []
        with fitz.open(file_path) as document:
            for page in document[: min(5, document.page_count)]:
                text_parts.append(page.get_text("text"))
        return "\n".join(text_parts)
    except Exception:
        return ""


def output_path(input_path: str, suffix: str, ext: str = ".pdf") -> str:
    directory = os.path.dirname(input_path) or "."
    base = os.path.splitext(os.path.basename(input_path))[0]
    candidate = os.path.join(directory, f"{base}{suffix}{ext}")
    if not os.path.exists(candidate):
        return candidate
    index = 1
    while True:
        candidate = os.path.join(directory, f"{base}{suffix}.{index}{ext}")
        if not os.path.exists(candidate):
            return candidate
        index += 1


def translate_pdf(pdf2zh_bin: str, file_path: str, engine: str, target_language: str, mode: str) -> list[str]:
    output_dir = os.path.dirname(file_path) or "."
    base_name = os.path.splitext(os.path.basename(file_path))[0]

    source_code = detect_source_lang_code(extract_pdf_text(file_path))
    target_code = output_lang_code(target_language)
    dual_output = output_path(file_path, f"_{source_code}_{target_code}", ".pdf")
    mono_output = output_path(file_path, f"_{target_code}", ".pdf")

    cmd = [
        pdf2zh_bin,
        file_path,
        "--lang-out",
        target_language,
        "--translate-table-text",
        "--skip-scanned-detection",
        "--enhance-compatibility",
        "--output",
        output_dir,
    ]
    if engine == "google":
        cmd.append("--google")
    elif engine == "bing":
        cmd.append("--bing")

    print(f"\nTranslating PDF: {file_path}", flush=True)
    print("Running command:", " ".join(cmd), flush=True)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    full_output: list[str] = []
    for line in process.stdout:
        full_output.append(line)
        print(line.rstrip(), flush=True)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"pdf2zh exited with code {return_code}")

    generated_files: list[str] = []
    possible_dual_files = [
        os.path.join(output_dir, f"{base_name}.no_watermark.{target_language}.dual.pdf"),
        os.path.join(output_dir, f"{base_name}.dual.pdf"),
        dual_output,
    ]
    possible_mono_files = [
        os.path.join(output_dir, f"{base_name}.no_watermark.{target_language}.mono.pdf"),
        os.path.join(output_dir, f"{base_name}.mono.pdf"),
        mono_output,
    ]

    if mode in {"dual", "both"}:
        for path in possible_dual_files:
            if os.path.exists(path):
                if path != dual_output:
                    os.rename(path, dual_output)
                    print(f"Renamed {os.path.basename(path)} to {os.path.basename(dual_output)}", flush=True)
                generated_files.append(dual_output)
                break

    if mode in {"mono", "both"}:
        for path in possible_mono_files:
            if os.path.exists(path):
                if path != mono_output:
                    os.rename(path, mono_output)
                    print(f"Renamed {os.path.basename(path)} to {os.path.basename(mono_output)}", flush=True)
                generated_files.append(mono_output)
                break

    if not generated_files:
        print("Command output:", flush=True)
        print("".join(full_output), flush=True)
        raise RuntimeError(f"No output files generated for {file_path}")

    print(f"Success: generated {len(generated_files)} file(s):", flush=True)
    for path in generated_files:
        print(f"  - {path}", flush=True)
    return generated_files


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Translate PDFs with pdf2zh-next.")
    parser.add_argument("--engine", choices=["google", "bing"], default="google")
    parser.add_argument("--lang-out", default="zh")
    parser.add_argument("--mode", choices=["dual", "mono", "both"], default="both")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    pdf2zh_bin = resolve_pdf2zh_bin()
    if not pdf2zh_bin:
        print("Error: pdf2zh_next was not found. Install pdf2zh-next or set PDF2ZH_NEXT_BIN.", flush=True)
        return 1

    failed: list[str] = []
    succeeded: list[tuple[str, list[str]]] = []
    for file_path in args.files:
        if not os.path.exists(file_path):
            print(f"Error: file does not exist: {file_path}", flush=True)
            failed.append(file_path)
            continue
        try:
            generated = translate_pdf(pdf2zh_bin, file_path, args.engine, args.lang_out, args.mode)
            succeeded.append((file_path, generated))
        except Exception as exc:
            failed.append(file_path)
            print(f"Error translating {file_path}: {exc}", flush=True)

    print("\nPDF Translation Summary:", flush=True)
    for file_path, generated in succeeded:
        print(f"  OK: {os.path.basename(file_path)}", flush=True)
        for path in generated:
            print(f"      {os.path.basename(path)}", flush=True)
    for file_path in failed:
        print(f"  FAILED: {os.path.basename(file_path)}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
