# 0.1.0 validation record

Tested on CachyOS, KDE Plasma Wayland, system Qt/PySide6 6.12.0. This is a single-machine result, not a distribution compatibility guarantee.

- 26 isolated regression tests passed: notification ordering/timing, suppression, playback, QML hover modes and controls, configuration migration, account selection and package lifecycle guards.
- `package()` layout validation passed, including QML platform adapter, executable permissions and exclusion of diagnostics/tests/caches from the installed application.
- `makepkg` completed with the fixed v0.1.0 tag. Before GitHub publication, its source URL was mapped to the identical local Git repository for this test; this does not validate public download availability.
- A real pacman installation automatically activated the intended desktop account, enabled the user unit and disabled the earlier source unit.
- Live primary-output, KWin watcher, native KDE DND and MPRIS checks passed. DND and the temporary test player were restored/removed.
- A real pacman removal restored Plasma's notification ownership and the exact saved OSD setting, removed enrollment records and retained personal data.

Stable 144 FPS is not achieved. See the performance record. Full logout/login, physical monitor/power hotplug and additional distributions still need real-world validation.

GitHub and AUR publication require authenticated accounts. Local tags, source files and package builds alone do not indicate those services are live.
