"""Folder pin tile: left=open Nemo, middle=open Terminal, right=menu.

Failures show an error dialog (never silent) since a stale/missing path
is the #1 reason "folder not opening".
"""
import os
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, Gtk, Gdk, GLib

from backends.icons import safe_icon, expand_folder_uri
from backends.launcher import spawn_detached

# preferred terminal first; Mint ships gnome-terminal, MATE/Xfce differ
TERMINALS = [
    "gnome-terminal",
    "mate-terminal",
    "xfce4-terminal",
    "x-terminal-emulator",
    "xterm",
]


class FolderTile(Gtk.Button):
    def __init__(self, pin: dict, on_unpin=None):
        super().__init__()
        # normalise ~/ and $HOME at the edge so old configs keep working
        if pin.get("uri"):
            pin = dict(pin, uri=expand_folder_uri(pin["uri"]))
        self.pin = pin
        self._on_unpin = on_unpin
        uri = pin.get("uri", "file://" + GLib.get_home_dir())
        name = pin.get("name") or self._name_from_uri(uri)

        self.set_tooltip_text(f"{name}\n{uri}\nLeft: open • Middle: terminal • Right: menu")
        self.get_style_context().add_class("pin-button")
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.set_halign(Gtk.Align.CENTER)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        icon = Gtk.Image.new_from_icon_name(
            safe_icon(pin.get("icon"), "folder"), Gtk.IconSize.DIALOG
        )
        icon.set_pixel_size(40)
        self._label = Gtk.Label(label=name)
        self._label.set_max_width_chars(10)
        self._label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        self._label.get_style_context().add_class("pin-label")
        box.pack_start(icon, False, False, 0)
        box.pack_start(self._label, False, False, 0)
        self.add(box)

        self.connect("button-press-event", self._on_press)
        self.show_all()

    def set_compact(self, compact: bool):
        """Folder names stay visible even on the collapsed rail — every
        folder shares the same icon, so an icon-only tile is unidentifiable."""
        try:
            self._label.set_visible(True)
            self._label.set_max_width_chars(6 if compact else 10)
            ctx = self._label.get_style_context()
            btn_ctx = self.get_style_context()
            if compact:
                ctx.add_class("pin-label-small")
                btn_ctx.add_class("pin-compact")
            else:
                ctx.remove_class("pin-label-small")
                btn_ctx.remove_class("pin-compact")
        except Exception:
            pass

    def _name_from_uri(self, uri: str) -> str:
        try:
            f = Gio.File.new_for_uri(uri)
            return f.get_basename() or uri
        except Exception:
            return uri

    def _local_path(self) -> str | None:
        try:
            f = Gio.File.new_for_uri(self.pin.get("uri", ""))
            return f.get_path()
        except Exception:
            return None

    def _error(self, primary: str, secondary: str):
        try:
            toplevel = self.get_toplevel()
            parent = toplevel if isinstance(toplevel, Gtk.Window) else None
            dlg = Gtk.MessageDialog(
                transient_for=parent,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text=primary,
            )
            dlg.format_secondary_text(secondary)
            dlg.run()
            dlg.destroy()
        except Exception:
            pass

    def _open_folder(self):
        uri = self.pin.get("uri", "")
        path = self._local_path()
        if path and not os.path.exists(path):
            self._error(
                f"Folder not found: {path}",
                "It may have been moved, renamed or deleted.\n"
                "Right-click → Unpin, then drag the folder back from Nemo.",
            )
            return
        try:
            parent = self.get_toplevel()
            if isinstance(parent, Gtk.Window):
                Gtk.show_uri_on_window(parent, uri, Gdk.CURRENT_TIME)
            else:
                Gtk.show_uri(None, uri, Gdk.CURRENT_TIME)
        except Exception as e:
            self._error(f"Could not open {uri}", str(e))

    def _open_terminal(self):
        workdir = self._local_path() or GLib.get_home_dir()
        if not os.path.isdir(workdir):
            workdir = GLib.get_home_dir()
        term = None
        for t in TERMINALS:
            try:
                if GLib.find_program_in_path(t):
                    term = t
                    break
            except Exception:
                continue
        if term is None:
            self._error("No terminal found", "Install gnome-terminal or similar.")
            return
        try:
            if term == "xterm":
                spawn_detached([term], workdir)
            else:
                spawn_detached([term, f"--working-directory={workdir}"], workdir)
        except Exception as e:
            try:
                spawn_detached([term], workdir)
            except Exception:
                self._error(f"Could not open terminal in {workdir}", str(e))

    def _on_press(self, _w, event):
        if event.button == 2:  # middle click
            self._open_terminal()
            return True
        if event.button == 3:  # right click
            self._popup_menu(event)
            return True
        if event.button == 1:
            self._open_folder()
            return True
        return False

    def _popup_menu(self, event):
        menu = Gtk.Menu()
        for label, fn in [
            ("Open in Nemo", self._open_folder),
            ("Open in Terminal", self._open_terminal),
            ("Copy path", self._copy_path),
        ]:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _i, f=fn: f())
            item.show()
            menu.append(item)
        if self._on_unpin:
            item = Gtk.MenuItem(label="Unpin")
            item.connect("activate", lambda _i: self._on_unpin(self.pin))
            item.show()
            menu.append(item)
        menu.popup_at_pointer(event)

    def _copy_path(self):
        try:
            clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clip.set_text(self.pin.get("uri", ""), -1)
        except Exception:
            pass
