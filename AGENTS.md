# Mint Project Bar — AGENTS.md

Left-edge dock for Linux Mint (Cinnamon-first, MATE/Xfce compatible).

## Stack
- Python 3.10+ + GTK3 + PyGObject (`gi`)
- `gtk-layer-shell` for left-edge anchoring + strut reservation (X11 + Wayland)
- `libwnck` for running-app indicators, `psutil`, `python3-xdg`
- Plain JSON config at `~/.config/mintprojectbar/config.json` (no dconf)
- Target: Mint 21.3 / 22, Cinnamon 6.x (X11-first, Wayland experimental)

## Planned layout
```
mintprojectbar/
  mintprojectbar.py      # single Gtk.Application (org.mint.projectbar), owns config + monitors
  window.py              # one Gtk.Window per enabled monitor
  widgets/
    pin_grid.py
    folder_tile.py       # Gio URI + icon + name. Left=open Nemo, middle=open Terminal `--working-directory`, right=context menu.
    app_tile.py          # launches via backends/launcher, running dot, error dialog
    add_dialog.py        # Add-app picker (installed apps + custom command)
    running_list.py      # open-windows task switcher, grouped by app (hover flyout to pick window, middle-click cycles, right-click minimize-all/close-all/pin)
    search.py
    sysmon.py
  backends/
    monitors.py          # Gdk.Display monitors-changed
    desktop_files.py     # /usr/share/applications + ~/.local/share/applications
    bookmarks.py         # ~/.config/gtk-3.0/bookmarks + Nemo
    launcher.py          # fuzzy desktop_id resolve + Exec fallback, returns (ok,msg)
    running.py           # Wnck tracker (X11), window_matches_pin + guess_pin
    icons.py             # safe_icon theme fallback + expand_folder_uri (~/$HOME)
  data/
    style.css            # glassy blue theme
    config.example.json
```

## Key behaviours
1. **Multi-monitor:** one Window per monitor. Mode in config: `all | primary | <connector e.g. DP-1>`.
   Enumerate via `Gdk.Display.get_default().get_monitor(i).get_connector()` + `get_geometry()`.
   Rebuild on `monitors-changed`. UX: prefs dropdown + `Move to next monitor` + `Super+Shift+S` to cycle.
   Anchor: `GtkLayerShell.init_for_window(win); set_anchor(LEFT, True); set_exclusive_zone(width)`.
   Collapsed 64px <-> expanded 240-260px. Modes: `none | autohide | intellihide`.
   Hovering a grouped app tile expands an inline detail pane to the right
   (Gtk.Revealer, no popover) listing that app's windows; click focuses.
   Collapsed rail is icon-only (labels hidden); expanded rail shows labels.

2. **Pins:**
   - Folders: Gio URI + icon + name. Left=open Nemo, middle=open Terminal `--working-directory`, right=context menu.
   - Apps: parse `.desktop`, allow custom `Exec=` + `Gtk.IconTheme` lookup. Running dots via Wnck.
   - Add via `+` button / right-click `Add app…` (picker + custom command), drag `.desktop` files, or `Pin` on any open window.
   - Sources: drag-drop from Nemo / Mint Menu, import GTK bookmarks.
   - Launch failures show an error dialog, never silent. Stale ids resolve fuzzily (gnome-terminal → org.gnome.Terminal).
3. **Open apps (X11/Wnck):** `Open` section lists windows; click focuses (click active = minimize), right-click close/pin.
   Desktop/dock background windows (nemo-desktop, conky) are never listed.
   `open_filter` in config: `bar` (default — only pinned + bar-launched apps) or `all`. Right-click the `Open` header to switch.

3. **Style — glassy blue:**
   - Base `rgba(23,68,140,0.55)`, highlight `rgba(140,190,255,0.25)`, border `rgba(150,200,255,0.35)`, text `#E8F1FF`.
   - CSS lives in `data/style.css`, window `set_app_paintable(True)` + RGBA visual. Requires Muffin compositing on.
   - All colours in CSS, never hardcoded in Python.

## Dev commands
```bash
# deps (Mint/Ubuntu)
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 libgtk-layer-shell0 gir1.2-wnck-3.0 python3-psutil python3-xdg

# run (once scaffolded)
python3 mintprojectbar.py

# build the .deb (output in dist/, gitignored)
./packaging/build-deb.sh 0.1.0

# lint / typecheck (use if added)
ruff check . && python3 -m py_compile $(git ls-files '*.py')
```

## Conventions for agents
- Python only, no Electron. Prefer editing existing files over creating new ones.
- GTK3, not GTK4 (XApp/Mint-Y theming).
- No secrets in repo. Config examples only, never real `~/.config` paths with user data.
- Verify with `python3 -m py_compile` before finishing. Test on X11 first, then Wayland layer-shell.
- Commit style: concise imperative (`Add monitor cycler`, `Fix strut on HDMI-0`). Never commit without explicit user request.
- Docs: keep this file + `README.md` in sync when adding modules or changing config schema.
