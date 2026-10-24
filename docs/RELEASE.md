Love Island 0.1.0 is an experimental island notification surface for KDE Plasma Wayland, primarily tested on CachyOS/Arch.

- Persistent capsule, hover expansion, media controls and notification history.
- Foreground FIFO countdowns, volume/brightness feedback, DND and lock/fullscreen suppression.
- Account-scoped Arch packaging with immediate activation, login startup and KDE restoration.
- Python/PySide6 + QML; C++ diagnostics are not runtime dependencies.

**Stable 144 FPS is not achieved.** Long frames remain. Other distributions, fresh-login scenarios and physical hotplug need further testing.

See README.md and docs/INSTALL.en.md before installation: activation takes notification ownership and briefly restarts Plasma shell. The existence of these packaging files does not imply the package has already been submitted to AUR.

Derived from teodorgross/Dynamic-Island-Plasma-Wayland v1.0.1, preserving the original MIT license. This is an independent repository, not a GitHub Fork.
