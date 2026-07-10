# Changelog

## 2.0.0 — 2026-07-10

### Added

- A shared native Swift/AppKit Service Tools application for all current Finder Quick Actions.
- Finder actions for PDF, document, and image translation; audio/video transcription; image resizing and compression; and PDF/image OCR.
- Native controls for translation engines, target languages, output modes, image backends, MacWhisper options, resize dimensions, formats, and quality.
- Portable, reviewable XML workflow bundles that use `$HOME` rather than a user-specific path.
- A reproducible release packager, standalone release installer, and SHA-256 checksum.
- Repository privacy tests that reject personal home-directory and device-path markers.

### Changed

- Replaced the active Tk frontends with the native Service Tools application.
- Made worker discovery relative to the application bundle.
- Updated public documentation with complete feature, dependency, privacy, and troubleshooting information.

### Preserved

- The original Python/Tk implementation remains available under `legacy/tk` for reference and existing users.

### Distribution

- The downloadable application is ad-hoc signed and is not Apple-notarized.
- Third-party translation, OCR, transcription, and image-processing dependencies are not bundled.
