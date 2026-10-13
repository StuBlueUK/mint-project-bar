"""Add-app dialog: pick an installed app or enter a custom command.

Returns a pin dict via callback on_add(pin). Emits nothing if cancelled.
"""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf

from backends.desktop_files import list_apps


class AddAppDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(
            title="Add app to sidebar",
            transient_for=parent,
            flags=0,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
        )
        self.set_default_size(420, 520)
        self.get_style_context().add_class("add-dialog")
        self._all_apps: list[dict] = []
        self._on_add = None
        self._build()
        self._reload_apps()

    def _build(self):
        box = self.get_content_area()
        box.set_spacing(6)
        box.set_border_width(10)

        # search
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search installed apps…")
        self.search.connect("search-changed", lambda _e: self._apply_filter())
        box.pack_start(self.search, False, False, 0)

        # app list
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(260)
        self.store = Gtk.ListStore(str, str, str, str)  # name, desktop_id, icon, exec
        self.tree = Gtk.TreeView(model=self._filtered_model())
        self.tree.set_headers_visible(False)
        self.tree.connect("row-activated", self._on_row_activated)
        col = Gtk.TreeViewColumn()
        cell_pb = Gtk.CellRendererPixbuf()
        cell_pb.set_property("stock-size", 5)  # Gtk.IconSize.DIALOG
        col.pack_start(cell_pb, False)
        col.add_attribute(cell_pb, "icon-name", 2)
        cell_tx = Gtk.CellRendererText()
        col.pack_start(cell_tx, True)
        col.add_attribute(cell_tx, "text", 0)
        self.tree.append_column(col)
        scroll.add(self.tree)
        box.pack_start(scroll, True, True, 0)

        add_btn = Gtk.Button(label="Pin selected app")
        add_btn.get_style_context().add_class("suggested-action")
        add_btn.connect("clicked", lambda _b: self._pin_selected())
        box.pack_start(add_btn, False, False, 0)

        # custom command
        frame = Gtk.Frame(label="Or custom command")
        grid = Gtk.Grid(column_spacing=6, row_spacing=6, margin=8)
        frame.add(grid)
        self.custom_name = Gtk.Entry()
        self.custom_name.set_placeholder_text("Name (e.g. VS Code)")
        self.custom_exec = Gtk.Entry()
        self.custom_exec.set_placeholder_text("Command (e.g. code ~/Projects)")
        self.custom_icon = Gtk.Entry()
        self.custom_icon.set_placeholder_text("Icon name (optional)")
        custom_btn = Gtk.Button(label="Pin custom command")
        custom_btn.connect("clicked", lambda _b: self._pin_custom())
        grid.attach(Gtk.Label(label="Name:"), 0, 0, 1, 1)
        grid.attach(self.custom_name, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Cmd:"), 0, 1, 1, 1)
        grid.attach(self.custom_exec, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="Icon:"), 0, 2, 1, 1)
        grid.attach(self.custom_icon, 1, 2, 1, 1)
        grid.attach(custom_btn, 0, 3, 2, 1)
        box.pack_start(frame, False, False, 0)

        box.show_all()

    # -- data -------------------------------------------------------------
    def _reload_apps(self):
        try:
            self._all_apps = list_apps()
        except Exception:
            self._all_apps = []
        self._apply_filter()

    def _filtered_model(self):
        self.filter_model = None
        return Gtk.TreeModelFilter(child_model=self.store)

    def _apply_filter(self):
        q = self.search.get_text().strip().lower()
        self.store.clear()
        for app in self._all_apps:
            if q and q not in app["name"].lower() and q not in app["desktop_id"].lower():
                continue
            self.store.append([app["name"], app["desktop_id"], app.get("icon") or "application-x-executable", app.get("exec") or ""])
        filt = Gtk.TreeModelFilter(child_model=self.store)
        self.tree.set_model(filt)

    def _selected_app(self):
        sel = self.tree.get_selection()
        model, it = sel.get_selected()
        if not it:
            return None
        return {
            "name": model[it][0],
            "desktop_id": model[it][1],
            "icon": model[it][2],
            "exec": model[it][3],
        }

    def _on_row_activated(self, _tree, _path, _col):
        self._pin_selected()

    def _pin_selected(self):
        app = self._selected_app()
        if not app:
            return
        pin = {"type": "app", "desktop_id": app["desktop_id"], "name": app["name"]}
        if self._on_add:
            self._on_add(pin)

    def _pin_custom(self):
        name = self.custom_name.get_text().strip() or self.custom_exec.get_text().strip()
        exec_line = self.custom_exec.get_text().strip()
        if not exec_line:
            return
        pin = {"type": "app", "exec": exec_line, "name": name}
        icon = self.custom_icon.get_text().strip()
        if icon:
            pin["icon"] = icon
        if self._on_add:
            self._on_add(pin)

    def run_with_callback(self, on_add):
        self._on_add = on_add
        self.run()
        self.destroy()
