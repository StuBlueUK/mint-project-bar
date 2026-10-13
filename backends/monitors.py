"""Monitor enumeration + target filtering.

Mode values: "all" | "primary" | "<connector e.g. DP-1>".
Connector comes from Gdk.Monitor.get_connector().
"""
from __future__ import annotations


def list_monitors(display) -> list[dict]:
    monitors = []
    n = display.get_n_monitors()
    for i in range(n):
        mon = display.get_monitor(i)
        try:
            connector = mon.get_connector() or f"MON-{i}"
        except Exception:
            connector = f"MON-{i}"
        try:
            geo = mon.get_geometry()
            geometry = (geo.x, geo.y, geo.width, geo.height)
        except Exception:
            geometry = (0, 0, 1920, 1080)
        try:
            primary = display.get_primary_monitor() == mon
        except Exception:
            primary = i == 0
        monitors.append(
            {
                "index": i,
                "monitor": mon,
                "connector": connector,
                "primary": primary,
                "geometry": geometry,
            }
        )
    return monitors


def filter_monitors(monitors: list[dict], mode: str) -> list[dict]:
    if mode == "all":
        return monitors
    if mode == "primary":
        for m in monitors:
            if m["primary"]:
                return [m]
        return monitors[:1]
    for m in monitors:
        if m["connector"] == mode:
            return [m]
    # Unknown connector (unplugged?) -> fall back to primary
    return filter_monitors(monitors, "primary")


def cycle_mode(monitors: list[dict], current: str) -> str:
    """all -> primary -> each connector -> all ... Bound to Super+Shift+S."""
    connectors = [m["connector"] for m in monitors]
    order = ["all", "primary"] + connectors
    if current not in order:
        return "primary"
    return order[(order.index(current) + 1) % len(order)]


def next_connector(monitors: list[dict], current: str) -> str:
    connectors = [m["connector"] for m in monitors]
    if not connectors:
        return current
    if current in connectors:
        return connectors[(connectors.index(current) + 1) % len(connectors)]
    # From all/primary, jump to first non-primary, else first
    for m in monitors:
        if not m["primary"]:
            return m["connector"]
    return connectors[0]
