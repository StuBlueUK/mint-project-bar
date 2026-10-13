"""One left-edge dock window per enabled monitor."""
import os
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAVE_LAYER_SHELL = True
except (ValueError, ImportError):
    GtkLayerShell = None  # type: ignore
    HAVE_LAYER_SHELL = False

from widgets.pin_grid import PinGrid
from widgets.search import SearchBar
from widgets.sysmon import SysMon
from widgets.add_dialog import AddAppDialog
from widgets.running_list import RunningList
from widgets.app_tile import AppTile
from backends.running import get_shared_tracker, window_matches_pin, window_is_bar_app
from backends.launcher import session_keys
from backends.icons import safe_icon

COLLAPSED_W = 64
EXPANDED_W = 248
DETAIL_W = 220
DETAIL_HIDE_MS = 900


def _load_css():
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(here, "data", "style.css"),
        os.path.join(here, "..", "data", "style.css"),
    ):
        if os.path.exists(candidate):
            css_path = candidate
            break
    else:
        return
    provider = Gtk.CssProvider()
    try:
        provider.load_from_path(css_path)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
    except Exception:
        pass


class SidebarWindow(Gtk.Window):
    def __init__(self, app, connector: str, geometry: tuple, config: dict,
                 on_pins_changed=None, on_request_mode=None, on_cycle=None,
                 on_open_filter=None):
        super().__init__(application=app)
        self.connector = connector
        self.config = config
        self._on_pins_changed = on_pins_changed
        self._on_request_mode = on_request_mode
        self._on_cycle = on_cycle
        self._on_open_filter = on_open_filter
        self.expanded = False
        self._detail_key: str | None = None
        self._hide_timer = 0
        self._show_timer = 0
        self.tracker = get_shared_tracker()
        try:
            self.tracker.connect(lambda: GLib.idle_add(self.refresh_running))
        except Exception:
            pass

        _load_css()
        self.set_name("sidebar")
        self.set_title(f"Mint Project Bar — {connector}")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_below(True)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.stick()

        # Transparency for glassy look (needs Muffin compositing on)
        self.set_app_paintable(True)
        try:
            visual = self.get_screen().get_rgba_visual()
            if visual:
                self.set_visual(visual)
        except Exception:
            pass

        width = int(config.get("width", COLLAPSED_W))
        x, y, _mw, mh = geometry
        self.set_default_size(width, mh)

        if HAVE_LAYER_SHELL:
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_namespace(self, "mintprojectbar")
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_exclusive_zone(self, width)
        else:
            # X11 fallback: pin to left edge of this monitor's geometry
            try:
                self.move(x, y)
            except Exception:
                pass

        self._build()
        self.connect("button-press-event", self._on_background_press)
        # Poll as fallback: Wnck signals can be missed on rapid open/close
        try:
            GLib.timeout_add_seconds(2, self._poll_running)
        except Exception:
            pass

    # -- UI ---------------------------------------------------------------
    def _build(self):
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add(hbox)

        # --- icon rail (left) ---
        rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        rail.get_style_context().add_class("sidebar-root")
        hbox.pack_start(rail, False, False, 0)

        self.search = SearchBar()
        rail.pack_start(self.search, False, False, 4)

        # Single scroll area for pins + Open section: everything flows
        # top-down with no dead gap; footer stays fixed at the bottom.
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.get_style_context().add_class("pin-scroll")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.add(content)
        self.pin_grid = PinGrid(
            self.config.get("pins", []), on_change=self._pins_changed
        )
        content.pack_start(self.pin_grid, False, False, 0)

        # Open apps (task switcher, one icon tile per app)
        open_event = Gtk.EventBox()
        open_event.set_tooltip_text("Right-click to choose which windows are shown")
        open_label = Gtk.Label(label="Open")
        open_label.get_style_context().add_class("section-label")
        self.open_label = open_label
        open_event.add(open_label)
        open_event.connect("button-press-event", self._on_open_header_press)
        content.pack_start(open_event, False, False, 0)
        self.open_event = open_event
        self.running_list = RunningList(
            self.tracker, on_pin_app=self._pin_app, on_hover=self._on_group_hover
        )
        content.pack_start(self.running_list, False, False, 0)
        rail.pack_start(scroll, True, True, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        footer.get_style_context().add_class("sidebar-footer")
        footer.pack_start(SysMon(), False, False, 0)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_btn = Gtk.Button.new_from_icon_name("list-add", Gtk.IconSize.MENU)
        add_btn.set_tooltip_text("Add app to sidebar")
        add_btn.get_style_context().add_class("footer-btn")
        add_btn.connect("clicked", lambda _b: self.open_add_dialog())
        bar.pack_start(add_btn, True, True, 0)

        expand_btn = Gtk.Button.new_from_icon_name("view-expand", Gtk.IconSize.MENU)
        expand_btn.set_tooltip_text("Expand / collapse")
        expand_btn.get_style_context().add_class("footer-btn")
        expand_btn.connect("clicked", lambda _b: self.toggle_expand())
        bar.pack_start(expand_btn, True, True, 0)

        next_btn = Gtk.Button.new_from_icon_name("go-next", Gtk.IconSize.MENU)
        next_btn.set_tooltip_text("Move to next monitor (Super+Shift+S)")
        next_btn.get_style_context().add_class("footer-btn")
        next_btn.connect("clicked", lambda _b: self._emit_cycle())
        bar.pack_start(next_btn, True, True, 0)
        footer.pack_start(bar, False, False, 0)
        rail.pack_start(footer, False, False, 4)

        # --- detail pane (right): expands on group hover ---
        self.detail_revealer = Gtk.Revealer()
        try:
            self.detail_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_RIGHT)
            self.detail_revealer.set_transition_duration(150)
        except Exception:
            pass
        self.detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.detail_box.get_style_context().add_class("detail-pane")
        self.detail_box.set_size_request(DETAIL_W, -1)
        self.detail_revealer.add(self.detail_box)
        self.detail_revealer.set_reveal_child(False)
        hbox.pack_start(self.detail_revealer, False, False, 0)
        # hovering the pane itself keeps it open
        try:
            self.detail_box.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        except Exception:
            pass
        self.detail_box.connect("enter-notify-event", lambda *_a: self._cancel_hide())
        self.detail_box.connect("leave-notify-event", lambda *_a: self._schedule_hide())

        self.show_all()
        self._apply_width()
        self.refresh_running()

    def _pins_changed(self, pins: list[dict]):
        if self._on_pins_changed:
            self._on_pins_changed(pins)
        try:
            self.refresh_running()
        except Exception:
            pass

    def _pin_app(self, pin: dict):
        try:
            self.pin_grid.add_pin(pin)
        except Exception:
            pass

    def _emit_cycle(self):
        if self._on_cycle:
            self._on_cycle()

    # -- add-app ------------------------------------------------------------
    def open_add_dialog(self):
        try:
            dlg = AddAppDialog(self)
            dlg.run_with_callback(self._pin_app)
        except Exception:
            pass

    # -- running windows ------------------------------------------------------
    def _poll_running(self):
        try:
            self.refresh_running()
        except Exception:
            pass
        return True  # keep timer

    def refresh_running(self):
        try:
            wins = self.tracker.list_windows()
        except Exception:
            wins = []
        # 'bar' filter: only windows of pinned / bar-launched apps (hides
        # conky, nemo-desktop and stuff started elsewhere)
        if self.config.get("open_filter", "bar") == "bar":
            try:
                shown = [
                    w for w in wins
                    if window_is_bar_app(w, self.config.get("pins", []), session_keys())
                ]
            except Exception:
                shown = wins
        else:
            shown = wins
        self._shown_wins = shown
        try:
            self.running_list.refresh(shown)
        except Exception:
            pass
        # running dots on pinned app tiles
        try:
            for child in self.pin_grid.get_children():
                if isinstance(child, AppTile):
                    running = any(window_matches_pin(w, child.pin) for w in wins)
                    child.set_running(running)
        except Exception:
            pass
        # keep an open detail pane in sync (hide if its app closed everything)
        if self._detail_key is not None:
            try:
                from backends.running import group_windows

                groups = {g["key"]: g for g in group_windows(self._shown_wins)}
                g = groups.get(self._detail_key)
                if g is None:
                    self._hide_detail()
                else:
                    self._fill_detail(g)
            except Exception:
                pass
        return False  # for idle_add: run once

    # -- Open-section filter (bar apps only <-> all windows) ----------------------
    def _on_open_header_press(self, _w, event):
        if event.button == 3:
            menu = Gtk.Menu()
            current = self.config.get("open_filter", "bar")
            for label, mode in [
                ("Show bar apps only", "bar"),
                ("Show all open windows", "all"),
            ]:
                item = Gtk.MenuItem(label=("● " if mode == current else "○ ") + label)
                item.connect(
                    "activate",
                    lambda _i, m=mode: self._on_open_filter(m) if self._on_open_filter else None,
                )
                item.show()
                menu.append(item)
            menu.popup_at_pointer(event)
            return True
        return False

    def set_open_filter(self, mode: str):
        self.config["open_filter"] = mode
        self.refresh_running()

    # -- hover detail pane (expands to the right) -------------------------------
    def _on_group_hover(self, group: dict | None):
        if group is None:
            self._cancel_show()
            self._schedule_hide()
            return
        # already showing this app: just stay open
        if group["key"] == self._detail_key:
            self._cancel_hide()
            self._cancel_show()
            return
        self._cancel_hide()
        self._cancel_show()
        # short delay so sweeping the mouse across the rail doesn't flash
        try:
            self._show_timer = GLib.timeout_add(150, self._show_timeout, group)
        except Exception:
            self._show_detail(group)

    def _show_timeout(self, group: dict):
        self._show_timer = 0
        self._show_detail(group)
        return False

    def _cancel_show(self):
        if getattr(self, "_show_timer", 0):
            try:
                GLib.source_remove(self._show_timer)
            except Exception:
                pass
            self._show_timer = 0

    def _show_detail(self, group: dict):
        self._detail_key = group["key"]
        self._fill_detail(group)
        try:
            self.detail_revealer.set_reveal_child(True)
        except Exception:
            pass
        self._update_strut()

    def _fill_detail(self, group: dict):
        for child in self.detail_box.get_children():
            self.detail_box.remove(child)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.get_style_context().add_class("detail-header")
        icon = Gtk.Image.new_from_icon_name(
            safe_icon(group.get("icon_name"), "application-x-executable"),
            Gtk.IconSize.DIALOG,
        )
        icon.set_pixel_size(28)
        header.pack_start(icon, False, False, 0)
        title = Gtk.Label(label=f"{group.get('label')} ({group.get('count')})", xalign=0.0)
        title.get_style_context().add_class("detail-title")
        title.set_ellipsize(3)
        header.pack_start(title, True, True, 0)
        if group.get("count", 0) > 1:
            close_all = Gtk.Button(label="Close all")
            close_all.get_style_context().add_class("detail-action")
            close_all.connect(
                "clicked",
                lambda _b, wins=list(group["windows"]): [self.tracker.close(w) for w in wins],
            )
            close_all.connect("enter-notify-event", lambda *_a: self._cancel_hide())
            close_all.connect("leave-notify-event", lambda *_a: self._schedule_hide())
            header.pack_start(close_all, False, False, 0)
        self.detail_box.pack_start(header, False, False, 4)
        for w in group["windows"]:
            self.detail_box.pack_start(self._detail_row(w), False, False, 0)
        hint = Gtk.Label(label="Click a window to focus it")
        hint.get_style_context().add_class("detail-hint")
        self.detail_box.pack_start(hint, False, False, 4)
        self.detail_box.show_all()

    def _detail_row(self, win: dict) -> Gtk.Button:
        row = Gtk.Button()
        row.get_style_context().add_class("flyout-row")
        if win.get("active"):
            row.get_style_context().add_class("flyout-row-active")
        row.set_relief(Gtk.ReliefStyle.NONE)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        dot = Gtk.Label(label="●" if win.get("active") else "○")
        dot.get_style_context().add_class("flyout-dot")
        box.pack_start(dot, False, False, 0)
        title = win.get("name") or "?"
        if len(title) > 38:
            title = title[:35] + "…"
        lbl = Gtk.Label(label=title, xalign=0.0)
        lbl.set_ellipsize(3)
        lbl.set_max_width_chars(28)
        lbl.get_style_context().add_class("flyout-label")
        box.pack_start(lbl, True, True, 0)
        row.add(box)
        row.set_tooltip_text(win.get("name", "?"))
        row.connect("clicked", lambda _b, w=win: self._focus_window(w))
        # rows are the real hover targets inside the pane: entering one
        # must cancel a pending hide, leaving the last one re-arms it
        row.connect("enter-notify-event", lambda *_a: self._cancel_hide())
        row.connect("leave-notify-event", lambda *_a: self._schedule_hide())
        row.show_all()
        return row

    def _focus_window(self, win: dict):
        try:
            self.tracker.activate(win)
        except Exception:
            pass

    def _schedule_hide(self):
        self._cancel_hide()
        try:
            self._hide_timer = GLib.timeout_add(DETAIL_HIDE_MS, self._hide_timeout)
        except Exception:
            pass

    def _hide_timeout(self):
        self._hide_timer = 0
        self._hide_detail()
        return False

    def _cancel_hide(self):
        if self._hide_timer:
            try:
                GLib.source_remove(self._hide_timer)
            except Exception:
                pass
            self._hide_timer = 0
        return False

    def _hide_detail(self):
        self._cancel_show()
        self._detail_key = None
        try:
            self.detail_revealer.set_reveal_child(False)
        except Exception:
            pass
        self._update_strut()

    def _rail_width(self) -> int:
        return EXPANDED_W if self.expanded else int(self.config.get("width", COLLAPSED_W))

    def _update_strut(self):
        w = self._rail_width()
        if self._detail_key is not None:
            w += DETAIL_W
        try:
            self.resize(w, self.get_allocated_height() or 800)
            if HAVE_LAYER_SHELL:
                GtkLayerShell.set_exclusive_zone(self, w)
        except Exception:
            pass

    # -- expand / collapse -------------------------------------------------
    def toggle_expand(self):
        self.expanded = not self.expanded
        self._apply_width()

    def _apply_width(self):
        w = self._rail_width()
        compact = (not self.expanded) and w <= 80
        try:
            self.pin_grid.set_compact(compact)
        except Exception:
            pass
        try:
            self.running_list.set_compact(compact)
        except Exception:
            pass
        try:
            self.open_event.set_visible(not compact)
        except Exception:
            pass
        self.search.set_visible(self.expanded or int(self.config.get("width", COLLAPSED_W)) > 100)
        self._update_strut()

    # -- background context menu -------------------------------------------
    def _on_background_press(self, _w, event):
        if event.button == 3:
            self._popup_menu(event)
            return True
        return False

    def _popup_menu(self, event):
        menu = Gtk.Menu()
        add = Gtk.MenuItem(label="Add app…")
        add.connect("activate", lambda _i: self.open_add_dialog())
        add.show()
        menu.append(add)
        sep_pin = Gtk.MenuItem(label="Add separator")
        sep_pin.connect("activate", lambda _i: self._pin_app({"type": "separator"}))
        sep_pin.show()
        menu.append(sep_pin)
        sep = Gtk.SeparatorMenuItem()
        sep.show()
        menu.append(sep)
        for label, mode in [
            ("Show on all monitors", "all"),
            ("Show on primary only", "primary"),
            (f"Show only here ({self.connector})", self.connector),
        ]:
            item = Gtk.MenuItem(label=label)
            item.connect(
                "activate",
                lambda _i, m=mode: self._on_request_mode(m) if self._on_request_mode else None,
            )
            item.show()
            menu.append(item)
        sep2 = Gtk.SeparatorMenuItem()
        sep2.show()
        menu.append(sep2)
        nxt = Gtk.MenuItem(label="Move to next monitor (Super+Shift+S)")
        nxt.connect("activate", lambda _i: self._emit_cycle())
        nxt.show()
        menu.append(nxt)
        exp = Gtk.MenuItem(label="Expand / collapse")
        exp.connect("activate", lambda _i: self.toggle_expand())
        exp.show()
        menu.append(exp)
        menu.popup_at_pointer(event)

    def set_monitor_connector(self, connector: str):
        self.connector = connector
        self.set_title(f"Mint Project Bar — {connector}")
