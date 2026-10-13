"""App pin tile: launches .desktop id or custom Exec=.

Uses backends.launcher so stale ids (e.g. gnome-terminal.desktop vs
org.gnome.Terminal.desktop) resolve fuzzily and failures show an error
dialog instead of silently doing nothing.
"""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, Gtk

from backends.launcher import resolve_info, icon_for_info, launch_pin
from backends.icons import safe_icon


class AppTile(Gtk.Button):
    # key used to match running windows to this pin
    match_key: str = ""

    def __init__(self, pin: dict, on_unpin=None):
        super().__init__()
        self.pin = pin
        self._on_unpin = on_unpin
        name = pin.get("name") or pin.get("desktop_id") or pin.get("exec") or "App"
        info = None
        if pin.get("desktop_id"):
            try:
                info = resolve_info(pin["desktop_id"])
                if info and info.get_display_name():
                    name = pin.get("name") or info.get_display_name()
            except Exception:
                info = None
        self._display_name = name
        # remember resolved id so running-dot matching survives renames
        try:
            self.match_key = (info.get_id().lower() if info else (pin.get("desktop_id") or "").lower())
        except Exception:
            self.match_key = (pin.get("desktop_id") or "").lower()

        missing = pin.get("desktop_id") and info is None and not pin.get("exec")
        tip = f"{name}"
        if missing:
            tip += f"\n⚠ not found: {pin.get('desktop_id')}"
        tip += "\nClick: launch • Right: menu"
        self.set_tooltip_text(tip)
        self.get_style_context().add_class("pin-button")
        if missing:
            self.get_style_context().add_class("pin-missing")
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.set_halign(Gtk.Align.CENTER)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        raw_icon = pin.get("icon") or (icon_for_info(info) if info else None)
        icon = Gtk.Image.new_from_icon_name(
            safe_icon(raw_icon, "application-x-executable", "image-missing"),
            Gtk.IconSize.DIALOG,
        )
        icon.set_pixel_size(40)
        self._label = Gtk.Label(label=name)
        self._label.set_max_width_chars(10)
        self._label.set_ellipsize(3)
        self._label.get_style_context().add_class("pin-label")
        box.pack_start(icon, False, False, 0)
        box.pack_start(self._label, False, False, 0)
        self.dot = Gtk.Label(label="●")
        self.dot.get_style_context().add_class("running-dot")
        self.dot.set_no_show_all(True)
        box.pack_start(self.dot, False, False, 0)
        self.add(box)

        self.connect("button-press-event", self._on_press)
        self.show_all()

    def set_compact(self, compact: bool):
        """Icon-only rail when the bar is collapsed."""
        try:
            self._label.set_visible(not compact)
        except Exception:
            pass

    def launch(self):
        ok, msg = launch_pin(self.pin)
        if not ok:
            self._show_error(msg)
        return ok

    def _show_error(self, msg: str):
        try:
            dlg = Gtk.MessageDialog(
                transient_for=self.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text=f"Could not launch “{self._display_name}”.",
            )
            dlg.format_secondary_text(
                f"{msg}\n\nRight-click → Unpin, then + Add app to re-pin it."
            )
            dlg.run()
            dlg.destroy()
        except Exception:
            pass

    def _on_press(self, _w, event):
        if event.button == 3:
            self._popup_menu(event)
            return True
        if event.button == 1:
            self.launch()
            return True
        return False

    def _popup_menu(self, event):
        menu = Gtk.Menu()
        launch = Gtk.MenuItem(label="Launch")
        launch.connect("activate", lambda _i: self.launch())
        launch.show()
        menu.append(launch)
        if self._on_unpin:
            unpin = Gtk.MenuItem(label="Unpin")
            unpin.connect("activate", lambda _i: self._on_unpin(self.pin))
            unpin.show()
            menu.append(unpin)
        menu.popup_at_pointer(event)

    def set_running(self, running: bool):
        self.dot.set_visible(running)
