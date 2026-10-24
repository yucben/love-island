# Love Island: installation

An experimental Python/PySide6 + QML notification island for KDE Plasma Wayland, derived from [Dynamic-Island-Plasma-Wayland](https://github.com/teodorgross/Dynamic-Island-Plasma-Wayland). This is an independent repository; upstream MIT copyright is retained. Current version: 0.1.0.

Primarily tested on CachyOS/Arch, Plasma 6.8.1 and Qt/PySide6 6.12.0. X11 and other distributions are not validated. Stable 144 FPS is **not achieved**; long frames remain. Use distribution Qt packages rather than mixing pip Qt with system KDE plugins.

## Arch package

The intended AUR name is `love-island`. Do not assume it is available until its AUR page exists. To build the fixed release locally:

```bash
git clone https://github.com/yucben/love-island.git
cd love-island
git checkout v0.1.0
cd packaging/aur
makepkg -si
```

Installation enrolls the invoking account (`SUDO_UID` when available, otherwise only one unambiguous active local KDE Wayland user). It starts immediately in that active session and automatically at later Plasma Wayland logins. Taking over notifications restarts Plasma shell briefly. With no identifiable user, activate from the intended desktop terminal:

```bash
love-island-session start
love-island-session status
love-island-session restore
```

`restore` gives notifications and OSD back to KDE and persists across logins. Explicit `start` enables the island again. Upgrades restart only active instances. Removal attempts restoration and retains configuration/history. See [packaging](../packaging/README.md) for failure and multi-user behavior.

## Source deployment

```bash
sudo pacman -S --needed pyside6 python-dbus python-gobject layer-shell-qt plasma-workspace kwin libkscreen kconfig glib2 ripgrep
bash tools/session.sh install
```

Use `~/.local/bin/island-session {status,start,restore}` for this installation mode. The Arch package disables an active source service during migration; do not run both modes together.

## Interaction

Hover to expand and leave to collapse. Music stays visible while playing; hovering reveals previous/play/next. Right-click opens history and archives active notifications. Volume/brightness interrupt temporarily. DND archives messages silently; lock/fullscreen hide the surface. Only the primary output is used by default. History actions open the sender, not expired notification buttons. MPRIS support is required for players.

Paths retain the `dynamic-island` name for existing users: configuration under `~/.config`, history under `~/.local/share`, original OSD state and lifecycle markers under `~/.local/state`. XDG directory variables are supported. Do not publish personal notification history or configuration.

## Test

```bash
PYTHONPATH=src /usr/bin/python -m unittest discover -s tests -v
```

Tests use temporary configuration and offscreen QML. For hardware timing and live desktop checks, see [diagnostics](../diagnostics/README.md). Screenshots are synthetic test scenes. Physical hotplug and fresh-login behavior need further real-hardware validation.

Licensed under [MIT](../LICENSE), retaining Teodor Gross's original copyright. Not affiliated with Apple.
