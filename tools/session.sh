#!/usr/bin/env bash
# Host-side lifecycle for this customised build. No privilege is needed here.
set -euo pipefail
umask 077
here="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")/.." && pwd)"
state="${XDG_STATE_HOME:-$HOME/.local/state}/dynamic-island"
target="$HOME/.local/share/dynamic-island-app"
unit_dir="$HOME/.config/systemd/user"
unit=dynamic-island.service
command="${1:-status}"
system_install=false
if [[ "$here" == /usr/lib/love-island ]]; then
    system_install=true
    unit=love-island.service
fi

snapshot_osd() {
    mkdir -p "$state"
    /usr/bin/python - "$state/original.json" "${XDG_CONFIG_HOME:-$HOME/.config}/plasmarc" <<'PYCODE'
import configparser, json, os, sys
if not os.path.exists(sys.argv[1]):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.read(sys.argv[2])
    value = parser.get('OSD', 'Enabled', fallback=None)
    with open(sys.argv[1], 'x') as handle:
        json.dump({'osd': value}, handle)
PYCODE
}


managed_stop() {
    mkdir -p "$state"
    printf '%s\n' "$$" > "$state/managed-stop"
    local result=0
    systemctl --user stop "$unit" || result=$?
    rm -f -- "$state/managed-stop"
    return "$result"
}

start_plasma() {
    if ! systemctl --user start plasma-plasmashell.service; then
        # A previous rapid deployment may have hit systemd's start limit.
        systemctl --user reset-failed plasma-plasmashell.service
        systemctl --user start plasma-plasmashell.service
    fi
}

restore_osd() {
    local original
    original="$(/usr/bin/python - "$state/original.json" <<'PY'
import json, sys
try:
    value = json.load(open(sys.argv[1])).get('osd')
except (OSError, ValueError):
    value = None
print(value if value is not None else 'unset')
PY
)"
    if [[ "$original" == unset ]]; then
        kwriteconfig6 --file plasmarc --group OSD --key Enabled --delete
    else
        kwriteconfig6 --file plasmarc --group OSD --key Enabled "$original"
    fi
}

case "$command" in
install)
    if $system_install; then
        echo 'Already installed by the package manager. Use love-island-session start.' >&2
        exit 2
    fi
    [[ ! -e /run/.containerenv ]] || { echo 'Run this command on the CachyOS host.' >&2; exit 1; }
    [[ "${XDG_SESSION_TYPE:-}" == wayland ]] || { echo 'A Wayland session is required.' >&2; exit 1; }
    /usr/bin/python -c 'from PySide6 import QtCore, QtQuick; import dbus' || {
        echo 'Install dependencies: sudo pacman -S --needed pyside6 python-dbus layer-shell-qt' >&2; exit 1;
    }
    [[ -e /usr/lib/qt6/qml/org/kde/layershell/qmldir ]] || { echo 'Missing layer-shell-qt' >&2; exit 1; }
    mkdir -p "$state/backups" "$unit_dir" "$HOME/.local/bin" "$HOME/.local/share/applications"
    backup="$(mktemp -d "$state/backups/install-XXXXXXXX")"
    for item in "$HOME/.config/plasmarc" "$HOME/.config/dynamic-island/config.json" "$unit_dir/$unit"; do
        [[ ! -f "$item" ]] || cp -a -- "$item" "$backup/$(basename "$item")"
    done
    /usr/bin/python - "$state/original.json" "$HOME/.config/plasmarc" <<'PY'
import configparser, json, os, sys
if not os.path.exists(sys.argv[1]):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.read(sys.argv[2])
    value = parser.get('OSD', 'Enabled', fallback=None)
    with open(sys.argv[1], 'w') as handle:
        json.dump({'osd': value}, handle)
PY
    # Copy to a stable directory, keeping the reviewed sources in the workspace.
    if [[ "$here" != "$target" ]]; then
        stage="$(mktemp -d "$HOME/.local/share/.dynamic-island-stage-XXXXXXXX")"
        cp -a -- "$here/src" "$here/LICENSE" "$stage/"
        mkdir -p "$stage/tools"
        cp -a -- "$here/tools/session.sh" "$here/tools/dynamic-island.service" "$stage/tools/"
        [[ ! -f "$here/CUSTOMIZATION.md" ]] || cp -a -- "$here/CUSTOMIZATION.md" "$stage/"
        if [[ -d "$target" ]]; then
            managed_stop || true
            mv -- "$target" "$backup/previous-app"
        fi
        mv -- "$stage" "$target"
    fi
    cat > "$HOME/.local/bin/dynamic-island" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$HOME/.local/share/dynamic-island-app/src"
exec /usr/bin/python -m dynamicisland "$@"
SH
    chmod 755 "$HOME/.local/bin/dynamic-island"
    ln -sfn -- "$target/tools/session.sh" "$HOME/.local/bin/island-session"
    PYTHONPATH="$target/src" /usr/bin/python - "$HOME/.config/dynamic-island/config.json" <<'PY'
import json, os, sys
path = sys.argv[1]
try:
    data = json.load(open(path))
except FileNotFoundError:
    data = {}
from dynamicisland.config import complete_settings
data = complete_settings(data)
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path+'.tmp', 'w') as handle:
    json.dump(data, handle, ensure_ascii=False, indent=2)
os.replace(path+'.tmp', path)
PY
    install -m 644 "$target/tools/dynamic-island.service" "$unit_dir/$unit"
    pacman -Q pyside6 shiboken6 python-dbus layer-shell-qt plasma-workspace > "$state/dependencies.txt"
    printf '%s\n' 'Love Island 0.1.0; based on upstream v1.0.1 50dec690461fb1519f349a85ba62c8e503228992' > "$state/source-version.txt"
    rg --files -g '*.py' -g '*.qml' -g '*.sh' -g '*.service' "$target/src" "$target/tools" \
        | sort | xargs -d '\n' sha256sum > "$state/source.sha256"
    cat > "$HOME/.local/share/applications/dynamic-island.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=灵动岛
Comment=打开灵动岛及通知中心
Exec=sh -c "$HOME/.local/bin/island-session start"
Icon=preferences-desktop-notification
Categories=Utility;
Terminal=false
DESKTOP
    cat > "$HOME/.local/share/applications/dynamic-island-restore.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=恢复 KDE 默认通知
Comment=关闭灵动岛，恢复桌面原有通知和音量亮度提示
Exec=sh -c "$HOME/.local/bin/island-session restore"
Icon=edit-undo
Categories=Utility;
Terminal=false
DESKTOP
    systemctl --user daemon-reload
    systemctl --user enable "$unit"
    printf 'Installed. Backup: %s\n' "$backup"
    exec "$target/tools/session.sh" start
    ;;
package-remove)
    if systemctl --user is-enabled --quiet "$unit" || systemctl --user is-active --quiet "$unit" || [[ -e "$state/love-island-enabled" ]]; then
        exec "$0" restore
    fi
    ;;
autostart)
    [[ "${XDG_SESSION_TYPE:-}" == wayland ]] || exit 0
    [[ ! -e "$state/love-island-disabled" ]] || exit 0
    if [[ ! -e "/var/lib/love-island/users/$(id -u)" && ! -e "$state/love-island-enabled" ]]; then
        exit 0
    fi
    exec "$0" start
    ;;
upgrade)
    # Upgrades preserve a user's explicit stop and only restart a live instance.
    systemctl --user daemon-reload
    if systemctl --user is-active --quiet "$unit"; then
        managed_stop
        exec "$0" start
    fi
    ;;
start)
    [[ "${XDG_SESSION_TYPE:-}" == wayland ]] || { echo 'A Plasma Wayland session is required.' >&2; exit 1; }
    snapshot_osd
    if $system_install; then
        # Migrate an earlier source installation without leaving two owners.
        if systemctl --user is-active --quiet dynamic-island.service; then
            printf '%s\n' "$$" > "$state/managed-stop"
            systemctl --user stop dynamic-island.service
            rm -f -- "$state/managed-stop"
            systemctl --user disable dynamic-island.service || true
        fi
    fi
    rm -f -- "$state/love-island-disabled"
    touch "$state/love-island-enabled"
    systemctl --user daemon-reload
    systemctl --user enable "$unit" >/dev/null
    if systemctl --user is-active --quiet "$unit"; then
        echo 'Dynamic Island is already running.'; exit 0
    fi
    # Release the name deterministically, with recovery on every failure path.
    trap 'start_plasma >/dev/null 2>&1 || true' EXIT
    systemctl --user stop plasma-plasmashell.service
    if ! systemctl --user start "$unit"; then
        restore_osd
        echo 'Start failed; restoring Plasma. See journalctl --user -u dynamic-island.service' >&2
        exit 1
    fi
    start_plasma
    trap - EXIT
    echo 'Dynamic Island is running.'
    ;;
restore|stop)
    mkdir -p "$state"
    touch "$state/love-island-disabled"
    rm -f -- "$state/love-island-enabled"
    managed_stop || true
    systemctl --user disable "$unit" || true
    restore_osd
    if systemctl --user is-active --quiet graphical-session.target; then
        systemctl --user restart plasma-plasmashell.service
    fi
    echo 'KDE notifications and original system prompts restored. History preserved.'
    ;;
prepare-osd)
    snapshot_osd
    kwriteconfig6 --file plasmarc --group OSD --key Enabled false
    ;;
recover)
    # Also runs after a crash, so losing this process never strands notifications.
    restore_osd
    if [[ -f "$state/managed-stop" ]]; then
        read -r manager_pid < "$state/managed-stop" || manager_pid=""
        if [[ "$manager_pid" =~ ^[0-9]+$ ]] && kill -0 "$manager_pid" 2>/dev/null; then
            exit 0  # The lifecycle command restarts Plasma exactly once.
        fi
    fi
    if systemctl --user is-active --quiet graphical-session.target; then
        systemctl --user --no-block restart plasma-plasmashell.service
    fi
    ;;
status)
    systemctl --user --no-pager status "$unit" || true
    busctl --user --no-pager status org.freedesktop.Notifications | head -12
    ;;
*)
    echo 'Usage: love-island-session {install|start|restore|status|autostart|upgrade}' >&2
    exit 2
    ;;
esac
