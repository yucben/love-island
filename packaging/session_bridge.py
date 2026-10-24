#!/usr/bin/python
"""Pacman hook bridge: fixed commands, executed as a selected desktop user.

Never import application code or execute a file from a user's home as root.
Enrollment is root-owned; user preferences are handled after dropping privilege.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import subprocess
import sys

ENROLLMENT = Path('/var/lib/love-island/users')
CONTROLLER = '/usr/bin/love-island-session'


def active_plasma_users():
    result = subprocess.run(['/usr/bin/loginctl', 'list-sessions', '--no-legend'],
                            capture_output=True, text=True, check=True, timeout=5)
    users = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        detail = subprocess.run(['/usr/bin/loginctl', 'show-session', fields[0],
                                 '-p', 'User', '-p', 'Active', '-p', 'Remote',
                                 '-p', 'Type', '-p', 'Desktop', '-p', 'Class'],
                                capture_output=True, text=True, timeout=5)
        if detail.returncode:
            continue
        data = dict(row.split('=', 1) for row in detail.stdout.splitlines() if '=' in row)
        if (data.get('Active') == 'yes' and data.get('Remote') == 'no'
                and data.get('Type') == 'wayland' and data.get('Class') == 'user'
                and 'kde' in data.get('Desktop', '').lower().split(':')):
            uid = data.get('User', '')
            if uid.isdecimal() and int(uid) >= 1000:
                users.add(int(uid))
    return users


def installation_user(active, sudo_uid):
    """Prefer the invoking account; never choose among multiple desktop users."""
    if sudo_uid and sudo_uid.isdecimal() and int(sudo_uid) >= 1000:
        return int(sudo_uid)
    if len(active) == 1:
        return next(iter(active))
    return None


def as_user(uid, action):
    account = pwd.getpwuid(uid)
    runtime = f'/run/user/{uid}'
    command = ['/usr/bin/runuser', '-u', account.pw_name, '--', '/usr/bin/env', '-i',
               f'HOME={account.pw_dir}', f'USER={account.pw_name}',
               f'LOGNAME={account.pw_name}', 'PATH=/usr/bin:/bin',
               f'XDG_RUNTIME_DIR={runtime}', f'DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus',
               'XDG_SESSION_TYPE=wayland', 'XDG_CURRENT_DESKTOP=KDE', CONTROLLER, action]
    return subprocess.run(command, timeout=40, check=False).returncode == 0


def enrolled_users():
    if not ENROLLMENT.exists():
        return set()
    return {int(path.name) for path in ENROLLMENT.iterdir()
            if path.name.isdecimal() and int(path.name) >= 1000}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if os.geteuid() != 0 or len(argv) != 1 or argv[0] not in {'install', 'upgrade', 'remove'}:
        print('Usage (root, package manager only): session-bridge {install|upgrade|remove}', file=sys.stderr)
        return 2
    action = argv[0]
    try:
        active = active_plasma_users()
        if action == 'install':
            uid = installation_user(active, os.environ.get('SUDO_UID'))
            if uid is None:
                print('love-island: no unambiguous installing account. In Plasma Wayland, run: love-island-session start')
                return 0
            pwd.getpwuid(uid)  # validate before enrollment
            ENROLLMENT.mkdir(parents=True, mode=0o755, exist_ok=True)
            (ENROLLMENT / str(uid)).touch(mode=0o644)
            if uid in active:
                if not as_user(uid, 'start'):
                    print('love-island: immediate activation failed; use love-island-session start to retry.')
            else:
                print('love-island: enrolled installing account; starts at next Plasma Wayland login.')
        elif action == 'upgrade':
            # Explicitly enabled accounts can also be outside the initial enrollment.
            for uid in active:
                as_user(uid, 'upgrade')
        else:
            for uid in enrolled_users() | active:
                try:
                    as_user(uid, 'package-remove')
                except (KeyError, subprocess.SubprocessError, OSError) as error:
                    print(f'love-island: could not restore account {uid}: {type(error).__name__}')
            for uid in enrolled_users():
                (ENROLLMENT / str(uid)).unlink(missing_ok=True)
            if ENROLLMENT.exists():
                ENROLLMENT.rmdir()
                ENROLLMENT.parent.rmdir()
    except (KeyError, OSError, subprocess.SubprocessError) as error:
        print(f'love-island: session activation unavailable ({type(error).__name__}). '
              'Run love-island-session start inside Plasma Wayland.')
    return 0  # a failed desktop operation must not abort the package transaction


if __name__ == '__main__':
    raise SystemExit(main())
