# Third-party notices

`scripts/vendor/translate_text_backend.py` is adapted from
[Jingyuan-Zheng/Mac-Lite-Translator_TranslateGemma](https://github.com/Jingyuan-Zheng/Mac-Lite-Translator_TranslateGemma),
commit `9763dcf892902d899d4676720bd4df896ae9e7cd`.
The only vendor change is removing the machine-specific default model path.
Its MIT license is retained in `scripts/vendor/LICENSE`.
The adapter reuses its Google/Bing/DeepL implementations; the UI event loop is
not run by the PDF workflow.

Model weights and external PDF/ML/OCR/image-processing tools are not bundled.
Consult each dependency's license and each external service's terms separately.
