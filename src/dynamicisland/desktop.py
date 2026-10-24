"""KWin fullscreen state, lock state, primary output and power transitions."""

from __future__ import annotations

import json
import threading

import dbus
import dbus.service
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from . import apps
from .desktop_sources import PowerMonitor, PrimaryOutputMonitor

INTERFACE = "org.dynamicisland.Desktop"
PATH = "/org/dynamicisland/Desktop"
PLUGIN = "dynamic-island-desktop"

# Observe all current-desktop fullscreen windows, not just the focused one:
# clicking a panel must not make an island appear over a fullscreen video.
SCRIPT = r"""
function report() {
    let outputs = [];
    workspace.windowList().forEach(function(w) {
        let onDesktop = w.onAllDesktops || !w.desktops || !w.desktops.length
            || w.desktops.indexOf(workspace.currentDesktop) !== -1;
        let onActivity = !w.activities || !w.activities.length
            || w.activities.indexOf(workspace.currentActivity) !== -1;
        if (w.fullScreen && !w.minimized && onDesktop && onActivity && w.output)
            outputs.push(String(w.output.name));
    });
    callDBus("%s", "/org/dynamicisland/Desktop", "org.dynamicisland.Desktop",
             "FullscreenOutputs", outputs.join("\n"));
}
function watch(w) {
    ["fullScreenChanged", "minimizedChanged", "outputChanged", "desktopsChanged",
     "activitiesChanged"].forEach(function(name) {
        if (w[name]) w[name].connect(report);
    });
}
workspace.windowList().forEach(watch);
workspace.windowAdded.connect(function(w) { watch(w); report(); });
workspace.windowRemoved.connect(report);
workspace.windowActivated.connect(report);
workspace.currentDesktopChanged.connect(report);
workspace.currentActivityChanged.connect(report);
report();
"""


class _Adaptor(dbus.service.Object):
    def __init__(self, bus, desktop):
        super().__init__(bus, PATH)
        self.desktop = desktop

    @dbus.service.method(INTERFACE, in_signature="s", out_signature="")
    def FullscreenOutputs(self, names):
        self.desktop.report_fullscreen(str(names))

    @dbus.service.method(INTERFACE, in_signature="", out_signature="s")
    def Snapshot(self):
        d = self.desktop
        state = {"primary": d.primary, "fullscreen": d.fullscreen,
                           "locked": d.locked, "dnd": d.doNotDisturb,
                           "kwinWatcher": d.watching}
        if d.state_provider:
            state.update(d.state_provider())
        return json.dumps(state)

    @dbus.service.method(INTERFACE, in_signature="", out_signature="s")
    def Capture(self):
        # Only this application's scene, never the desktop or other windows.
        return self.desktop.capture_handler() if self.desktop.capture_handler else ""


class DesktopBridge(QObject):
    changed = Signal()
    primaryChanged = Signal()
    powerChanged = Signal(bool, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._locked = True  # Fail closed until the screen saver answers.
        self._dnd = False
        self._fullscreen_outputs = set()
        self.watching = False
        self.state_provider = None
        self.capture_handler = None
        self._bus = dbus.SessionBus()
        self._adaptor = _Adaptor(self._bus, self)
        self._lock_retry = QTimer(self)
        self._lock_retry.setSingleShot(True)
        self._lock_retry.setInterval(2000)
        self._lock_retry.timeout.connect(self._read_lock)
        self._bus.add_signal_receiver(self._lock_changed, signal_name="ActiveChanged",
            dbus_interface="org.freedesktop.ScreenSaver", path="/ScreenSaver")
        self._bus.add_signal_receiver(self._screensaver_owner, signal_name="NameOwnerChanged",
            dbus_interface="org.freedesktop.DBus", arg0="org.freedesktop.ScreenSaver")
        self._read_lock()
        self._bus.add_signal_receiver(self._kwin_owner, signal_name="NameOwnerChanged",
            dbus_interface="org.freedesktop.DBus", arg0="org.kde.KWin")
        self._install_kwin()
        self._power = PowerMonitor(parent=self)
        self._power.changed.connect(self.powerChanged.emit)
        self._outputs = PrimaryOutputMonitor(QGuiApplication.instance(), self)
        self._outputs.changed.connect(self.primaryChanged.emit)
        self._outputs.changed.connect(self.changed.emit)

    def _install_kwin(self):
        destination = str(self._bus.get_unique_name())
        def install():
            self.watching = apps.run_script(SCRIPT % destination, PLUGIN, keep=True)
            print(f"[island] fullscreen watcher: {self.watching}")
        threading.Thread(target=install, daemon=True, name="island-desktop").start()

    def _kwin_owner(self, name, old, new):
        if str(new):
            QTimer.singleShot(1500, self._install_kwin)

    def _lock_changed(self, active):
        self._lock_retry.stop()
        self._locked = bool(active)
        self.changed.emit()

    def _read_lock(self):
        # At login the notification unit can precede KScreenLocker. Retry
        # asynchronously instead of remaining hidden until the first unlock.
        try:
            saver = self._bus.get_object("org.freedesktop.ScreenSaver", "/ScreenSaver", introspect=False)
            saver.GetActive(dbus_interface="org.freedesktop.ScreenSaver", timeout=2,
                reply_handler=self._lock_changed,
                error_handler=lambda error: self._lock_retry.start())
        except dbus.DBusException:
            self._lock_retry.start()

    def _screensaver_owner(self, name, old, new):
        if str(new):
            self._read_lock()
        else:
            self._locked = True
            self.changed.emit()
            self._lock_retry.start()

    def report_fullscreen(self, names):
        outputs = set(names.splitlines())
        if outputs != self._fullscreen_outputs:
            self._fullscreen_outputs = outputs
            self.changed.emit()

    @Slot(bool)
    def setDoNotDisturb(self, value):
        if value != self._dnd:
            self._dnd = value
            self.changed.emit()

    @Property(str, notify=primaryChanged)
    def primary(self):
        return self._outputs.primary

    @Property(bool, notify=changed)
    def fullscreen(self):
        return self.primary in self._fullscreen_outputs

    @Property(bool, notify=changed)
    def locked(self):
        return self._locked

    @Property(bool, notify=changed)
    def blocked(self):
        return self.locked or self.fullscreen

    @Property(bool, notify=changed)
    def doNotDisturb(self):
        return self._dnd

    @Slot()
    def stop(self):
        apps.unload_script(PLUGIN)
