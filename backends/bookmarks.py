"""Read GTK bookmarks + Nemo-relevant folders for pin import."""
from __future__ import annotations

import os
from urllib.parse import unquote
from urllib.request import url2pathname


def read_gtk_bookmarks() -> list[dict]:
    path = os.path.expanduser("~/.config/gtk-3.0/bookmarks")
    pins: list[dict] = []
    if not os.path.exists(path):
        return pins
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            uri = parts[0]
            name = parts[1] if len(parts) > 1 else _name_from_uri(uri)
            pins.append({"type": "folder", "uri": uri, "name": name})
    return pins


def _name_from_uri(uri: str) -> str:
    try:
        p = url2pathname(uri.split("file://", 1)[1])
        return unquote(os.path.basename(p.rstrip("/")) or p)
    except Exception:
        return uri
