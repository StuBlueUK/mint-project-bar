"""Icon + path helpers: never show a broken/missing icon,
and expand ~/ $HOME in pinned folder URIs."""
from __future__ import annotations

import os

try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
except Exception:  # pragma: no cover
    Gtk = None  # type: ignore


def safe_icon(name: str | None, *fallbacks: str) -> str:
    """Return the first icon name present in the current theme."""
    candidates = [n for n in (name, *fallbacks) if n]
    if Gtk is None:
        return candidates[0] if candidates else "image-missing"
    try:
        theme = Gtk.IconTheme.get_default()
        for n in candidates:
            # absolute paths are used as-is
            if os.path.isabs(n) and os.path.exists(n):
                return n
            try:
                if theme.has_icon(n):
                    return n
            except Exception:
                continue
    except Exception:
        pass
    return candidates[-1] if candidates else "image-missing"


def expand_folder_uri(uri: str) -> str:
    """Expand ~/ $HOME $USER inside file:// folder URIs."""
    if not uri:
        return uri
    try:
        if uri.startswith("file://"):
            path = uri[len("file://"):]
            expanded = os.path.expandvars(os.path.expanduser(path))
            if expanded != path:
                return "file://" + expanded
        elif uri.startswith(("~", "$")):
            return "file://" + os.path.expandvars(os.path.expanduser(uri))
    except Exception:
        pass
    return uri
