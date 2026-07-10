# Translate Document Quick Action

A native macOS utility app and Finder Quick Action collection for translating documents, PDFs, and images, transcribing audio or video, resizing images, and creating searchable PDFs.

The current release uses one Swift/AppKit application for every tool. Successful OCR runs stay out of the way, failures open the shared log window, and translated files are written next to the originals without overwriting existing output.

## Included Quick Actions

- **Translate PDF...** — translate PDFs with `pdf2zh-next`.
- **Translate Document...** — translate TXT, Markdown, and DOCX files with Google, Bing, or Ollama.
- **Translate Image...** — use macOS Vision OCR or `manga-image-translator`, then translate detected text.
- **Transcribe Audio...** — transcribe audio or video with the MacWhisper CLI and optionally translate the transcript.
- **Resize Image** — resize, optimize, or convert images with ImageMagick.
- **OCR PDF...** and **OCR Image...** — create searchable PDFs with OCRmyPDF and Tesseract.

TXT and Markdown bilingual output is interleaved. DOCX translation modifies Word XML while preserving package structure and media references. Image bilingual output places the original and translated image side by side. Output names include language or operation suffixes and automatically gain `_2`, `_3`, and later suffixes when necessary.

## Requirements

- macOS 13 or later.
- Xcode Command Line Tools (`swiftc`).
- Python 3.10 or later.
- Python packages from `requirements.txt`.

Install the shared Python packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional tool-specific dependencies:

```bash
# PDF translation
uv tool install --python python3.13 "pdf2zh-next==2.6.4" --with "BabelDOC==0.5.16"

# Resize, optimize, and convert images
brew install imagemagick

# OCR
brew install ocrmypdf tesseract

# Lightweight image translation with Apple Vision
pip install pyobjc-framework-Vision pyobjc-framework-Quartz pyobjc-framework-AppKit
```

Audio transcription requires MacWhisper 13.20 or later with its command-line tool enabled in `MacWhisper > Settings > Advanced > Command-Line Tool`. Image translation can optionally call a separately installed [`manga-image-translator`](https://github.com/zyddnys/manga-image-translator).

## Build and Install

Build the app, worker bundle, and Finder workflows:

```bash
python3 build_service_tools.py
```

Generated artifacts are placed in `dist/`. To build and install them for the current user:

```bash
python3 build_service_tools.py --install
```

Ready-to-inspect XML versions of every Finder workflow are committed under `workflows/`. Maintainers can refresh them from the same definitions used by the builder:

```bash
python3 build_service_tools.py --export-workflows
```

The installer writes only the named Quick Actions from this project and the following support directory:

```text
~/Library/Services/Service Tools/
```

The application finds its `Workers` directory relative to its own bundle. Generated workflows use `$HOME`, so the repository contains no user-specific absolute path. If the workers should run with a Python interpreter other than the first standard executable found, set:

```bash
export TRANSLATION_TOOLS_PYTHON=/path/to/python3
```

Before contributing or publishing a build, run the source and privacy checks:

```bash
python3 -m compileall -q build_service_tools.py scripts legacy/tk
python3 -m unittest discover -s tests
python3 build_service_tools.py --export-workflows
```

## Command-Line Usage

The Python workers can also be called directly. For example:

```bash
python3 scripts/translate_document_worker.py \
  --engine google --lang-out zh --mode both notes.md report.docx

python3 scripts/translation_pdf_worker.py \
  --engine google --lang-out zh --mode both paper.pdf

python3 scripts/translate_image_worker.py \
  --image-engine simple-macos --text-engine google \
  --lang-in auto --lang-out zh --mode both image.png

python3 scripts/translate_audio_worker.py \
  --operation both --engine google --lang-out zh --mode dual interview.m4a
```

Google and Bing modes use public web endpoints rather than paid official APIs and may be rate-limited or changed upstream. Use Ollama or replace the adapter with an official API for sensitive documents.

## Repository Layout

```text
app/Sources/TranslationTools.swift   Native macOS interface
scripts/                             Current Python workers
build_service_tools.py               Reproducible app and workflow builder
workflows/                            Reviewable Finder Quick Action bundles
legacy/tk/                           Archived pre-Swift Tk implementation
docs/images/                         Output examples
```

The archived Tk release remains available under [`legacy/tk`](legacy/tk/README.md). It is retained for reference and for users who need its standalone Python GUIs, but new development targets the native Swift application.

## Preview

**TXT output**

![TXT translation output](docs/images/txt-output.png)

**Markdown bilingual output**

![Markdown bilingual output](docs/images/markdown-bilingual.png)

**DOCX bilingual output**

![DOCX bilingual output](docs/images/docx-bilingual.png)

**PDF bilingual output**

![PDF bilingual output](docs/images/pdf-bilingual.png)

**Image bilingual output**

![Image bilingual output](docs/images/image-bilingual.png)

## License

MIT. This repository does not vendor `pdf2zh-next`, BabelDOC, OCRmyPDF, Tesseract, ImageMagick, MacWhisper, or `manga-image-translator`.
