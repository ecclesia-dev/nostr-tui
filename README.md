# nostr-tui

A terminal UI client for the [Nostr](https://nostr.com) protocol, built with Python and [Textual](https://textual.textualize.io/).

Browse your Nostr feed, post notes, attach images via NIP-96, and send zaps — all from the terminal.

---

## Requirements

- Python 3.11+
- [`chafa`](https://hpjansson.org/chafa/) — for inline image rendering (sixel/kitty/ascii). Optional; images fall back to URL display if missing.

Install `chafa` on macOS:

```sh
brew install chafa
```

---

## Installation

```sh
pip install .
```

This installs the `nostr-tui` command.

---

## Configuration

Copy the example config and fill in your details:

```sh
mkdir -p ~/.config/nostr-tui
cp config.example.toml ~/.config/nostr-tui/config.toml
```

Edit `~/.config/nostr-tui/config.toml`:

```toml
[nostr]
nsec = "nsec1..."          # your Nostr private key (bech32 nsec format)
relays = [
  "wss://relay.damus.io",
  "wss://nos.lol",
]

[display]
image_protocol = "sixel"   # sixel | ascii | kitty
max_image_height = 20

[upload]
# Optional: override the NIP-96 upload server (default: nostr.build)
# server = "https://nostr.build/api/v2/upload/files"
```

> **Security:** `~/.config/nostr-tui/config.toml` is excluded from git by `.gitignore`.
> Never commit your real `nsec`. The config file stays local.

---

## Running

```sh
nostr-tui
```

---

## Features

- **Feed** — subscribes to kind:1 text notes from configured relays, deduplicated, sorted newest-first
- **Posting** — compose and publish signed kind:1 notes via NIP-01
- **Image upload** — attach images via [NIP-96](https://github.com/nostr-protocol/nips/blob/master/96.md) (defaults to nostr.build, configurable)
- **Inline images** — renders image URLs in notes via `chafa` (sixel/kitty/ascii)
- **Zap display** — shows incoming zap totals on notes (reads `amount` tags from zap receipts)
- **Zap sending** — sends NIP-57 kind:9734 zap requests; press `z` to open the zap dialog

---

## Key Bindings

| Key | Action |
|-----|--------|
| `n` | Focus compose input (new note) |
| `r` | Refresh feed (re-subscribe) |
| `i` | Attach image (opens path dialog) |
| `z` | Send a zap (opens zap dialog) |
| `q` | Quit |

---

## Attaching Images

Press `i` (or click the 📎 Image button in the compose panel) to open the image path dialog.
Enter the local file path to your image and press Enter or click **Attach**.
The image will be uploaded on post and its URL appended to your note content.

---

## Sending Zaps

Press `z` to open the zap dialog. Click on a note first to pre-fill the recipient pubkey.

The zap flow:
1. Looks up the recipient's Lightning address from their kind:0 metadata
2. Builds a signed NIP-57 zap request (kind:9734) and publishes it to relays
3. Shows you the recipient's Lightning address / LNURL in a notification

> **Note:** Full invoice generation and payment require a connected Lightning wallet.
> This client handles the Nostr side (zap request publication). Payment is external.

---

## Known Limitations

- **Zap sending UI (v0):** The zap dialog builds and publishes the kind:9734 zap request event, but does not automatically generate or pay a Lightning invoice. You receive the recipient's LNURL/Lightning address in a notification for manual payment.
- **Image attach path (v0):** Image attachment uses a path dialog rather than a file picker. You must type the full local file path.
- **No DMs / threads:** Only kind:1 notes are displayed. Replies, DMs, and other event kinds are not yet handled.
- **No relay write auth:** Relay authentication (NIP-42) is not implemented.

---

## Project Layout

```
nostr_tui/
  app.py        Main Textual app, modals (ImagePathModal, ZapModal)
  compose.py    Compose widget
  feed.py       Feed and NoteWidget
  relay.py      RelayPool — async WebSocket connections
  events.py     NIP-01 event construction and signing
  images.py     NIP-96 image upload, chafa rendering
  zaps.py       NIP-57 zap request construction, LNURL lookup
  config.py     Config loader (TOML)
```

---

*Ad maiorem Dei gloriam.*
