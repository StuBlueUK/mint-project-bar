"""Robust app launching: resolves stale desktop_ids, strips Exec codes,
expands ~/env in custom commands, and returns errors instead of failing silently.
"""
from __future__ import annotations

import os
import re
import shlex

try:
    import gi

    gi.require_version("Gio", "2.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gio, Gdk, GLib
except Exception:  # pragma: no cover
    Gio = Gdk = GLib = None  # type: ignore

# Exec field codes that take no value and must be stripped (%f %F %u %U %d %D
# %n %N %i %c %k %v %m). Codes with values are rare in the wild; drop the token.
_EXEC_CODE_RE = re.compile(r"%[fFuUdDnNiIckvm]")


def _all_infos() -> list:
    if Gio is None:
        return []
    try:
        return list(Gio.DesktopAppInfo.get_all())
    except Exception:
        return []


def resolve_info(desktop_id: str | None):
    """Resolve a .desktop id fuzzily. Exact hit first, then basename/alias match.

    Handles the classic breakage: config says gnome-terminal.desktop but the
    system ships org.gnome.Terminal.desktop.
    """
    if not desktop_id or Gio is None:
        return None
    # 1. exact
    try:
        info = Gio.DesktopAppInfo.new(desktop_id)
        if info:
            return info
    except Exception:
        pass
    want = desktop_id.lower()
    want_base = os.path.basename(want).replace(".desktop", "")
    # normalise separators: gnome-terminal ~ org.gnome.Terminal ~ gnome_terminal
    want_tokens = set(re.split(r"[.\-_ ]+", want_base))
    # collect fuzzy candidates, prefer shortest / fewest extra tokens so
    # gnome-terminal -> org.gnome.Terminal, not .Terminal.Preferences
    best = None
    best_extra = 999
    for info in _all_infos():
        try:
            cand_id = (info.get_id() or "").lower()
            cand_base = os.path.basename(cand_id).replace(".desktop", "")
            if cand_id == want or cand_base == want_base:
                return info
            cand_tokens = set(re.split(r"[.\-_ ]+", cand_base))
            name = (info.get_display_name() or "").lower()
            matched = False
            if want_base and want_base in cand_tokens:
                matched = True
            elif want_tokens and want_tokens <= cand_tokens:
                matched = True
            elif want_base in (name.replace(" ", "-"), name.replace(" ", "")):
                matched = True
            if matched:
                extra = len(cand_tokens - want_tokens) + max(0, len(cand_base) - len(want_base)) / 100.0
                if extra < best_extra:
                    best_extra = extra
                    best = info
        except Exception:
            continue
    return best


def icon_for_info(info) -> str:
    try:
        icon = info.get_icon()
        if icon is not None:
            # ThemedIcon -> first name; FileIcon -> path
            if hasattr(icon, "get_names"):
                try:
                    names = icon.get_names()
                    if names:
                        return names[0]
                except Exception:
                    pass
            try:
                s = icon.to_string()
                if s:
                    # "themed-icon:name1:name2" or plain name/path
                    if s.startswith(". "):
                        s = s[2:]
                    parts = s.split(":")
                    return parts[-1] or s
            except Exception:
                pass
        s = info.get_string("Icon")
        if s:
            return s
    except Exception:
        pass
    return "application-x-executable"


def _strip_exec_codes(exec_line: str) -> list[str]:
    try:
        argv = shlex.split(exec_line)
    except Exception:
        return []
    out = []
    for tok in argv:
        cleaned = _EXEC_CODE_RE.sub("", tok)
        if cleaned:
            out.append(os.path.expandvars(os.path.expanduser(cleaned)))
    return out


def spawn_detached(argv: list[str], workdir: str | None = None) -> None:
    """Launch argv detached. NB: PyGObject takes (argv, working_directory=,
    flags=) — NOT the C positional order (that silently broke every
    custom-exec launch)."""
    GLib.spawn_async(
        list(argv),
        **({"working_directory": workdir} if workdir else {}),
        flags=GLib.SpawnFlags.SEARCH_PATH,
    )


def launch_info(info) -> tuple[bool, str]:
    """Launch a resolved DesktopAppInfo. Returns (ok, message)."""
    try:
        ctx = Gio.AppLaunchContext.new()
        try:
            display = Gdk.Display.get_default()
            if display is not None:
                screen = Gdk.Screen.get_default()
                if screen is not None:
                    ctx.set_screen(screen)
        except Exception:
            pass
        ok = info.launch([], ctx)
        if ok:
            try:
                note_launched({"type": "app", "desktop_id": info.get_id()})
            except Exception:
                pass
            return True, "launched"
        # launch() returned False: fall back to raw Exec=
        exec_line = info.get_string("Exec") or ""
        argv = _strip_exec_codes(exec_line)
        if argv:
            if info.get_boolean("Terminal"):
                argv = ["x-terminal-emulator", "-e"] + argv
            spawn_detached(argv)
            return True, "launched via Exec fallback"
        return False, "launch() returned False and no Exec= found"
    except Exception as e:
        # Last resort: raw Exec=
        try:
            exec_line = info.get_string("Exec") or ""
            argv = _strip_exec_codes(exec_line)
            if argv:
                spawn_detached(argv)
                return True, "launched via Exec fallback"
        except Exception:
            pass
        return False, str(e)


def launch_custom(exec_line: str) -> tuple[bool, str]:
    if not exec_line or not exec_line.strip():
        return False, "empty command"
    try:
        argv = shlex.split(os.path.expandvars(os.path.expanduser(exec_line)))
    except Exception as e:
        return False, f"bad command: {e}"
    if not argv:
        return False, "empty command"
    try:
        spawn_detached(argv)
        return True, "launched"
    except Exception as e:
        return False, str(e)


def launch_pin(pin: dict) -> tuple[bool, str]:
    """Entry point for AppTile. Returns (ok, message) — never raises."""
    if pin.get("desktop_id"):
        info = resolve_info(pin["desktop_id"])
        if info is None:
            if pin.get("exec"):
                ok, msg = launch_custom(pin["exec"])
                if ok:
                    note_launched(pin)
                return ok, msg
            return False, f"app not found: {pin['desktop_id']} (uninstalled or renamed?)"
        ok, msg = launch_info(info)
        if not ok and pin.get("exec"):
            ok, msg = launch_custom(pin["exec"])
            if ok:
                note_launched(pin)
        elif ok:
            note_launched(pin)
        return ok, msg
    if pin.get("exec"):
        ok, msg = launch_custom(pin["exec"])
        if ok:
            note_launched(pin)
        return ok, msg
    return False, "pin has neither desktop_id nor exec"


# -- bar-launched session tracking -------------------------------------------
# Pins/apps the user actually started from the bar this session. The Open
# section can filter to these (+ pinned apps) instead of every window.
_session_keys: set[str] = set()


def note_launched(pin: dict):
    """Remember a successful bar launch for the Open-section filter."""
    try:
        if pin.get("desktop_id"):
            _session_keys.add(pin["desktop_id"].lower())
        elif pin.get("exec"):
            prog = pin["exec"].strip().split()[0].split("/")[-1].lower()
            if prog:
                _session_keys.add("exec:" + prog)
    except Exception:
        pass


def session_keys() -> set[str]:
    return set(_session_keys)
