"""Package lifecycle contracts without touching a real user session."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('session_bridge', ROOT / 'packaging/session_bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class PackageLifecycleTests(unittest.TestCase):
    def test_enrollment_does_not_guess_between_accounts(self):
        self.assertEqual(bridge.installation_user({1000, 1001}, '1001'), 1001)
        self.assertEqual(bridge.installation_user({1000}, None), 1000)
        self.assertIsNone(bridge.installation_user({1000, 1001}, None))
        self.assertIsNone(bridge.installation_user(set(), '0'))

    def test_bridge_drops_privilege_and_clears_environment(self):
        with patch.object(bridge.pwd, 'getpwuid') as lookup, patch.object(bridge.subprocess, 'run') as run:
            lookup.return_value.pw_name = 'desktop'
            lookup.return_value.pw_dir = '/home/desktop'
            run.return_value.returncode = 0
            self.assertTrue(bridge.as_user(1000, 'start'))
            command = run.call_args.args[0]
            self.assertEqual(command[:7], ['/usr/bin/runuser', '-u', 'desktop', '--', '/usr/bin/env', '-i', 'HOME=/home/desktop'])
            self.assertEqual(command[-2:], ['/usr/bin/love-island-session', 'start'])
            self.assertIn('DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus', command)

    def test_install_starts_only_selected_account_and_remove_uses_guard(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(bridge, 'ENROLLMENT', Path(directory) / 'state/users'), \
                patch.object(bridge.os, 'geteuid', return_value=0), \
                patch.object(bridge, 'active_plasma_users', return_value={1000, 1001}), \
                patch.object(bridge.pwd, 'getpwuid'), patch.object(bridge, 'as_user', return_value=True) as call, \
                patch.dict(os.environ, {'SUDO_UID': '1001'}):
            self.assertEqual(bridge.main(['install']), 0)
            call.assert_called_once_with(1001, 'start')
            self.assertEqual(bridge.enrolled_users(), {1001})
            call.reset_mock()
            self.assertEqual(bridge.main(['remove']), 0)
            self.assertEqual({item.args for item in call.call_args_list}, {(1000, 'package-remove'), (1001, 'package-remove')})
            self.assertFalse(bridge.ENROLLMENT.exists())

    def run_session(self, action, *, disabled=False, enabled=False):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            state = folder / '.local/state/dynamic-island'
            state.mkdir(parents=True)
            if disabled:
                (state / 'love-island-disabled').touch()
            if enabled:
                (state / 'love-island-enabled').touch()
            binary = folder / 'bin'
            binary.mkdir()
            log = folder / 'calls'
            for name in ('systemctl', 'kwriteconfig6'):
                script = binary / name
                script.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$SESSION_TEST_LOG"\nexit 1\n')
                script.chmod(0o755)
            environment = dict(os.environ, HOME=str(folder), XDG_STATE_HOME=str(folder / '.local/state'),
                               XDG_SESSION_TYPE='wayland', PATH=f'{binary}:/usr/bin:/bin', SESSION_TEST_LOG=str(log))
            result = subprocess.run(['bash', str(ROOT / 'tools/session.sh'), action], env=environment,
                                    capture_output=True, text=True, timeout=5)
            return result, log.read_text() if log.exists() else '', (state / 'love-island-disabled').exists()

    def test_login_respects_explicit_disable(self):
        result, calls, _ = self.run_session('autostart', disabled=True, enabled=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, '')

    def test_upgrade_does_not_start_an_inactive_instance(self):
        # Only the activity check fails: upgrades must respect an inactive service.
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'systemctl'
            log = Path(directory) / 'calls'
            binary.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$SESSION_TEST_LOG"\ncase "$*" in *is-active*) exit 1;; esac\n')
            binary.chmod(0o755)
            result = subprocess.run(['bash', str(ROOT / 'tools/session.sh'), 'upgrade'],
                                    env=dict(os.environ, HOME=directory, PATH=f'{directory}:/usr/bin:/bin', SESSION_TEST_LOG=str(log)),
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(' start ', log.read_text())

    def test_package_removal_leaves_unrelated_users_untouched(self):
        result, calls, disabled = self.run_session('package-remove')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(disabled)
        self.assertNotIn('stop ', calls)
        self.assertNotIn('restart ', calls)


if __name__ == '__main__':
    unittest.main()
