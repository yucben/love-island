# Source-only diagnostics

Run on the CachyOS host with its system Qt/Python, from the project directory.
These tools are not installed with the application.

```bash
/usr/bin/python diagnostics/check-session.py
/usr/bin/python diagnostics/measure-animation.py --exclusive --target-fps 144 --check
bash diagnostics/build-native-probe.sh
```

The live session check temporarily enables and restores native DND and creates/removes a test MPRIS player. It only tests a fullscreen window when already locked or explicitly passed `--fullscreen`.

The animation check temporarily restores Plasma notifications and restarts the island on exit. Do not run overlapping island surfaces: they invalidate measurements. `--minimal` reproduces the old spring timing; `--linear-minimal` uses continuous animation. A failed 144 FPS check reflects the currently unmet target.

`frameSwapped` measures application frame readiness, not hardware presentation. Shape updates measure property changes, not displayed FPS. The native C++ probe additionally supports Wayland presentation feedback. Software rendering with a precise animation clock is an experiment, not a production fix.

The native build requires the host compiler, pkg-config, wayland-scanner, Wayland development files and matching Qt private headers. It builds in a unique cache directory and prints the executable path. The protocol XML and its license are bundled in `protocols/`; no generated `/tmp` files are required.

The canonical functional suite is `PYTHONPATH=src /usr/bin/python -m unittest discover -s tests -v`. Legacy upstream tools are not included in this independent release.
