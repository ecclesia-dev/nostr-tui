"""Image rendering (via chafa) and NIP-96 upload."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import requests

NIP96_UPLOAD_URL = "https://nostr.build/api/v2/upload/files"


def render_image_url(url: str, max_height: int = 20, protocol: str = "sixel") -> str:
    """Download an image and render it as terminal art via chafa.

    Args:
        url: HTTP(S) URL of the image.
        max_height: Maximum height in character rows.
        protocol: Terminal graphics protocol (sixel, kitty, ascii).

    Returns:
        Rendered string output from chafa, or a fallback message on error.
    """
    try:
        resp = requests.get(url, timeout=10, stream=True)
        resp.raise_for_status()
    except Exception:
        return f"[image: {url}]"

    suffix = Path(url.split("?")[0]).suffix or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        for chunk in resp.iter_content(8192):
            tmp.write(chunk)
        tmp_path = tmp.name

    format_map = {
        "sixel": "sixels",
        "kitty": "kitty",
        "ascii": "symbols",
    }
    chafa_fmt = format_map.get(protocol, "symbols")

    try:
        result = subprocess.run(
            [
                "chafa",
                "--format", chafa_fmt,
                "--size", f"x{max_height}",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return result.stdout
    except FileNotFoundError:
        return f"[image: {url}] (install chafa for inline images)"
    except Exception:
        pass
    finally:
        os.unlink(tmp_path)

    return f"[image: {url}]"


def upload_image_nip96(
    filepath: str,
    upload_url: str = NIP96_UPLOAD_URL,
) -> str:
    """Upload an image file via NIP-96.

    Args:
        filepath: Local path to the image file.
        upload_url: NIP-96 upload endpoint (defaults to nostr.build).

    Returns:
        The public URL of the uploaded image.

    Raises:
        RuntimeError: If the upload fails.
    """
    path = Path(filepath)
    if not path.exists():
        raise RuntimeError(f"File not found: {filepath}")

    with open(path, "rb") as f:
        resp = requests.post(
            upload_url,
            files={"file": (path.name, f)},
            timeout=60,
        )

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Upload failed: HTTP {resp.status_code}")

    data = resp.json()
    # nostr.build returns {"status": "success", "nip94_event": {"tags": [["url", "..."], ...]}}
    try:
        tags = data["nip94_event"]["tags"]
        for tag in tags:
            if tag[0] == "url":
                return tag[1]
    except (KeyError, IndexError, TypeError):
        pass

    raise RuntimeError(f"Upload response missing URL: {data}")
