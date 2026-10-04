from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import signal
import tempfile
from pathlib import Path

from pdf_translation_bridge import BackendServer, DEFAULT_MODEL
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


def _translate_pdf(pdf2zh_bin: str, file_path: str, engine: str, target_language: str, mode: str, cli_command: str, output_dir: str) -> list[str]:
    base_name = os.path.splitext(os.path.basename(file_path))[0]

    source_code = detect_source_lang_code(extract_pdf_text(file_path))
    target_code = output_lang_code(target_language)

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
    cmd += ["--clitranslator", "--clitranslator-command", cli_command,
            "--clitranslator-timeout", "300", "--qps", "1" if engine in {"cloud", "google", "bing", "deepl"} else "20", "--pool-max-workers", "1",
            "--lang-in", {"CN": "zh", "TW": "zh-Hant", "AUTO": "en"}.get(source_code, source_code.lower())]
    if mode == "mono":
        cmd.append("--no-dual")
    elif mode == "dual":
        cmd.append("--no-mono")

    print(f"\nTranslating PDF: {file_path}", flush=True)
    print(f"Running PDF translation with {engine} → {target_language} ({mode}).", flush=True)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    assert process.stdout is not None
    full_output: list[str] = []
    try:
        for line in process.stdout:
            full_output.append(line)
            print(line.rstrip(), flush=True)
        return_code = process.wait()
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
    if return_code != 0:
        raise RuntimeError(f"pdf2zh exited with code {return_code}")

    selected: list[tuple[str, str]] = []
    for kind, suffix in [("dual", f"_{source_code}_{target_code}"), ("mono", f"_{target_code}")]:
        if mode not in {kind, "both"}:
            continue
        candidates = [
            os.path.join(output_dir, f"{base_name}.no_watermark.{target_language}.{kind}.pdf"),
            os.path.join(output_dir, f"{base_name}.{kind}.pdf"),
        ]
        found = next((path for path in candidates if os.path.isfile(path)), None)
        if found:
            selected.append((found, suffix))
    expected_count = 2 if mode == "both" else 1
    if len(selected) != expected_count:
        raise RuntimeError(f"Expected {expected_count} output files, found {len(selected)} for {file_path}")

    generated_files: list[str] = []
    for source_path, suffix in selected:
        # Reserve the final name atomically, including when two workflows run.
        while True:
            destination = output_path(file_path, suffix)
            try:
                output_file = open(destination, "xb")
                break
            except FileExistsError:
                continue
        try:
            with output_file, open(source_path, "rb") as input_file:
                shutil.copyfileobj(input_file, output_file)
            shutil.copystat(source_path, destination)
        except BaseException:
            os.unlink(destination)
            raise
        generated_files.append(destination)

    print(f"Success: generated {len(generated_files)} file(s):", flush=True)
    for path in generated_files:
        print(f"  - {path}", flush=True)
    return generated_files


def translate_pdf(pdf2zh_bin: str, file_path: str, engine: str, target_language: str, mode: str, model: str = DEFAULT_MODEL) -> list[str]:
    source = detect_source_lang_code(extract_pdf_text(file_path))
    source = {"CN": "zh", "TW": "zh-Hant", "AUTO": "en"}.get(source, source.lower())
    target = {"zh-cn": "zh", "zh-hans": "zh", "zh-tw": "zh-Hant"}.get(target_language.lower(), target_language)
    # A new output directory prevents old PDFs from being mistaken for success.
    with tempfile.TemporaryDirectory(prefix="pdf-translation-") as directory:
        with BackendServer(engine, source, target, model) as server:
            return _translate_pdf(pdf2zh_bin, file_path, engine, target_language, mode, server.command(), directory)


def _terminate(signum, _frame):
    raise SystemExit(128 + signum)


def main(argv: Iterable[str] | None = None) -> int:
    signal.signal(signal.SIGTERM, _terminate)
    parser = argparse.ArgumentParser(description="Translate PDFs with pdf2zh-next.")
    parser.add_argument("--engine", choices=["apple", "gemma", "cloud", "google", "bing", "deepl"], default="apple")
    parser.add_argument("--lang-out", default="zh")
    parser.add_argument("--mode", choices=["dual", "mono", "both"], default="both")
    parser.add_argument("--model", default=os.environ.get("TRANSLATE_TEXT_MODEL", DEFAULT_MODEL))
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
            generated = translate_pdf(pdf2zh_bin, file_path, args.engine, args.lang_out, args.mode, args.model)
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
