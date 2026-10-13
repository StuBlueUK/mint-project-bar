"""Open-apps section, grouped by app: one icon tile per app.

Hovering a multi-window tile notifies the parent window via on_hover,
which expands an inline pane to the RIGHT of the rail listing that
app's windows (no popover positioning issues under layer-shell).
Left-click: single window -> focus/minimize toggle; group -> re-show pane.
Middle-click on a group: cycle focus to the next window in that group.
Right-click: per-window focus items + minimize-all / close-all / pin.
"""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from backends.running import group_windows, guess_pin
from backends.icons import safe_icon


class RunningList(Gtk.Box):
    def __init__(self, tracker, on_pin_app=None, on_hover=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.tracker = tracker
        self._on_pin_app = on_pin_app
        self._on_hover = on_hover  # fn(group or None)
        self._compact = True
        self._groups: list[dict] = []
        self.get_style_context().add_class("running-list")
        self._empty = Gtk.Label(label="No open windows")
        self._empty.get_style_context().add_class("running-empty")
        self.refresh()

    def set_hover_callback(self, fn):
        self._on_hover = fn

    def set_compact(self, compact: bool):
        if compact != self._compact:
            self._compact = compact
            self.refresh()

    def get_groups(self) -> list[dict]:
        return list(self._groups)

    def refresh(self, windows: list[dict] | None = None):
        for child in self.get_children():
            self.remove(child)
        wins = windows if windows is not None else self._safe_list()
        self._groups = group_windows(wins)
        if not self._groups:
            self.pack_start(self._empty, False, False, 2)
        for g in self._groups:
            self.pack_start(self._group_tile(g), False, False, 0)
        self.show_all()

    def _safe_list(self):
        try:
            return self.tracker.list_windows()
        except Exception:
            return []

    # -- tiles ------------------------------------------------------------------
    def _group_tile(self, group: dict) -> Gtk.Button:
        btn = Gtk.Button()
        btn.get_style_context().add_class("run-button")
        if group.get("active"):
            btn.get_style_context().add_class("run-active")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_halign(Gtk.Align.CENTER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)

        overlay = Gtk.Overlay()
        icon = Gtk.Image.new_from_icon_name(
            safe_icon(group.get("icon_name"), "application-x-executable", "image-missing"),
            Gtk.IconSize.DIALOG,
        )
        icon.set_pixel_size(36)
        overlay.add(icon)
        if group["count"] > 1:
            badge = Gtk.Label(label=str(group["count"]))
            badge.get_style_context().add_class("run-badge")
            badge.set_halign(Gtk.Align.END)
            badge.set_valign(Gtk.Align.START)
            overlay.add_overlay(badge)
        box.pack_start(overlay, False, False, 0)

        lbl = Gtk.Label(label=(group.get("label") or "?")[:14])
        lbl.set_max_width_chars(10)
        lbl.set_ellipsize(3)
        lbl.get_style_context().add_class("pin-label")
        lbl.set_visible(not self._compact)
        box.pack_start(lbl, False, False, 0)
        btn.add(box)

        tip_lines = [w.get("name", "?") for w in group["windows"][:8]]
        if group["count"] > 8:
            tip_lines.append(f"… +{group['count'] - 8} more")
        tip = f"{group['label']} ({group['count']})\n" + "\n".join(f"• {t}" for t in tip_lines)
        if group["count"] > 1:
            tip += "\nHover: windows expand right • Middle: cycle • Right: all/pin"
        else:
            tip += "\nLeft: focus • Right: close/pin"
        btn.set_tooltip_text(tip)
        btn.connect("button-press-event", self._on_press, group)
        if len(group["windows"]) > 1:
            btn.connect("enter-notify-event", self._notify_hover, group)
            btn.connect("leave-notify-event", self._notify_hover_none)
        btn.show_all()
        return btn

    def _notify_hover(self, *_args):
        group = _args[-1]
        if self._on_hover:
            try:
                self._on_hover(group)
            except Exception:
                pass
        return False

    def _notify_hover_none(self, *_args):
        if self._on_hover:
            try:
                self._on_hover(None)
            except Exception:
                pass
        return False

    # -- clicks -------------------------------------------------------------------
    def _on_press(self, _w, event, group: dict):
        if event.button == 3:
            self._popup(event, group)
            return True
        if event.button == 2:  # middle: cycle to next window in group
            self._cycle(group)
            return True
        if event.button == 1:
            wins = group["windows"]
            if len(wins) == 1:
                try:
                    self.tracker.activate(wins[0])
                except Exception:
                    pass
            elif self._on_hover:
                # touchscreens get no hover: re-show the pane explicitly
                try:
                    self._on_hover(group)
                except Exception:
                    pass
            return True
        return False

    def _cycle(self, group: dict):
        wins = group["windows"]
        if not wins:
            return
        try:
            idx = next((i for i, w in enumerate(wins) if w.get("active")), 0)
            self.tracker.activate(wins[(idx + 1) % len(wins)])
        except Exception:
            pass

    def _popup(self, event, group: dict):
        menu = Gtk.Menu()
        for w in group["windows"]:
            title = w.get("name") or "?"
            if len(title) > 40:
                title = title[:37] + "…"
            prefix = "● " if w.get("active") else "○ "
            item = Gtk.MenuItem(label=prefix + title)
            item.connect("activate", lambda _i, win=w: self.tracker.activate(win))
            item.show()
            menu.append(item)
        sep = Gtk.SeparatorMenuItem()
        sep.show()
        menu.append(sep)
        if len(group["windows"]) > 1:
            for label, fn in [
                ("Minimize all", lambda: [self.tracker.minimize(w) for w in group["windows"]]),
                ("Close all", lambda: [self.tracker.close(w) for w in group["windows"]]),
            ]:
                item = Gtk.MenuItem(label=label)
                item.connect("activate", lambda _i, f=fn: f())
                item.show()
                menu.append(item)
        else:
            w = group["windows"][0]
            for label, fn in [
                ("Minimize", lambda: self.tracker.minimize(w)),
                ("Close window", lambda: self.tracker.close(w)),
            ]:
                item = Gtk.MenuItem(label=label)
                item.connect("activate", lambda _i, f=fn: f())
                item.show()
                menu.append(item)
        if self._on_pin_app:
            pin = guess_pin(group["windows"][0])
            if pin:
                item = Gtk.MenuItem(label=f"Pin “{pin.get('name') or group.get('label')}” to sidebar")
                item.connect("activate", lambda _i: self._on_pin_app(pin))
                item.show()
                menu.append(item)
        menu.popup_at_pointer(event)

    def running_keys(self) -> list[dict]:
        return self._safe_list()
