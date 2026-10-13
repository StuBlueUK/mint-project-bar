#!/usr/bin/env python3
"""Mint Project Bar daemon: single Gtk.Application, one Window per monitor.

Run: python3 mintprojectbar.py
Config: ~/.config/mintprojectbar/config.json (seeded from data/config.example.json)
Shortcut: Super+Shift+S cycles monitor mode (all -> primary -> DP-1 -> ...).
"""
import json
import os
import shutil
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, Gio

from backends.monitors import (
    list_monitors,
    filter_monitors,
    cycle_mode,
    next_connector,
)
from window import SidebarWindow, HAVE_LAYER_SHELL

if HAVE_LAYER_SHELL:
    from gi.repository import GtkLayerShell

APP_ID = "org.mint.projectbar"
CONFIG_DIR = os.path.expanduser("~/.config/mintprojectbar")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LEGACY_CONFIG_PATH = os.path.expanduser("~/.config/mint-sidebar/config.json")


def load_config() -> dict:
    # Migrate from old mint-sidebar path once
    if not os.path.exists(CONFIG_PATH) and os.path.exists(LEGACY_CONFIG_PATH):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            shutil.copy(LEGACY_CONFIG_PATH, CONFIG_PATH)
        except Exception:
            pass
    if not os.path.exists(CONFIG_PATH):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        here = os.path.dirname(os.path.abspath(__file__))
        example = os.path.join(here, "data", "config.example.json")
        if os.path.exists(example):
            shutil.copy(example, CONFIG_PATH)
        else:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"monitors": "all", "width": 64, "pins": []}, f, indent=2)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg.setdefault("monitors", "all")
    cfg.setdefault("width", 64)
    cfg.setdefault("pins", [])
    cfg.setdefault("open_filter", "bar")
    # expand ~/ $HOME in folder pins so example configs work on any machine
    try:
        from backends.icons import expand_folder_uri

        for pin in cfg["pins"]:
            if isinstance(pin, dict) and pin.get("type") == "folder" and pin.get("uri"):
                pin["uri"] = expand_folder_uri(pin["uri"])
    except Exception:
        pass
    return cfg


def save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


class ProjectBarApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.config = load_config()
        self.windows: dict[str, SidebarWindow] = {}
        self.add_action_with_accel("cycle-monitor", "<Super><Shift>s")
        self.add_action_with_accel("quit", "<Super>q")

    def add_action_with_accel(self, name: str, accel: str):
        action = Gio.SimpleAction.new(name, None)
        if name == "cycle-monitor":
            action.connect("activate", lambda *_: self.cycle_monitor_mode())
        elif name == "quit":
            action.connect("activate", lambda *_: self.quit())
        self.add_action(action)
        try:
            self.set_accels_for_action(f"app.{name}", [accel])
        except Exception:
            pass

    def do_activate(self):
        self.rebuild_windows()
        display = Gdk.Display.get_default()
        if display and not hasattr(self, "_mon_sig"):
            try:
                display.connect("monitors-changed", lambda *_: self.rebuild_windows())
                self._mon_sig = True
            except Exception:
                pass

    def rebuild_windows(self):
        display = Gdk.Display.get_default()
        if display is None:
            return
        monitors = list_monitors(display)
        targets = filter_monitors(monitors, self.config.get("monitors", "all"))
        wanted = {m["connector"] for m in targets}

        # Close windows on disabled monitors
        for conn in list(self.windows):
            if conn not in wanted:
                try:
                    self.windows[conn].destroy()
                except Exception:
                    pass
                del self.windows[conn]

        # Create / refresh windows on wanted monitors
        for m in targets:
            conn = m["connector"]
            win = self.windows.get(conn)
            if win is None:
                win = SidebarWindow(
                    self,
                    conn,
                    m["geometry"],
                    self.config,
                    on_pins_changed=self.on_pins_changed,
                    on_request_mode=self.set_monitor_mode,
                    on_cycle=self.cycle_monitor_mode,
                    on_open_filter=self.set_open_filter,
                )
                if HAVE_LAYER_SHELL:
                    try:
                        GtkLayerShell.set_monitor(win, m["monitor"])
                    except Exception:
                        pass
                self.windows[conn] = win
            else:
                win.set_monitor_connector(conn)
            win.present()

    # -- monitor switching (works on any monitor setup) -------------------
    def set_monitor_mode(self, mode: str):
        self.config["monitors"] = mode
        save_config(self.config)
        self.rebuild_windows()

    def cycle_monitor_mode(self, *_args):
        """Super+Shift+S: all -> primary -> each connector -> all."""
        display = Gdk.Display.get_default()
        monitors = list_monitors(display) if display else []
        if not monitors:
            return
        current = self.config.get("monitors", "all")
        # Single-window "move to next" behaviour when pinned to one monitor:
        # jump straight to the next connector instead of via all/primary.
        if current not in ("all", "primary"):
            self.set_monitor_mode(next_connector(monitors, current))
        else:
            self.set_monitor_mode(cycle_mode(monitors, current))

    def on_pins_changed(self, pins: list[dict]):
        self.config["pins"] = pins
        save_config(self.config)

    def set_open_filter(self, mode: str):
        self.config["open_filter"] = mode
        save_config(self.config)
        for win in self.windows.values():
            try:
                win.set_open_filter(mode)
            except Exception:
                pass


def main(argv=None) -> int:
    app = ProjectBarApp()
    return app.run(sys.argv if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
