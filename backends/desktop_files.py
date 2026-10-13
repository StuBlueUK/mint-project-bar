"""List installed .desktop apps for pinning."""
from __future__ import annotations

import os

try:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
except Exception:  # pragma: no cover - import guard for docs builds
    Gio = None  # type: ignore


def _icon_name(info) -> str:
    try:
        from backends.launcher import icon_for_info

        return icon_for_info(info)
    except Exception:
        pass
    try:
        s = info.get_string("Icon")
        if s:
            return s
    except Exception:
        pass
    return "application-x-executable"


def list_apps() -> list[dict]:
    if Gio is None:
        return []
    apps = []
    for info in Gio.DesktopAppInfo.get_all():
        try:
            desktop_id = info.get_id()
            name = info.get_display_name() or desktop_id
            # Skip hidden / no-display entries
            if info.get_nodisplay():
                continue
            apps.append(
                {
                    "desktop_id": desktop_id,
                    "name": name,
                    "icon": _icon_name(info),
                    "exec": info.get_string("Exec") or "",
                }
            )
        except Exception:
            continue
    return sorted(apps, key=lambda a: a["name"].lower())


def user_app_dirs() -> list[str]:
    return [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications"),
    ]
