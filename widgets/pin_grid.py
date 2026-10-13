"""Vertical pin list: folders + apps + separators. Accepts Nemo drops."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Gdk

from widgets.folder_tile import FolderTile
from widgets.app_tile import AppTile


class PinGrid(Gtk.Box):
    def __init__(self, pins: list[dict], on_change=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._pins = list(pins)
        self._on_change = on_change
        self._compact = True  # collapsed 64px rail starts icon-only
        self.set_border_width(6)
        self._rebuild()
        # Drag-drop from Nemo: accept file URIs -> add folder pins
        self.drag_dest_set(
            Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY,
        )
        self.drag_dest_add_uri_targets()
        self.connect("drag-data-received", self._on_drop)

    def _rebuild(self):
        for child in self.get_children():
            self.remove(child)
        for pin in self._pins:
            kind = pin.get("type")
            if kind == "separator":
                self.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 4)
            elif kind == "folder":
                tile = FolderTile(pin, on_unpin=self.remove_pin)
                tile.set_compact(self._compact)
                self.pack_start(tile, False, False, 0)
            elif kind == "app":
                tile = AppTile(pin, on_unpin=self.remove_pin)
                tile.set_compact(self._compact)
                self.pack_start(tile, False, False, 0)
        self.show_all()

    def set_compact(self, compact: bool):
        """Icon-only tiles when the rail is collapsed."""
        self._compact = compact
        for child in self.get_children():
            try:
                child.set_compact(compact)
            except AttributeError:
                pass

    def _on_drop(self, _w, _ctx, _x, _y, data, _info, _time):
        import os
        from urllib.parse import unquote
        from urllib.request import url2pathname

        for uri in data.get_uris():
            # .desktop file dropped (e.g. from /usr/share/applications or Menu)
            # -> pin as app instead of folder
            try:
                if uri.endswith(".desktop"):
                    desktop_id = os.path.basename(uri)
                    self.add_pin({"type": "app", "desktop_id": desktop_id})
                    continue
                # local file path that is a .desktop file
                if uri.startswith("file://"):
                    path = url2pathname(uri[len("file://"):])
                    path = unquote(path)
                    if path.endswith(".desktop"):
                        self.add_pin({"type": "app", "desktop_id": os.path.basename(path)})
                        continue
            except Exception:
                pass
            self.add_pin({"type": "folder", "uri": uri})

    def add_pin(self, pin: dict):
        self._pins.append(pin)
        self._rebuild()
        if self._on_change:
            self._on_change(self._pins)

    def remove_pin(self, pin: dict):
        if pin in self._pins:
            self._pins.remove(pin)
            self._rebuild()
            if self._on_change:
                self._on_change(self._pins)

    def get_pins(self) -> list[dict]:
        return list(self._pins)
