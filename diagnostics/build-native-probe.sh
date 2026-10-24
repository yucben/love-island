#!/usr/bin/env bash
# Source-only diagnostic. Qt private headers are deliberately not a runtime dependency.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cache="${XDG_CACHE_HOME:-$HOME/.cache}/dynamic-island-diagnostics"
mkdir -p "$cache"
build="$(mktemp -d "$cache/native-XXXXXXXX")"
qt_version="$(pkg-config --modversion Qt6Gui)"
qt_include="$(pkg-config --variable=includedir Qt6Gui)"
wayland-scanner client-header "$here/protocols/presentation-time.xml" "$build/island-presentation-time.h"
wayland-scanner private-code "$here/protocols/presentation-time.xml" "$build/island-presentation-time.c"
cc -fPIC -c "$build/island-presentation-time.c" -o "$build/protocol.o" $(pkg-config --cflags wayland-client)
c++ -O2 -fPIC -std=c++17 -I"$build" \
    -I"$qt_include/QtGui/$qt_version" -I"$qt_include/QtGui/$qt_version/QtGui" \
    -I"$qt_include/QtCore/$qt_version" -I"$qt_include/QtCore/$qt_version/QtCore" \
    "$here/native-frame-probe.cpp" "$build/protocol.o" -o "$build/native-frame-probe" \
    $(pkg-config --cflags --libs Qt6Quick Qt6Qml Qt6Gui wayland-client)
printf '%s\n' "$build/native-frame-probe"
