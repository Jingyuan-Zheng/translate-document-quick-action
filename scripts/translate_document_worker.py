import argparse
import copy
import html
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from typing import Dict, Iterable, List

import requests


SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".docx"}
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")
LANGUAGE_NAMES = {
    "zh": "Simplified Chinese",
    "zh-cn": "Simplified Chinese",
    "zh-tw": "Traditional Chinese",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "uk": "Ukrainian",
    "pl": "Polish",
    "nl": "Dutch",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "tr": "Turkish",
    "ar": "Arabic",
    "he": "Hebrew",
    "el": "Greek",
}
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
    "uk": "UK",
    "pl": "PL",
    "nl": "NL",
    "sv": "SV",
    "no": "NO",
    "da": "DA",
    "fi": "FI",
    "tr": "TR",
    "ar": "AR",
    "he": "HE",
    "el": "EL",
}
LATIN_LANGUAGE_HINTS = {
    "DE": {
        "der",
        "die",
        "das",
        "und",
        "ist",
        "nicht",
        "ein",
        "eine",
        "mit",
        "für",
        "auf",
        "ich",
        "sie",
        "wir",
        "werden",
    },
    "FR": {
        "le",
        "la",
        "les",
        "des",
        "est",
        "une",
        "avec",
        "pour",
        "dans",
        "pas",
        "nous",
        "vous",
        "être",
        "cette",
    },
    "ES": {
        "el",
        "la",
        "los",
        "las",
        "que",
        "para",
        "con",
        "una",
        "por",
        "como",
        "esta",
        "este",
        "pero",
        "son",
    },
    "IT": {
        "il",
        "lo",
        "la",
        "gli",
        "che",
        "per",
        "con",
        "una",
        "sono",
        "come",
        "questo",
        "questa",
        "non",
    },
    "PT": {
        "que",
        "para",
        "com",
        "uma",
        "não",
        "como",
        "esta",
        "este",
        "por",
        "são",
        "mais",
        "foi",
    },
    "EN": {
        "the",
        "and",
        "that",
        "with",
        "this",
        "for",
        "you",
        "are",
        "not",
        "have",
        "will",
        "from",
        "they",
        "was",
    },
}


def remove_control_characters(value: str) -> str:
    return "".join(ch for ch in value if ch in "\n\r\t" or unicodedata.category(ch)[0] != "C")


def target_for_google(lang: str) -> str:
    return {"zh": "zh-CN", "zh-cn": "zh-CN", "zh-tw": "zh-TW"}.get(lang.lower(), lang)


def target_for_bing(lang: str) -> str:
    return {"zh": "zh-Hans", "zh-cn": "zh-Hans", "zh-tw": "zh-Hant"}.get(lang.lower(), lang)


def output_lang_code(lang: str) -> str:
    normalized = (lang or "auto").strip().lower().replace("_", "-")
    return LANGUAGE_OUTPUT_CODES.get(normalized, normalized.split("-")[0].upper())


def count_chars(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text))


def detect_source_lang_code(text: str, fallback: str = "auto") -> str:
    sample = text[:20000]
    if not sample.strip():
        return output_lang_code(fallback)

    counts = {
        "CN": count_chars(r"[\u4e00-\u9fff]", sample),
        "JA": count_chars(r"[\u3040-\u30ff]", sample),
        "KO": count_chars(r"[\uac00-\ud7af]", sample),
        "RU": count_chars(r"[\u0400-\u04ff]", sample),
        "EL": count_chars(r"[\u0370-\u03ff]", sample),
        "AR": count_chars(r"[\u0600-\u06ff]", sample),
        "HE": count_chars(r"[\u0590-\u05ff]", sample),
    }
    lang, count = max(counts.items(), key=lambda item: item[1])
    if count >= 5:
        return lang

    lowered_words = re.findall(r"[a-zA-ZÀ-ÿ]+", sample.lower())
    if not lowered_words:
        return output_lang_code(fallback)
    word_counts = {code: sum(1 for word in lowered_words if word in hints) for code, hints in LATIN_LANGUAGE_HINTS.items()}
    lang, count = max(word_counts.items(), key=lambda item: item[1])
    if count > 0:
        return lang

    if re.search(r"[äöüß]", sample, re.IGNORECASE):
        return "DE"
    if re.search(r"[àâçéèêëîïôùûüÿœ]", sample, re.IGNORECASE):
        return "FR"
    if re.search(r"[áéíñóúü¿¡]", sample, re.IGNORECASE):
        return "ES"
    return "EN"


def source_lang_code_for_text(content: str) -> str:
    return detect_source_lang_code(content)


def source_lang_code_for_docx(input_path: str) -> str:
    try:
        with zipfile.ZipFile(input_path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        return "AUTO"
    text = re.sub(r"<[^>]+>", " ", xml)
    return detect_source_lang_code(html.unescape(text))


def docx_xml_part_names(names: List[str]) -> List[str]:
    patterns = [
        r"word/document\.xml$",
        r"word/header\d+\.xml$",
        r"word/footer\d+\.xml$",
        r"word/footnotes\.xml$",
        r"word/endnotes\.xml$",
        r"word/comments\.xml$",
    ]
    return [name for name in names if any(re.match(pattern, name) for pattern in patterns)]


class BaseTranslator:
    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        raise NotImplementedError

    def translate_with_retry(self, text: str, source_lang: str, target_lang: str, attempts: int = 5) -> str:
        if not text or not text.strip():
            return text
        last_exc = None
        for attempt in range(attempts):
            try:
                return self.translate(text, source_lang, target_lang)
            except Exception as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"translation failed after {attempts} attempts: {last_exc}")


class GoogleMobileTranslator(BaseTranslator):
    def __init__(self):
        self.session = requests.Session()
        self.endpoint = "https://translate.google.com/m"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }

    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        text = text[:5000]
        response = self.session.get(
            self.endpoint,
            params={"tl": target_for_google(target_lang), "sl": source_lang or "auto", "q": text},
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        matches = re.findall(r'(?s)class="(?:t0|result-container)">(.*?)<', response.text)
        if not matches:
            raise RuntimeError("Google response did not contain a translation result")
        return remove_control_characters(html.unescape(matches[0]))


class BingWebTranslator(BaseTranslator):
    def __init__(self):
        self.session = requests.Session()
        self.endpoint = "https://www.bing.com/translator"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
        }

    def find_sid(self):
        response = self.session.get(self.endpoint, headers=self.headers, timeout=30)
        response.raise_for_status()
        url = response.url[:-10]
        ig = re.findall(r'"ig":"(.*?)"', response.text)[0]
        iid = re.findall(r'data-iid="(.*?)"', response.text)[-1]
        key, token = re.findall(r"params_AbusePreventionHelper\s=\s\[(.*?),\"(.*?)\",", response.text)[0]
        return url, ig, iid, key, token

    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        text = text[:1000]
        url, ig, iid, key, token = self.find_sid()
        from_lang = "en" if source_lang == "auto" else source_lang
        response = self.session.post(
            f"{url}ttranslatev3?IG={ig}&IID={iid}",
            data={
                "fromLang": from_lang,
                "to": target_for_bing(target_lang),
                "text": text,
                "token": token,
                "key": key,
            },
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()[0]["translations"][0]["text"]


class OllamaTranslator(BaseTranslator):
    def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        target_name = LANGUAGE_NAMES.get(target_lang.lower(), target_lang)
        payload = {
            "model": OLLAMA_MODEL,
            "stream": False,
            "options": {"temperature": 0},
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "You are a professional machine translation engine. "
                        f"Translate the following text into {target_name}. "
                        "Return only the translation, with no notes or explanations.\n\n"
                        f"{text}"
                    ),
                }
            ],
        }
        response = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
        response.raise_for_status()
        content = response.json()["message"]["content"].strip()
        return re.sub(r"^<think>.+?</think>", "", content, count=1, flags=re.DOTALL).strip()


def get_translator(engine: str) -> BaseTranslator:
    if engine == "google":
        return GoogleMobileTranslator()
    if engine == "bing":
        return BingWebTranslator()
    if engine == "ollama":
        return OllamaTranslator()
    raise ValueError(f"Unsupported engine: {engine}")


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


def chunk_text(text: str, max_chars: int = 4000) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    parts = re.split(r"(\n\s*\n)", text)
    chunks = []
    current = ""
    for part in parts:
        if len(current) + len(part) > max_chars and current:
            chunks.append(current)
            current = part
        else:
            current += part
    if current:
        chunks.append(current)
    return chunks


def translate_text_block(translator: BaseTranslator, text: str, target_lang: str) -> str:
    translated = []
    for chunk in chunk_text(text):
        if chunk.strip():
            translated.append(translator.translate_with_retry(chunk, "auto", target_lang))
        else:
            translated.append(chunk)
    return "".join(translated)


def translate_segment(translator: BaseTranslator, text: str, target_lang: str, cache: Dict[str, str]) -> str:
    if not text or not text.strip():
        return text
    leading = re.match(r"^\s*", text).group(0)
    trailing = re.search(r"\s*$", text).group(0)
    body = text[len(leading) : len(text) - len(trailing) if trailing else len(text)]
    if not body:
        return text
    if body not in cache:
        cache[body] = translator.translate_with_retry(body, "auto", target_lang)
    return leading + cache[body] + trailing


def translate_lines_preserving_layout(translator: BaseTranslator, content: str, target_lang: str) -> str:
    lines = content.splitlines()
    translated: List[str] = []
    cache: Dict[str, str] = {}
    for line in lines:
        if not line.strip() or re.match(r"^\s*[-=_*]{3,}\s*$", line):
            translated.append(line)
        else:
            translated.append(translate_segment(translator, line, target_lang, cache))
    result = "\n".join(translated)
    if content.endswith(("\n", "\r")):
        result += "\n"
    return result


def translate_txt_bilingual_interleaved(translator: BaseTranslator, content: str, target_lang: str) -> str:
    lines = content.splitlines()
    bilingual: List[str] = []
    cache: Dict[str, str] = {}
    for line in lines:
        if not line.strip() or re.match(r"^\s*[-=_*]{3,}\s*$", line):
            bilingual.append(line)
        else:
            bilingual.append(line)
            bilingual.append(translate_segment(translator, line, target_lang, cache))
    result = "\n".join(bilingual)
    if content.endswith(("\n", "\r")):
        result += "\n"
    return result


def translate_txt(input_path: str, translator: BaseTranslator, target_lang: str, mode: str) -> List[str]:
    with open(input_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    generated = []
    source_code = source_lang_code_for_text(content)
    target_code = output_lang_code(target_lang)
    mono_output = output_path(input_path, f"_{target_code}", ".txt")
    dual_output = output_path(input_path, f"_{source_code}_{target_code}", ".txt")
    if mode in {"mono", "both"}:
        translated = translate_lines_preserving_layout(translator, content, target_lang)
        with open(mono_output, "w", encoding="utf-8") as handle:
            handle.write(translated)
        generated.append(mono_output)
    if mode in {"dual", "both"}:
        bilingual = translate_txt_bilingual_interleaved(translator, content, target_lang)
        with open(dual_output, "w", encoding="utf-8") as handle:
            handle.write(bilingual)
        generated.append(dual_output)
    return generated


PLACEHOLDER_PATTERN = (
    r"FRONTMATTER_\d+|MULTILINE_CODE_\d+|LATEX_BLOCK_\d+|CODE_\d+|LATEX_INLINE_\d+|"
    r"LINK_PRE_\d+|LINK_SUF_\d+|LINK_\d+|STRONG_PRE_\d+|STRONG_SUF_\d+|"
    r"HEADING_\d+|LIST_\d+|BLOCKQUOTE_\d+|HTML_\d+"
)
PLACEHOLDER_SPLIT_REGEX = re.compile(rf"(<<<(?:{PLACEHOLDER_PATTERN})>>>)")
PLACEHOLDER_TEST_REGEX = re.compile(rf"^<<<(?:{PLACEHOLDER_PATTERN})>>>$")


def next_placeholder(kind: str, counters: Dict[str, int], placeholders: Dict[str, str], value: str) -> str:
    counters[kind] = counters.get(kind, 100) + 1
    placeholder = f"<<<{kind}_{counters[kind]}>>>"
    placeholders[placeholder] = value
    return placeholder


def protect_markdown_blocks(content: str, placeholders: Dict[str, str], counters: Dict[str, int]) -> str:
    if content.startswith("---\n"):
        content = re.sub(
            r"^---\n[\s\S]*?\n---(?=\n|$)",
            lambda match: next_placeholder("FRONTMATTER", counters, placeholders, match.group(0)),
            content,
            count=1,
        )

    lines = content.split("\n")
    protected_lines: List[str] = []
    block: List[str] = []
    fence: str | None = None
    for line in lines:
        fence_match = re.match(r"^\s*(```+|~~~+)", line)
        if fence:
            block.append(line)
            if line.strip().startswith(fence):
                protected_lines.append(next_placeholder("MULTILINE_CODE", counters, placeholders, "\n".join(block)))
                block = []
                fence = None
            continue
        if fence_match:
            fence = fence_match.group(1)[:3]
            block = [line]
            continue
        protected_lines.append(line)
    if block:
        protected_lines.extend(block)
    content = "\n".join(protected_lines)

    return re.sub(
        r"\$\$[\s\S]*?\$\$",
        lambda match: next_placeholder("LATEX_BLOCK", counters, placeholders, match.group(0)),
        content,
    )


def protect_markdown_line(line: str, placeholders: Dict[str, str], counters: Dict[str, int]) -> str:
    modified = line

    if re.match(r"^\s*[-*_]{3,}\s*$", modified):
        return next_placeholder("HTML", counters, placeholders, modified)

    modified = re.sub(
        r"`([^`\n]+?)`",
        lambda match: next_placeholder("CODE", counters, placeholders, match.group(0)),
        modified,
    )

    def protect_inline_latex(match: re.Match) -> str:
        content = match.group(1)
        if re.match(r"^[\s\d,.]+$", content) and "\\" not in content:
            return match.group(0)
        return next_placeholder("LATEX_INLINE", counters, placeholders, match.group(0))

    modified = re.sub(r"\$([^$\n]+?)\$", protect_inline_latex, modified)

    html_patterns = [
        r"<!--[\s\S]*?-->",
        r"<([a-zA-Z][a-zA-Z0-9-]*)\s*[^>]*/>",
        r"</([a-zA-Z][a-zA-Z0-9-]*)>",
        r"<([a-zA-Z][a-zA-Z0-9-]*)(?:\s+[^>]*)?>",
    ]
    for pattern in html_patterns:
        modified = re.sub(pattern, lambda match: next_placeholder("HTML", counters, placeholders, match.group(0)), modified)

    def protect_image(match: re.Match) -> str:
        prefix, content, suffix = match.group(1), match.group(2), match.group(3)
        if not content.strip():
            return next_placeholder("LINK", counters, placeholders, match.group(0))
        index = counters.get("LINK", 100) + 1
        counters["LINK"] = index
        prefix_placeholder = f"<<<LINK_PRE_{index}>>>"
        suffix_placeholder = f"<<<LINK_SUF_{index}>>>"
        placeholders[prefix_placeholder] = prefix
        placeholders[suffix_placeholder] = suffix
        return f"{prefix_placeholder}{content}{suffix_placeholder}"

    modified = re.sub(r"(!\[)(.*?)(\]\(.*?\))", protect_image, modified)

    def protect_link(match: re.Match) -> str:
        prefix, content, suffix = match.group(1), match.group(2), match.group(3)
        index = counters.get("LINK", 100) + 1
        counters["LINK"] = index
        prefix_placeholder = f"<<<LINK_PRE_{index}>>>"
        suffix_placeholder = f"<<<LINK_SUF_{index}>>>"
        placeholders[prefix_placeholder] = prefix
        placeholders[suffix_placeholder] = suffix
        return f"{prefix_placeholder}{content}{suffix_placeholder}"

    modified = re.sub(r"(\[)(.*?)(\]\(.*?\))", protect_link, modified)
    modified = re.sub(r"https?://[^\s)]+", lambda match: next_placeholder("LINK", counters, placeholders, match.group(0)), modified)

    def protect_strong(match: re.Match) -> str:
        index = counters.get("STRONG", 100) + 1
        counters["STRONG"] = index
        prefix_placeholder = f"<<<STRONG_PRE_{index}>>>"
        suffix_placeholder = f"<<<STRONG_SUF_{index}>>>"
        placeholders[prefix_placeholder] = match.group(1)
        placeholders[suffix_placeholder] = match.group(3)
        return f"{prefix_placeholder}{match.group(2)}{suffix_placeholder}"

    modified = re.sub(r"(\*\*|__)(.+?)(\1)", protect_strong, modified)

    modified = re.sub(
        r"^(#{1,6}\s+)(.*)",
        lambda match: next_placeholder("HEADING", counters, placeholders, match.group(1)) + match.group(2),
        modified,
    )
    modified = re.sub(
        r"^(\s*(?:[-*+]|\d+\.)\s+)(.*)",
        lambda match: next_placeholder("LIST", counters, placeholders, match.group(1)) + match.group(2),
        modified,
    )
    modified = re.sub(
        r"^(>\s*)(.*)",
        lambda match: next_placeholder("BLOCKQUOTE", counters, placeholders, match.group(1)) + match.group(2),
        modified,
    )
    return modified


def translate_protected_line(
    translator: BaseTranslator,
    line: str,
    target_lang: str,
    cache: Dict[str, str],
) -> str:
    if not line.strip() or PLACEHOLDER_TEST_REGEX.match(line.strip()):
        return line
    translated_parts: List[str] = []
    for segment in PLACEHOLDER_SPLIT_REGEX.split(line):
        if not segment:
            continue
        if PLACEHOLDER_TEST_REGEX.match(segment):
            translated_parts.append(segment)
        else:
            translated_parts.append(translate_segment(translator, segment, target_lang, cache))
    return "".join(translated_parts)


def is_markdown_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def is_markdown_table_separator_cell(cell: str) -> bool:
    return bool(re.match(r"^:?-{3,}:?$", cell.strip()))


def is_markdown_table_separator_row(line: str) -> bool:
    if not is_markdown_table_row(line):
        return False
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(is_markdown_table_separator_cell(cell) for cell in cells)


def split_markdown_table_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_markdown_table_row(cells: List[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def translate_markdown_table_cell(
    translator: BaseTranslator,
    cell: str,
    target_lang: str,
    cache: Dict[str, str],
) -> str:
    if not cell.strip() or is_markdown_table_separator_cell(cell):
        return cell
    return translate_protected_line(translator, cell, target_lang, cache)


def translate_markdown_table_row(
    translator: BaseTranslator,
    line: str,
    target_lang: str,
    cache: Dict[str, str],
) -> str:
    if is_markdown_table_separator_row(line):
        return line
    return render_markdown_table_row(
        [translate_markdown_table_cell(translator, cell, target_lang, cache) for cell in split_markdown_table_row(line)]
    )


def translate_markdown_table_row_bilingual(
    translator: BaseTranslator,
    line: str,
    target_lang: str,
    cache: Dict[str, str],
) -> str:
    if is_markdown_table_separator_row(line):
        return line
    bilingual_cells = []
    for cell in split_markdown_table_row(line):
        translated = translate_markdown_table_cell(translator, cell, target_lang, cache)
        bilingual_cells.append(cell if translated == cell else f"{cell}<br>{translated}")
    return render_markdown_table_row(bilingual_cells)


def restore_placeholders(text: str, placeholders: Dict[str, str]) -> str:
    for placeholder, value in sorted(placeholders.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(placeholder, value)
    return text


def translate_markdown_content(translator: BaseTranslator, content: str, target_lang: str) -> str:
    placeholders: Dict[str, str] = {}
    counters: Dict[str, int] = {}
    protected = protect_markdown_blocks(content, placeholders, counters)
    protected_lines = [protect_markdown_line(line, placeholders, counters) for line in protected.split("\n")]
    cache: Dict[str, str] = {}
    translated_lines = [
        translate_markdown_table_row(translator, line, target_lang, cache)
        if is_markdown_table_row(line)
        else translate_protected_line(translator, line, target_lang, cache)
        for line in protected_lines
    ]
    translated = restore_placeholders("\n".join(translated_lines), placeholders)
    if content.endswith("\n") and not translated.endswith("\n"):
        translated += "\n"
    return translated


def translate_markdown_bilingual_interleaved(translator: BaseTranslator, content: str, target_lang: str) -> str:
    placeholders: Dict[str, str] = {}
    counters: Dict[str, int] = {}
    protected = protect_markdown_blocks(content, placeholders, counters)
    protected_lines = [protect_markdown_line(line, placeholders, counters) for line in protected.split("\n")]
    cache: Dict[str, str] = {}
    bilingual_lines: List[str] = []
    for line in protected_lines:
        if not line.strip() or PLACEHOLDER_TEST_REGEX.match(line.strip()):
            bilingual_lines.append(line)
            continue
        if is_markdown_table_row(line):
            bilingual_lines.append(translate_markdown_table_row_bilingual(translator, line, target_lang, cache))
            continue
        translated = translate_protected_line(translator, line, target_lang, cache)
        bilingual_lines.append(line)
        bilingual_lines.append(translated)
    bilingual = restore_placeholders("\n".join(bilingual_lines), placeholders)
    if content.endswith("\n") and not bilingual.endswith("\n"):
        bilingual += "\n"
    return bilingual


def translate_markdown(input_path: str, translator: BaseTranslator, target_lang: str, mode: str) -> List[str]:
    with open(input_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    generated = []
    source_code = source_lang_code_for_text(content)
    target_code = output_lang_code(target_lang)
    mono_output = output_path(input_path, f"_{target_code}")
    dual_output = output_path(input_path, f"_{source_code}_{target_code}")
    if mode in {"mono", "both"}:
        translated = translate_markdown_content(translator, content, target_lang)
        with open(mono_output, "w", encoding="utf-8") as handle:
            handle.write(translated)
        generated.append(mono_output)
    if mode in {"dual", "both"}:
        bilingual = translate_markdown_bilingual_interleaved(translator, content, target_lang)
        with open(dual_output, "w", encoding="utf-8") as handle:
            handle.write(bilingual)
        generated.append(dual_output)
    return generated


def docx_paragraph_text_nodes(paragraph):
    from lxml import etree

    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    }

    text_nodes = []
    for node in paragraph.xpath(".//w:t", namespaces=namespaces):
        nearest_paragraph = None
        for ancestor in node.iterancestors():
            if etree.QName(ancestor).localname == "p" and ancestor.nsmap.get("w") == namespaces["w"]:
                nearest_paragraph = ancestor
                break
        if nearest_paragraph is paragraph:
            text_nodes.append(node)
    return text_nodes


def translate_docx_paragraph_text(
    paragraph,
    translator: BaseTranslator,
    target_lang: str,
    cache: Dict[str, str],
) -> int:
    namespaces = {
        "xml": "http://www.w3.org/XML/1998/namespace",
    }

    text_nodes = docx_paragraph_text_nodes(paragraph)

    if not text_nodes:
        return 0

    original = "".join(node.text or "" for node in text_nodes)
    if not original.strip():
        return 0

    translated = translate_segment(translator, original, target_lang, cache)
    text_nodes[0].text = translated
    text_nodes[0].set(f"{{{namespaces['xml']}}}space", "preserve")
    for node in text_nodes[1:]:
        node.text = ""
    return 1


def translated_docx_bilingual_paragraph(paragraph, translated_text: str):
    from lxml import etree

    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "xml": "http://www.w3.org/XML/1998/namespace",
    }

    translated_paragraph = etree.Element(f"{{{namespaces['w']}}}p")

    paragraph_properties = paragraph.find(f"{{{namespaces['w']}}}pPr")
    if paragraph_properties is not None:
        translated_paragraph.append(copy.deepcopy(paragraph_properties))

    translated_run = etree.SubElement(translated_paragraph, f"{{{namespaces['w']}}}r")
    text_nodes = docx_paragraph_text_nodes(paragraph)
    if text_nodes:
        source_run = text_nodes[0].getparent()
        while source_run is not None and etree.QName(source_run).localname != "r":
            source_run = source_run.getparent()
        if source_run is not None:
            run_properties = source_run.find(f"{{{namespaces['w']}}}rPr")
            if run_properties is not None:
                translated_run.append(copy.deepcopy(run_properties))

    text_node = etree.SubElement(translated_run, f"{{{namespaces['w']}}}t")
    text_node.set(f"{{{namespaces['xml']}}}space", "preserve")
    text_node.text = translated_text
    return translated_paragraph


def translate_docx_paragraph_bilingual(
    paragraph,
    translator: BaseTranslator,
    target_lang: str,
    cache: Dict[str, str],
) -> int:
    text_nodes = docx_paragraph_text_nodes(paragraph)
    if not text_nodes:
        return 0

    original = "".join(node.text or "" for node in text_nodes)
    if not original.strip():
        return 0

    translated = translate_segment(translator, original, target_lang, cache)
    translated_paragraph = translated_docx_bilingual_paragraph(paragraph, translated)
    parent = paragraph.getparent()
    if parent is None:
        return 0
    parent.insert(parent.index(paragraph) + 1, translated_paragraph)
    return 1


def translate_docx_xml_part(
    xml_bytes: bytes,
    translator: BaseTranslator,
    target_lang: str,
    cache: Dict[str, str],
    bilingual: bool = False,
) -> tuple[bytes, int]:
    from lxml import etree

    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
    root = etree.fromstring(xml_bytes, parser)
    translated_count = 0
    for paragraph in root.xpath(".//w:p", namespaces=namespaces):
        if bilingual:
            translated_count += translate_docx_paragraph_bilingual(paragraph, translator, target_lang, cache)
        else:
            translated_count += translate_docx_paragraph_text(paragraph, translator, target_lang, cache)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), translated_count


def translate_docx_preserve_layout(
    input_path: str,
    output_path_value: str,
    translator: BaseTranslator,
    target_lang: str,
    bilingual: bool = False,
) -> int:
    cache: Dict[str, str] = {}
    translated_count = 0
    with zipfile.ZipFile(input_path, "r") as source:
        names = source.namelist()
        xml_parts = set(docx_xml_part_names(names))
        with zipfile.ZipFile(output_path_value, "w") as destination:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename in xml_parts:
                    data, count = translate_docx_xml_part(data, translator, target_lang, cache, bilingual=bilingual)
                    translated_count += count
                destination.writestr(info, data)
    return translated_count


def translate_docx(input_path: str, translator: BaseTranslator, target_lang: str, mode: str) -> List[str]:
    generated = []
    source_code = source_lang_code_for_docx(input_path)
    target_code = output_lang_code(target_lang)
    mono_output = output_path(input_path, f"_{target_code}", ".docx")
    dual_output = output_path(input_path, f"_{source_code}_{target_code}", ".docx")

    if mode in {"mono", "both"}:
        translated_count = translate_docx_preserve_layout(input_path, mono_output, translator, target_lang)
        generated.append(mono_output)
        print(f"DOCX layout-preserving translation updated {translated_count} paragraph(s).")

    if mode in {"dual", "both"}:
        translated_count = translate_docx_preserve_layout(input_path, dual_output, translator, target_lang, bilingual=True)
        generated.append(dual_output)
        print(f"DOCX bilingual layout-preserving translation inserted {translated_count} paragraph(s).")
    return generated


def process_file(input_path: str, translator: BaseTranslator, target_lang: str, mode: str) -> List[str]:
    ext = os.path.splitext(input_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {input_path}")
    if ext == ".txt":
        return translate_txt(input_path, translator, target_lang, mode)
    if ext in {".md", ".markdown"}:
        return translate_markdown(input_path, translator, target_lang, mode)
    if ext == ".docx":
        return translate_docx(input_path, translator, target_lang, mode)
    raise ValueError(f"Unsupported file type: {input_path}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Translate txt, markdown, and docx files.")
    parser.add_argument("--engine", choices=["google", "bing", "ollama"], default="google")
    parser.add_argument("--lang-out", choices=sorted(LANGUAGE_NAMES.keys()), default="zh")
    parser.add_argument("--mode", choices=["dual", "mono", "both"], default="both")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    translator = get_translator(args.engine)
    failed = []
    succeeded = []

    for file_path in args.files:
        print(f"\nTranslating: {file_path}")
        if not os.path.exists(file_path):
            print(f"Error: file does not exist: {file_path}")
            failed.append(file_path)
            continue
        try:
            generated = process_file(file_path, translator, args.lang_out, args.mode)
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
