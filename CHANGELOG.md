# Changelog

All notable changes to Nostr TUI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-03-03

### Added
- Textual TUI client for Nostr with feed, posting, images, and zaps
- Image attachment UI
- Configurable upload URL

### Fixed
- Security hardening: signature verification, relay/upload URL validation
- README corrections
- Temp file leak cleanup
- Relay CLOSE handling
- Image upload improvements
- Async safety improvements
- Corrected setuptools backend
- Tightened .gitignore (config.toml not *.toml)

### Credits
Built by Jerome. Reviewed by Cyprian (QA).
