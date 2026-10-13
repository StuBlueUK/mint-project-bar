"""Running-window tracker (X11/Wnck). Graceful no-op on Wayland.

Wraps Wnck.Screen singleton, emits on_change callbacks, and maps windows
back to .desktop ids so pins can show running dots and "Pin this app" works.
"""
from __future__ import annotations

import re

try:
    import gi

    gi.require_version("Wnck", "3.0")
    from gi.repository import Wnck, Gtk
    HAVE_WNCK = True
except Exception:  # Wayland or missing gir1.2-wnck-3.0
    Wnck = Gtk = None  # type: ignore
    HAVE_WNCK = False

_tracker_instance = None


def get_shared_tracker():
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = RunningTracker()
    return _tracker_instance


def _tokens(s: str) -> set[str]:
    return set(t for t in re.split(r"[.\-_ :/()]+", (s or "").lower()) if t)


class RunningTracker:
    available = HAVE_WNCK

    def __init__(self):
        self._callbacks: list = []
        self._screen = None
        if not HAVE_WNCK:
            return
        try:
            self._screen = Wnck.Screen.get_default()
            if self._screen is None:
                self.available = False
                return
            self._screen.force_update()
            for sig in ("window-opened", "window-closed", "active-window-changed"):
                try:
                    self._screen.connect(sig, lambda *_a: self._emit())
                except Exception:
                    pass
        except Exception:
            self.available = False
            self._screen = None

    # -- subscription ------------------------------------------------------
    def connect(self, callback):
        self._callbacks.append(callback)

    def _emit(self):
        for cb in list(self._callbacks):
            try:
                cb()
            except Exception:
                pass

    # -- query --------------------------------------------------------------
    def list_windows(self) -> list[dict]:
        if not self.available or self._screen is None:
            return []
        try:
            self._screen.force_update()
            wins = self._screen.get_windows() or []
        except Exception:
            return []
        out = []
        for w in wins:
            try:
                name = w.get_name() or "?"
                if "Mint Project Bar" in name:
                    continue
                # hide desktop/dock background components (nemo-desktop,
                # conky, docks): they are not switchable apps
                try:
                    wt = w.get_window_type()
                    if wt in (Wnck.WindowType.DESKTOP, Wnck.WindowType.DOCK):
                        continue
                except Exception:
                    pass
                out.append(
                    {
                        "xid": w.get_xid(),
                        "name": name,
                        "active": bool(w.is_active()),
                        "minimized": bool(w.is_minimized()),
                        "class_group": _safe(w.get_class_group_name),
                        "class_instance": _safe(w.get_class_instance_name),
                        "app_name": _safe(lambda: w.get_application().get_name()) if _safe(lambda: w.get_application()) else "",
                        "icon_name": _safe(w.get_icon_name) or "application-x-executable",
                        "window": w,
                    }
                )
            except Exception:
                continue
        # active first, then alphabetical
        out.sort(key=lambda d: (not d["active"], d["name"].lower()))
        return out

    # -- actions (select between them) ---------------------------------------
    def activate(self, win: dict | object):
        w = win.get("window") if isinstance(win, dict) else win
        if w is None or Gtk is None:
            return
        try:
            t = Gtk.get_current_event_time()
        except Exception:
            t = 0
        try:
            if w.is_minimized():
                w.unminimize(t)
            # toggle: clicking active window minimizes (taskbar behaviour)
            if w.is_active():
                w.minimize()
            else:
                w.activate(t)
        except Exception:
            pass

    def close(self, win: dict | object):
        w = win.get("window") if isinstance(win, dict) else win
        if w is None or Gtk is None:
            return
        try:
            w.close(Gtk.get_current_event_time())
        except Exception:
            pass

    def minimize(self, win: dict | object):
        w = win.get("window") if isinstance(win, dict) else win
        if w is None:
            return
        try:
            w.minimize()
        except Exception:
            pass


def _safe(fn, default=""):
    try:
        v = fn()
        return v if v is not None else default
    except Exception:
        return default


# -- grouping (one tile per app, not per window) ------------------------------
def group_key(win: dict) -> str:
    """Normalized app identity so N Firefox windows collapse to one tile."""
    for field in ("class_group", "class_instance", "app_name"):
        v = (win.get(field) or "").strip().lower()
        if v:
            # drop version-ish suffixes: "firefox-beta" stays, "chrome 123" -> chrome
            v = re.split(r"\s+\d", v)[0].strip()
            return v
    # class info missing (some Electron/Chromium windows): shared icon
    # still identifies the app, so group on it before falling to titles.
    icon = (win.get("icon_name") or "").strip().lower()
    if icon and icon != "application-x-executable":
        return "icon:" + icon
    # last resort: first chunk of window title
    title = (win.get("name") or "?").strip().lower().split(" — ")[0].split(" - ")[0]
    return title[:24] or "?"


def group_label(win: dict) -> str:
    for field in ("app_name", "class_group", "class_instance"):
        v = (win.get(field) or "").strip()
        if v:
            return v
    # class info missing: window titles are usually "<doc> - <App>", use the app part
    title = (win.get("name") or "?").strip()
    for sep in (" — ", " - ", " | "):
        if sep in title:
            title = title.split(sep)[-1].strip() or title
            break
    return title[:18] or "?"


def group_windows(windows: list[dict]) -> list[dict]:
    """Collapse a window list into per-app groups.

    Returns [{key, label, icon_name, windows, count, active}...],
    sorted active-group-first then alphabetical.
    """
    buckets: dict[str, list[dict]] = {}
    for w in windows:
        buckets.setdefault(group_key(w), []).append(w)
    groups = []
    for key, wins in buckets.items():
        wins.sort(key=lambda d: (not d.get("active"), d.get("name", "").lower()))
        first_active = next((w for w in wins if w.get("active")), wins[0])
        # prefer a non-generic icon from the group
        icon = first_active.get("icon_name") or "application-x-executable"
        if icon == "application-x-executable":
            for w in wins:
                if w.get("icon_name") and w["icon_name"] != "application-x-executable":
                    icon = w["icon_name"]
                    break
        groups.append(
            {
                "key": key,
                "label": group_label(first_active),
                "icon_name": icon,
                "windows": wins,
                "count": len(wins),
                "active": any(w.get("active") for w in wins),
            }
        )
    groups.sort(key=lambda g: (not g["active"], g["label"].lower()))
    return groups


def window_matches_pin(win: dict, pin: dict) -> bool:
    """True if a running window belongs to a pinned app."""
    hay = " ".join(
        [
            win.get("class_group", ""),
            win.get("class_instance", ""),
            win.get("app_name", ""),
            win.get("name", ""),
        ]
    ).lower()
    if pin.get("desktop_id"):
        base = pin["desktop_id"].lower().replace(".desktop", "")
        parts = [p for p in re.split(r"[.\-_]+", base) if p and p not in ("org", "gnome", "com", "io", "net", "desktop")]
        for p in parts:
            if len(p) >= 3 and p in hay:
                return True
        # explicit name match
        if pin.get("name", "").lower() in hay:
            return True
    elif pin.get("exec"):
        prog = pin["exec"].strip().split()[0]
        prog = prog.split("/")[-1].lower()
        if len(prog) >= 3 and prog in hay:
            return True
    return False


def guess_pin(win: dict):
    """Best-effort pin dict for 'Pin this app' on an open window."""
    try:
        from backends.launcher import _all_infos  # local import

        wtoks = _tokens(win.get("class_group", "")) | _tokens(win.get("class_instance", "")) | _tokens(win.get("app_name", ""))
        wtoks = {t for t in wtoks if len(t) >= 3}
        best = None
        best_score = 0
        for info in _all_infos():
            try:
                cid = (info.get_id() or "").lower().replace(".desktop", "")
                ctoks = _tokens(cid) | _tokens(info.get_display_name() or "")
                score = len(wtoks & ctoks)
                if score > best_score:
                    best_score = score
                    best = info
            except Exception:
                continue
        if best is not None and best_score > 0:
            return {"type": "app", "desktop_id": best.get_id(), "name": best.get_display_name()}
    except Exception:
        pass
    # fallback: launch by class name guess
    guess = win.get("class_instance") or win.get("class_group") or win.get("app_name")
    if guess:
        return {"type": "app", "exec": guess.lower(), "name": win.get("name") or guess}
    return None


def window_is_bar_app(win: dict, pins: list[dict], sess_keys: set[str]) -> bool:
    """True if a window belongs to the bar: pinned app or bar-launched app.

    Used by the Open-section 'bar only' filter to hide desktop junk
    (conky, nemo-desktop, …) and apps started elsewhere.
    """
    for pin in pins or []:
        if isinstance(pin, dict) and pin.get("type") == "app":
            try:
                if window_matches_pin(win, pin):
                    return True
            except Exception:
                continue
    if not sess_keys:
        return False
    hay = " ".join(
        [
            win.get("class_group", ""),
            win.get("class_instance", ""),
            win.get("app_name", ""),
            win.get("name", ""),
        ]
    ).lower()
    for key in sess_keys:
        if key.startswith("exec:"):
            prog = key[5:]
            if len(prog) >= 3 and prog in hay:
                return True
        else:
            base = key.replace(".desktop", "")
            for p in re.split(r"[.\-_]+", base):
                if p and p not in ("org", "gnome", "com", "io", "net", "desktop") and len(p) >= 3 and p in hay:
                    return True
    return False
