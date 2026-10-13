# Mint Project Bar

Left-edge dock for Linux Mint (Cinnamon-first, MATE/Xfce compatible).
Pin folders and apps, switch between open windows, all in a glassy blue rail.

![Mint Project Bar](screenshot.png)

## Features
- **Any monitor** — one dock per screen, or pin to primary / a single connector. `Super+Shift+S` cycles.
- **Folder pins** — left-click opens Nemo, middle-click opens a terminal there, right-click for more.
- **App pins** — installed-app picker, custom commands, drag-and-drop `.desktop` files.
- **Open apps** — grouped by app; hover a stack to fan windows out to the right, click to focus.
- **Glassy blue theme** — all styling in `data/style.css`, no hardcoded colours.

## Install
```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 \
  libgtk-layer-shell0 gir1.2-wnck-3.0 python3-psutil python3-xdg
```

## Run
```bash
python3 mintprojectbar.py
```

Config lives at `~/.config/mintprojectbar/config.json` (see `data/config.example.json`).
Right-click the bar for monitor choice, `Open`-section filter (`bar` / `all`), and add/remove pins.
