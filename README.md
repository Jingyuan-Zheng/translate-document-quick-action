# Translate Document Quick Action

Translate common documents from Finder or the command line while preserving useful structure.

Supported formats:

- PDF via `pdf2zh-next`
- DOCX with XML in-place translation, preserving the original package structure and media references
- Markdown with common Markdown structure protection
- TXT with line-preserving translation
- Images through an optional `manga-image-translator` adapter

Outputs are written next to the input file and never overwrite existing files. Monolingual files use the target language suffix, for example `_CN.docx`; bilingual files use source and target codes, for example `_EN_CN.docx`.

## Status

This project started as a macOS Finder Quick Action, but the core scripts are plain Python.

- macOS: Finder Quick Actions and Tkinter GUI are supported.
- Linux and Windows: the CLI worker can translate TXT, Markdown, DOCX, and images if Python dependencies are installed. The PDF and image GUIs can run where Tkinter is available and the external backends are installed.
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

Translate images through `manga-image-translator`:

```bash
python3 scripts/translate_image_worker.py --lang-in auto --lang-out zh --mode both --mit-translator offline image.png
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

Image bilingual output uses side-by-side composition. The actual OCR, inpainting, rendering, and translated-text placement are delegated to `manga-image-translator`.

## Notes

Google and Bing engines in this project use web endpoints, not official paid APIs. They may be rate limited or change upstream behavior. For sensitive documents, use a local backend such as Ollama or replace the translator adapter with an official API.

DOCX translation preserves media references by modifying Word XML in place. It covers normal body text, headers, footers, footnotes, endnotes, and comments. Very complex Word features such as SmartArt, embedded objects, equations, or unusual text boxes may need additional testing.

`manga-image-translator` currently disables its Google translator in the public registry, so image translation should use one of its supported translators such as `offline`, `custom_openai`, `chatgpt`, `deepl`, or another backend you configure in that project. This repository only wraps its CLI and normalizes output naming.

## License

MIT. This repository does not vendor `pdf2zh-next`, BabelDOC, or other third-party translation projects.
