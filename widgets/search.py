"""Top search entry: fuzzy filter of app names, Enter launches first match."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Gio


class SearchBar(Gtk.Entry):
    def __init__(self):
        super().__init__()
        self.set_placeholder_text("Search apps…")
        self.get_style_context().add_class("sidebar-search")
        self.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search")
        self.connect("activate", self._on_activate)

    def _on_activate(self, _entry):
        query = self.get_text().strip().lower()
        if not query:
            return
        from backends.launcher import launch_info

        for info in Gio.DesktopAppInfo.get_all():
            try:
                if info.get_nodisplay():
                    continue
                name = (info.get_display_name() or "").lower()
                if query in name or query in (info.get_id() or "").lower():
                    launch_info(info)
                    self.set_text("")
                    return
            except Exception:
                continue
