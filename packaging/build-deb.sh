#!/bin/sh
# Build the mint-project-bar .deb (no root needed to build).
# Usage: ./packaging/build-deb.sh [version]   (default 0.1.0)
set -eu
VERSION="${1:-0.1.0}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$HERE/dist/stage"
DEB="$HERE/dist/mint-project-bar_${VERSION}_all.deb"

rm -rf "$STAGE" "$DEB"
mkdir -p "$STAGE/DEBIAN" \
  "$STAGE/usr/share/mint-project-bar" \
  "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/etc/xdg/autostart" \
  "$STAGE/usr/share/doc/mint-project-bar"

# app payload (no caches, no git metadata)
cp "$HERE/mintprojectbar.py" "$HERE/window.py" "$STAGE/usr/share/mint-project-bar/"
cp -r "$HERE/backends" "$HERE/widgets" "$HERE/data" "$STAGE/usr/share/mint-project-bar/"
find "$STAGE/usr/share/mint-project-bar" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/usr/share/mint-project-bar" -name "*.pyc" -delete 2>/dev/null || true
chmod 644 "$STAGE/usr/share/mint-project-bar/mintprojectbar.py" "$STAGE/usr/share/mint-project-bar/window.py"

# launcher wrapper
cp "$HERE/packaging/usr-bin-mint-project-bar" "$STAGE/usr/bin/mint-project-bar"
chmod 755 "$STAGE/usr/bin/mint-project-bar"

# .desktop launcher + autostart entry
cp "$HERE/packaging/mint-project-bar.desktop" "$STAGE/usr/share/applications/"
cp "$HERE/packaging/mint-project-bar-autostart.desktop" "$STAGE/etc/xdg/autostart/"

# docs
cp "$HERE/README.md" "$STAGE/usr/share/doc/mint-project-bar/"
cp "$HERE/packaging/copyright" "$STAGE/usr/share/doc/mint-project-bar/copyright"

# control file with baked version
sed "s/^Version:.*/Version: $VERSION/" "$HERE/packaging/control" > "$STAGE/DEBIAN/control"

dpkg-deb --build "$STAGE" "$DEB"
echo "Built: $DEB"
dpkg-deb --info "$DEB"
