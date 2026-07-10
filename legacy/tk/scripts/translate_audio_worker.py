from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List


SUPPORTED_EXTENSIONS = {
    ".aac",
    ".aif",
    ".aiff",
    ".flac",
    ".m4a",
    ".m4v",
    ".mov",
    ".mp3",
    ".mp4",
    ".wav",
}


def output_path(input_path: str, suffix: str, ext: str = ".txt") -> str:
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


def load_document_worker_module():
    script_dir = Path(__file__).resolve().parent
    candidates = [
        os.environ.get("TRANSLATE_DOCUMENT_WORKER_SCRIPT"),
        str(script_dir / "translate_document_worker.py"),
        str(script_dir / ".translate_document_worker.py"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            spec = importlib.util.spec_from_file_location("translate_document_worker_for_audio", candidate)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
    raise RuntimeError("translate_document_worker.py was not found; cannot load text translation backends.")


def output_lang_code(lang: str) -> str:
    return load_document_worker_module().output_lang_code(lang)


def source_lang_code_for_text(text: str) -> str:
    return load_document_worker_module().source_lang_code_for_text(text)


def get_text_translator(engine: str):
    return load_document_worker_module().get_translator(engine)


def translate_text(translator, text: str, target_lang: str) -> str:
    module = load_document_worker_module()
    return module.translate_text_block(translator, text, target_lang).strip()


def translate_transcript_bilingual(translator, transcript: str, target_lang: str) -> str:
    module = load_document_worker_module()
    return module.translate_txt_bilingual_interleaved(translator, transcript, target_lang).strip()


def resolve_mw_bin() -> str | None:
    configured = os.environ.get("MACWHISPER_CLI") or os.environ.get("MW_BIN")
    candidates = [
        configured,
        shutil.which("mw"),
        "/usr/local/bin/mw",
        "/opt/homebrew/bin/mw",
    ]
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def clean_transcript(raw_output: str) -> str:
    lines = []
    for line in raw_output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^(Error|OVERVIEW|USAGE|OPTIONS|ARGUMENTS):", stripped):
            continue
        if re.match(r"^Transcribing .+\.\.\.$", stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def transcribe_with_macwhisper(input_path: str, model: str | None = None, stream: bool = False) -> str:
    mw_bin = resolve_mw_bin()
    if not mw_bin:
        raise RuntimeError(
            "MacWhisper CLI was not found. Install it from MacWhisper > Settings > Advanced > Command-Line Tool."
        )
    cmd = [mw_bin, "transcribe", input_path]
    if model:
        cmd.extend(["--model", model])
    if stream:
        cmd.append("--stream")
    print("Running command:", " ".join(cmd))
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = clean_transcript(process.stdout)
    if process.returncode != 0:
        raise RuntimeError(process.stdout.strip() or f"mw transcribe failed with code {process.returncode}")
    if not output:
        raise RuntimeError("mw transcribe completed but returned an empty transcript.")
    return output


def write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.rstrip() + "\n")


def process_audio(
    input_path: str,
    operation: str,
    engine: str,
    target_lang: str,
    mode: str,
    model: str | None,
    stream: bool,
) -> List[str]:
    ext = os.path.splitext(input_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported audio/video type: {input_path}")

    transcript = transcribe_with_macwhisper(input_path, model=model, stream=stream)
    generated: List[str] = []

    if operation in {"transcribe", "both"}:
        transcript_output = output_path(input_path, "_TRANSCRIPT", ".txt")
        write_text(transcript_output, transcript)
        generated.append(transcript_output)

    if operation in {"translate", "both"}:
        translator = get_text_translator(engine)
        source_code = source_lang_code_for_text(transcript)
        target_code = output_lang_code(target_lang)
        if mode in {"mono", "both"}:
            mono_output = output_path(input_path, f"_{target_code}", ".txt")
            translated = translate_text(translator, transcript, target_lang)
            write_text(mono_output, translated)
            generated.append(mono_output)
        if mode in {"dual", "both"}:
            dual_output = output_path(input_path, f"_{source_code}_{target_code}", ".txt")
            bilingual = translate_transcript_bilingual(translator, transcript, target_lang)
            write_text(dual_output, bilingual)
            generated.append(dual_output)

    return generated


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transcribe audio/video with MacWhisper CLI and optionally translate transcript text.")
    parser.add_argument("--operation", choices=["transcribe", "translate", "both"], default="both")
    parser.add_argument("--engine", choices=["google", "bing", "ollama"], default="google")
    parser.add_argument("--lang-out", default="zh")
    parser.add_argument("--mode", choices=["dual", "mono", "both"], default="dual")
    parser.add_argument("--model", default=os.environ.get("MACWHISPER_MODEL"))
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    failed = []
    succeeded = []
    for file_path in args.files:
        print(f"\nProcessing audio: {file_path}")
        if not os.path.exists(file_path):
            print(f"Error: file does not exist: {file_path}")
            failed.append(file_path)
            continue
        try:
            generated = process_audio(
                file_path,
                args.operation,
                args.engine,
                args.lang_out,
                args.mode,
                args.model,
                args.stream,
            )
            succeeded.append((file_path, generated))
            print(f"Success: generated {len(generated)} file(s):")
            for path in generated:
                print(f"  - {path}")
        except Exception as exc:
            failed.append(file_path)
            print(f"Error processing {file_path}: {exc}")

    print("\nAudio Summary:")
    for file_path, generated in succeeded:
        print(f"  OK: {os.path.basename(file_path)}")
        for path in generated:
            print(f"      {os.path.basename(path)}")
    for file_path in failed:
        print(f"  FAILED: {os.path.basename(file_path)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
