# Legacy Tk Version

This directory preserves the original Python/Tk macOS Finder Quick Action implementation that preceded the native Swift `Service Tools` app.

It is archived rather than deleted so existing users and contributors can inspect or continue using the earlier standalone GUIs. New features and fixes should normally target the repository root.

## Contents

```text
scripts/                      Tk GUIs and their worker scripts
macos/install_quick_actions.py  Legacy per-user installer
```

## Install the Archived Version

From the repository root:

```bash
python3 legacy/tk/macos/install_quick_actions.py
```

This installs the legacy scripts under `~/Library/Application Support/TranslateDocumentQuickAction` and creates its four translation/transcription Quick Actions under `~/Library/Services`.

Do not install the legacy and current Quick Actions at the same time: they use several of the same Finder menu names.
