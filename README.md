# Translate Document Quick Action

Translate common documents from Finder or the command line while preserving useful structure.

Supported formats:

- PDF via `pdf2zh-next`
- DOCX with XML in-place translation, preserving the original package structure and media references
- Markdown with common Markdown structure protection
- TXT with line-preserving translation
- Images through a lightweight macOS Vision OCR engine or an optional `manga-image-translator` adapter

Outputs are written next to the input file and never overwrite existing files. Monolingual files use the target language suffix, for example `_CN.docx`; bilingual files use source and target codes, for example `_EN_CN.docx`.

## Status

This project started as a macOS Finder Quick Action, but the core scripts are plain Python.

- macOS: Finder Quick Actions and Tkinter GUI are supported.
- Linux and Windows: the CLI worker can translate TXT, Markdown, and DOCX if Python dependencies are installed. The PDF GUI can run where Tkinter is available and `pdf2zh_next` is on `PATH`. Image translation currently needs macOS Vision OCR or an external image backend.
- Finder integration is macOS-only.

## Install

Install the Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For PDF translation, install `pdf2zh-next` separately:

```bash
uv tool install --python python3.13 "pdf2zh-next==2.6.4" --with "BabelDOC==0.5.16"
```

For image translation, install `manga-image-translator` separately. It is intentionally not vendored here because it is a large GPL-3.0 project with model dependencies.

```bash
git clone https://github.com/zyddnys/manga-image-translator.git
cd manga-image-translator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export MANGA_TRANSLATOR_PYTHON="$PWD/venv/bin/python"
```

For lightweight macOS image OCR, install PyObjC Vision bindings in the Python environment that runs the image worker:

```bash
pip install pyobjc-framework-Vision pyobjc-framework-Quartz pyobjc-framework-AppKit
```

If you want to use the macOS Finder Quick Actions:

```bash
python3 macos/install_quick_actions.py
```

The GUI Python must include Tkinter. If your default Python does not, set:

```bash
export TRANSLATE_DOCUMENT_GUI_PYTHON=/path/to/python-with-tkinter
```

## CLI Usage

Translate TXT, Markdown, and DOCX:

```bash
python3 scripts/translate_document_worker.py --engine google --lang-out zh --mode both file.txt notes.md paper.docx
```

Options:

- `--engine google`: Google mobile web endpoint
- `--engine bing`: Bing web endpoint
- `--engine ollama`: local Ollama chat API
- `--mode mono`: translated-only output
- `--mode dual`: bilingual output
- `--mode both`: generate both

PDF is handled by `pdf2zh-next`:

```bash
pdf2zh_next input.pdf --lang-out zh --translate-table-text --skip-scanned-detection --enhance-compatibility --output . --google
```

Translate images with lightweight macOS Vision OCR:

```bash
python3 scripts/translate_image_worker.py --image-engine simple-macos --text-engine google --lang-in auto --lang-out zh --mode both image.png
```

Translate images through `manga-image-translator`:

```bash
python3 scripts/translate_image_worker.py --image-engine manga --lang-in auto --lang-out zh --mode both --mit-translator offline image.png
```

Image monolingual output is the translated image, for example `_CN.png`. Image bilingual output is a side-by-side image with the original on the left and translated result on the right, for example `_AUTO_CN.png` or `_EN_CN.png` if `--lang-in en` is provided.

## Output Style

TXT and Markdown bilingual output is interleaved:

```text
Original paragraph
Translated paragraph
```

DOCX bilingual output inserts a translated paragraph directly after each original paragraph while keeping the original DOCX media and layout references.

PDF bilingual output uses `pdf2zh-next`'s alternating-page dual PDF mode.

Image bilingual output uses side-by-side composition. With `--image-engine simple-macos`, OCR uses Apple's Vision framework and translated text is rendered back with Pillow. With `--image-engine manga`, OCR, inpainting, rendering, and translated-text placement are delegated to `manga-image-translator`.

## Notes

Google and Bing engines in this project use web endpoints, not official paid APIs. They may be rate limited or change upstream behavior. For sensitive documents, use a local backend such as Ollama or replace the translator adapter with an official API.

DOCX translation preserves media references by modifying Word XML in place. It covers normal body text, headers, footers, footnotes, endnotes, and comments. Very complex Word features such as SmartArt, embedded objects, equations, or unusual text boxes may need additional testing.

`simple-macos` is designed for screenshots, slides, diagrams, and other relatively clean images. It covers source text with a sampled background color and writes translated text into the detected boxes; it is not AI inpainting. For manga, complex backgrounds, or high-quality text removal, use the `manga` engine.

`manga-image-translator` currently disables its Google translator in the public registry, so image translation through the `manga` engine should use one of its supported translators such as `offline`, `custom_openai`, `chatgpt`, `deepl`, or another backend you configure in that project. This repository only wraps its CLI and normalizes output naming.

## License

MIT. This repository does not vendor `pdf2zh-next`, BabelDOC, or other third-party translation projects.
