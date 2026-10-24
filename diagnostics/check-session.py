#!/usr/bin/env python3
"""Live integration checks; restore native DND and remove the temporary player/window."""
import json
import os
import subprocess
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)
import dbus
import dbus.service
from PySide6.QtCore import QMetaObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
from dynamicisland import glibpump

app = QGuiApplication([])
glibpump.install(app)
bus = dbus.SessionBus()


def snapshot():
    return json.loads(str(bus.call_blocking("org.freedesktop.Notifications",
        "/org/dynamicisland/Desktop", "org.dynamicisland.Desktop", "Snapshot", "", (), timeout=2)))


initial = snapshot()
assert initial["kwinWatcher"], initial
assert initial["primary"] == initial["surfaceScreen"], initial
assert initial["windowVisible"] == (not initial["locked"] and not initial["fullscreen"]), initial
print("PASS primary output, fullscreen watcher and lock visibility", initial)

engine = QQmlApplicationEngine()
engine.loadData(b'''import QtQml
import org.kde.notificationmanager as NM
QtObject {
    property var previous
    property QtObject settings: NM.Settings { id: settings }
    function enableDnd() {
        previous = settings.notificationsInhibitedUntil
        settings.notificationsInhibitedUntil = new Date(Date.now() + 60000)
        settings.save()
    }
    function restoreDnd() {
        settings.notificationsInhibitedUntil = previous
        settings.save()
    }
}''', QUrl("file:///tmp/island-dnd-validation.qml"))
assert engine.rootObjects(), "DND QML failed to load"
settings = engine.rootObjects()[0]
try:
    assert QMetaObject.invokeMethod(settings, "enableDnd")
    QTest.qWait(1700)
    assert snapshot()["dnd"], snapshot()
    print("PASS native KDE DND is observed by the running island")
finally:
    QMetaObject.invokeMethod(settings, "restoreDnd")
    QTest.qWait(1700)
assert snapshot()["dnd"] == initial["dnd"], snapshot()
print("PASS original KDE DND state restored")

PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPS = "org.freedesktop.DBus.Properties"
name = "org.mpris.MediaPlayer2.island_validation_" + str(os.getpid())


class Player(dbus.service.Object):
    def __init__(self):
        self.name = dbus.service.BusName(name, bus=bus)
        super().__init__(bus, "/org/mpris/MediaPlayer2")

    @dbus.service.method(PROPS, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return {"PlaybackStatus": "Playing", "Metadata": dbus.Dictionary({
            "xesam:title": "灵动岛媒体集成验证", "xesam:artist": dbus.Array(["测试播放器"], signature="s")
        }, signature="sv")}

    @dbus.service.method(PROPS, in_signature="ss", out_signature="v")
    def Get(self, interface, key):
        return {"Identity": "Island validation", "DesktopEntry": "island-validation"}.get(key, "")

    @dbus.service.signal(PROPS, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated): pass


player = Player()
try:
    QTest.qWait(200)
    player.PropertiesChanged(PLAYER_IFACE, player.GetAll(PLAYER_IFACE), [])
    QTest.qWait(1600)
    assert snapshot()["mediaVisible"], snapshot()
    print("PASS MPRIS playback reaches the persistent media state")
finally:
    player.remove_from_connection()
    bus.release_name(name)
    QTest.qWait(1000)
print("PASS temporary MPRIS player removed")

# Only create a short-lived fullscreen validation window while the user is
# already locked. Never unlock the session or interrupt an active desktop.
if initial["locked"] or "--fullscreen" in sys.argv:
    environment = dict(os.environ)
    environment.pop("QT_QPA_PLATFORM", None)
    environment.pop("QT_WAYLAND_SHELL_INTEGRATION", None)
    window = subprocess.Popen(["/usr/bin/python", "-c", '''
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow
from PySide6.QtCore import QTimer
app = QGuiApplication([])
app.setApplicationName("island-validation")
window = QQuickWindow()
window.setColor("#101010")
window.setTitle("Island fullscreen validation")
window.showFullScreen()
QTimer.singleShot(5000, app.quit)
app.exec()
'''], env=environment)
    try:
        QTest.qWait(1600)
        current = snapshot()
        assert current["fullscreen"], current
        assert not current["windowVisible"], current
        print("PASS actual KWin fullscreen window hides the island")
    finally:
        window.terminate()
        window.wait(timeout=5)
        QTest.qWait(1000)
    assert snapshot()["fullscreen"] == initial["fullscreen"], snapshot()
    print("PASS fullscreen state clears after the validation window closes")

print("Live integration checks passed.")
