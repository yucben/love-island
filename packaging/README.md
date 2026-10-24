# Arch / AUR packaging

`aur/PKGBUILD` tracks the fixed `v0.1.0` release tag, not the moving main branch. It installs the private Python/QML application under `/usr/lib/love-island`, launchers in `/usr/bin`, a systemd **user** unit, menu entries and an XDG login entry. It does not run Python application code as root.

## Account-scoped activation

Pacman invokes `session-bridge` after installation. It prefers a valid `SUDO_UID`; without one it only chooses a single unambiguous active local KDE Wayland account. An offline sudo-invoking account is enrolled for its next login. Multiple eligible users without an invoking UID are left untouched, with instructions to run `love-island-session start` manually.

Enrollment records live in root-owned `/var/lib/love-island/users/<uid>`. The XDG entry only acts for an enrolled or explicitly enabled account, and always respects the user's persistent disabled marker. It does not automatically enroll every user on the computer.

For immediate takeover, the bridge drops privilege using `runuser` and a cleared environment before invoking the fixed `/usr/bin/love-island-session`. It never executes a launcher from a user's home as root. Notification ownership requires a short Plasma shell restart. Package transactions succeed even if activation fails; retry from the desktop terminal.

`restore` writes a persistent disabled marker and restores the original OSD key. Explicit `start` clears that marker. Upgrades only restart running instances and do not enable stopped ones. A previous source service is stopped and disabled during package activation.

## Removal and failure

`pre_remove` calls the fixed controller while its files still exist. The controller only restores users with an enabled/running instance or an explicit enabled marker; unrelated active users are left unchanged. Root enrollment records are removed. Personal configuration, notification history, OSD backup and disabled marker remain.

Crash recovery restores OSD and asks Plasma to reclaim notifications. This is best effort: a crashed user manager, session shutdown or unreachable user bus can prevent immediate restoration. From a working Plasma session, use `love-island-session restore` before removal when possible. Fresh login and physical hotplug require further hardware validation.

## Build and submit

```bash
cd packaging/aur
makepkg --printsrcinfo > .SRCINFO
makepkg -si
```

AUR receives only `PKGBUILD`, `.SRCINFO` and `love-island.install`, not the application tree or a compiled package. Publishing requires an AUR account and its registered SSH public key. Never commit a private key. The GitHub repository and tag must exist before public users can build the package.

`tools/check-package.sh` validates the staged layout without installing it or changing a session. `tests/test_packaging.py` checks account selection, privilege dropping and lifecycle guards with mocks. These do not substitute for a real pacman installation/removal check.
