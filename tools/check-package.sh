#!/usr/bin/env bash
# Validate package() directly against this checkout; no system writes or downloads.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
source "$root/packaging/aur/PKGBUILD"
srcdir="$work/src"
pkgdir="$work/pkg"
mkdir -p "$srcdir" "$pkgdir"
ln -s -- "$root" "$srcdir/$pkgname"
package
for item in usr/bin/love-island usr/bin/love-island-session \
    usr/lib/love-island/session-bridge usr/lib/love-island/tools/session.sh; do
    test -x "$pkgdir/$item"
done
test -f "$pkgdir/usr/lib/love-island/src/dynamicisland/qml/Platform/PlasmaSettings.qml"
test -f "$pkgdir/usr/lib/systemd/user/love-island.service"
test -f "$pkgdir/etc/xdg/autostart/love-island.desktop"
test -f "$pkgdir/usr/share/licenses/love-island/LICENSE"
test ! -e "$pkgdir/usr/lib/love-island/diagnostics"
test ! -e "$pkgdir/usr/lib/love-island/tests"
if find "$pkgdir" -type d -name __pycache__ | read -r _; then
    echo 'Unexpected Python cache in package' >&2
    exit 1
fi
echo 'PASS package layout, executable modes, QML data and runtime-only contents'
