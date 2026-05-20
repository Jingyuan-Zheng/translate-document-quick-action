# Translate Document Quick Action

Translate common documents from Finder or the command line while preserving useful structure.

Supported formats:

- PDF via `pdf2zh-next`
- DOCX with XML in-place translation, preserving the original package structure and media references
- Markdown with common Markdown structure protection
- TXT with line-preserving translation

Outputs are written next to the input file and never overwrite existing files. Monolingual files use the target language suffix, for example `_CN.docx`; bilingual files use source and target codes, for example `_EN_CN.docx`.

## Status

This project started as a macOS Finder Quick Action, but the core scripts are plain Python.

- macOS: Finder Quick Actions and Tkinter GUI are supported.
- Linux and Windows: the CLI worker can translate TXT, Markdown, and DOCX if Python dependencies are installed. The PDF GUI can run where Tkinter is available and `pdf2zh_next` is on `PATH`.
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

## Output Style

TXT and Markdown bilingual output is interleaved:

```text
Original paragraph
Translated paragraph
```

DOCX bilingual output inserts a translated paragraph directly after each original paragraph while keeping the original DOCX media and layout references.

PDF bilingual output uses `pdf2zh-next`'s alternating-page dual PDF mode.

## Notes

Google and Bing engines in this project use web endpoints, not official paid APIs. They may be rate limited or change upstream behavior. For sensitive documents, use a local backend such as Ollama or replace the translator adapter with an official API.

DOCX translation preserves media references by modifying Word XML in place. It covers normal body text, headers, footers, footnotes, endnotes, and comments. Very complex Word features such as SmartArt, embedded objects, equations, or unusual text boxes may need additional testing.

## License

MIT. This repository does not vendor `pdf2zh-next`, BabelDOC, or other third-party translation projects.
