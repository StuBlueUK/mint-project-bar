"""Tiny CPU/RAM footer. psutil optional — shows … when missing."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

try:
    import psutil
except Exception:
    psutil = None


class SysMon(Gtk.Label):
    def __init__(self):
        super().__init__(label="…")
        self.get_style_context().add_class("sysmon")
        GLib.timeout_add_seconds(2, self._refresh)
        self._refresh()

    def _refresh(self):
        if psutil is None:
            self.set_text("sysmon: install python3-psutil")
        else:
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
                self.set_text(f"CPU {cpu:.0f}%  MEM {mem:.0f}%")
            except Exception:
                self.set_text("…")
        return True  # keep timer
