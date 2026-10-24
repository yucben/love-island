"""Adapters for power transitions and KScreen's primary-output selection."""
from __future__ import annotations

import json

import dbus
from PySide6.QtCore import QObject, QProcess, QTimer, Signal


def select_primary_output(outputs, fallback=""):
    """Choose the highest-priority enabled connector, ignoring stale entries."""
    enabled = [output for output in outputs if output.get("enabled")
               and output.get("connected") and output.get("name")]
    def priority(output):
        try:
            return int(output.get("priority") or 999)
        except (TypeError, ValueError):
            return 999
    return str(min(enabled, key=priority)["name"]) if enabled else fallback


class PowerMonitor(QObject):
    changed = Signal(bool, int)

    def __init__(self, bus=None, parent=None):
        super().__init__(parent)
        self._on_battery = None
        self._bus = None
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(150)
        self._settle.timeout.connect(self.refresh)
        try:
            self._bus = dbus.SystemBus() if bus is None else bus
            self._bus.add_signal_receiver(lambda *args: self._settle.start(),
                signal_name="PropertiesChanged", dbus_interface="org.freedesktop.DBus.Properties",
                bus_name="org.freedesktop.UPower")
            self.refresh()
        except dbus.DBusException as error:
            print(f"[island] power state unavailable: {error}")

    def refresh(self):
        if self._bus is None:
            return
        try:
            root = self._bus.get_object("org.freedesktop.UPower", "/org/freedesktop/UPower")
            on_battery = bool(root.Get("org.freedesktop.UPower", "OnBattery",
                dbus_interface="org.freedesktop.DBus.Properties", timeout=1))
            battery = self._bus.get_object("org.freedesktop.UPower", "/org/freedesktop/UPower/devices/DisplayDevice")
            values = battery.GetAll("org.freedesktop.UPower.Device",
                dbus_interface="org.freedesktop.DBus.Properties", timeout=1)
            percentage = round(float(values.get("Percentage", 0))) if values.get("IsPresent") else -1
            if self._on_battery is not None and self._on_battery != on_battery:
                self.changed.emit(not on_battery, percentage)
            self._on_battery = on_battery
        except dbus.DBusException as error:
            print(f"[island] cannot read power: {error}")


class PrimaryOutputMonitor(QObject):
    changed = Signal()

    def __init__(self, application, parent=None):
        super().__init__(parent)
        self._application = application
        self._primary = self._fallback()
        self._process = QProcess(self)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(lambda *_: self._set_primary(self._fallback()))
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(2000)
        self._timeout.timeout.connect(self._process.kill)
        self._poll = QTimer(self)
        self._poll.setInterval(3000)
        self._poll.timeout.connect(self.refresh)
        self._poll.start()
        application.primaryScreenChanged.connect(lambda *_: self.refresh())
        application.screenAdded.connect(lambda *_: self.refresh())
        application.screenRemoved.connect(lambda *_: self.refresh())
        self.refresh()

    @property
    def primary(self):
        return self._primary

    def _fallback(self):
        screen = self._application.primaryScreen()
        return screen.name() if screen else ""

    def _set_primary(self, name):
        if name != self._primary:
            self._primary = name
            self.changed.emit()

    def refresh(self):
        if self._process.state() == QProcess.NotRunning:
            self._process.start("kscreen-doctor", ["-j"])
            self._timeout.start()

    def _finished(self, code, status):
        self._timeout.stop()
        try:
            data = json.loads(bytes(self._process.readAllStandardOutput()))
            self._set_primary(select_primary_output(data.get("outputs", []), self._fallback()))
        except (ValueError, TypeError, AttributeError):
            self._set_primary(self._fallback())
