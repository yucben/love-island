"""Exercise queue lifetime, suppression/history and the real QML scene offscreen."""
import os
from support import APPLICATION, TEST_ROOT

import unittest
from pathlib import Path

from PySide6.QtCore import QObject, Property, QPoint, QPointF, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QImage, QColor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from dynamicisland.artwork import ArtworkProvider, ThemeIconProvider
from dynamicisland.config import Config
from dynamicisland.desktop_sources import PowerMonitor, select_primary_output
from dynamicisland.controller import IslandController
from dynamicisland.media import MediaWatcher, Track, PLAYER
from dynamicisland.model import NotificationModel, OSD_HINT
from dynamicisland.server import NotificationService
from dynamicisland.strings import Strings
from dynamicisland.window import WindowTools



class Desktop(QObject):
    changed = Signal()
    powerChanged = Signal(bool, int)
    _blocked = False
    _dnd = False

    @Property(bool, notify=changed)
    def blocked(self): return self._blocked

    @Property(bool, notify=changed)
    def doNotDisturb(self): return self._dnd


class MediaSource(QObject):
    changed = Signal(object)
    replaced = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.track = None
        self.commands = []

    def current(self): return self.track

    def command(self, bus_name, member): self.commands.append((bus_name, member))

    def publish(self, track):
        self.track = track
        self.changed.emit(track)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.owner = QObject()
        self.config = Config(self.owner)
        self.config.merge({"soundEnabled": False, "osdTimeout": 180})
        self.service = NotificationService(self.owner, claim=False)
        self.model = NotificationModel(self.owner)
        self.art = ArtworkProvider()
        self.controller = IslandController(self.config, self.model, self.service, self.art, self.owner)
        self.media = MediaSource(self.owner)
        self.controller.attach_media(self.media)
        self.desktop = Desktop(self.owner)
        self.controller.attach_desktop(self.desktop)
        self.controller.clearHistory()

    def tearDown(self):
        self.controller.dismissAll()
        self.owner.deleteLater()
        APPLICATION.processEvents()

    def notify(self, nid, title="消息", timeout=1000, hints=None, actions=None):
        self.controller.receive("测试", nid, "", title, "正文", actions or [], hints or {}, timeout)

    def test_fifo_replacement_and_osd_priority(self):
        self.notify(1)
        self.notify(2)
        self.notify(1, "更新消息")
        self.assertEqual(self.model.ids(), [1, 2])
        self.controller.show_status("volume", "", 45, "")
        self.assertEqual(self.model.ids()[1:], [1, 2])
        self.controller.show_status("volume", "", 46, "")
        self.assertEqual(len(self.model.ids()), 3)

    def test_waiting_notification_does_not_expire_behind_osd(self):
        self.notify(1, timeout=120)
        self.controller.show_status("volume", "", 50, "")
        QTest.qWait(140)
        self.assertIsNotNone(self.model.get(1))
        QTest.qWait(90)
        self.assertEqual(self.model.ids(), [1])
        QTest.qWait(160)
        self.assertEqual(self.model.ids(), [])

    def test_hover_pauses_only_the_front_countdown(self):
        self.notify(1, timeout=100)
        self.notify(2, timeout=100)
        self.controller.setHovered(True)
        QTest.qWait(150)
        self.assertEqual(self.model.ids(), [1, 2])
        self.controller.setHovered(False)
        QTest.qWait(130)
        self.assertEqual(self.model.ids(), [2])

    def test_fullscreen_suppression_preserves_history(self):
        self.desktop._blocked = True
        self.desktop.changed.emit()
        self.notify(1, "全屏时的消息")
        self.assertEqual(self.model.ids(), [])
        self.assertEqual(self.controller.history[0]["summary"], "全屏时的消息")

    def test_entering_fullscreen_archives_active_notifications(self):
        self.notify(1)
        self.desktop._blocked = True
        self.desktop.changed.emit()
        self.assertEqual(self.model.ids(), [])
        self.assertEqual(len(self.controller.history), 1)
        self.desktop._blocked = False
        self.desktop.changed.emit()
        self.assertEqual(self.model.ids(), [])

    def test_dnd_suppresses_critical_but_allows_manual_osd(self):
        self.desktop._dnd = True
        self.desktop.changed.emit()
        self.notify(1, "严重通知", hints={"urgency": 2})
        self.assertEqual(self.model.ids(), [])
        self.controller.show_status("volume", "", 25, "")
        self.assertEqual(self.model.rowCount(), 1)

    def test_more_notifications_than_visual_stack_are_retained(self):
        for nid in range(1, 12): self.notify(nid)
        self.assertEqual(self.model.ids(), list(range(1, 12)))

    def test_queue_capacity_archives_overflow(self):
        for nid in range(1, 104): self.notify(nid)
        self.assertEqual(self.model.rowCount(), 100)
        self.assertEqual(len(self.controller.history), 3)
        self.controller.dismissAll()
        self.assertEqual(self.model.ids(), [])

    def test_media_is_not_a_transient_notification(self):
        track = Track("org.mpris.MediaPlayer2.test")
        track.title = "Midnight City"
        track.artist = "M83"
        track.playing = True
        self.media.publish(track)
        self.assertEqual(self.model.ids(), [])
        self.assertTrue(self.controller.media["visible"])
        self.assertEqual(self.controller.media["title"], "Midnight City")

    def test_first_signal_from_new_player_is_announced(self):
        watcher = MediaWatcher(self.owner, claim=False)
        name = "org.mpris.MediaPlayer2.test"
        watcher._name_of = lambda sender: name
        watcher._identify = lambda track: None
        def read_player(bus_name):
            track = Track(bus_name)
            track.title = "Already playing"
            track.playing = True
            watcher._tracks[bus_name] = track
        watcher._read = read_player
        announced = []
        watcher.changed.connect(announced.append)
        watcher._on_properties(PLAYER, {"PlaybackStatus": "Playing"}, [], sender=":1.99")
        self.assertEqual(len(announced), 1)
        self.assertEqual(announced[0].title, "Already playing")

    def test_power_listener_announces_transitions_not_initial_state(self):
        class Power:
            on_battery = True
            def add_signal_receiver(self, *args, **kwargs): pass
            def get_object(self, *args): return self
            def Get(self, *args, **kwargs): return self.on_battery
            def GetAll(self, *args, **kwargs): return {"IsPresent": True, "Percentage": 67.6}
        power = Power()
        monitor = PowerMonitor(bus=power, parent=self.owner)
        events = []
        monitor.changed.connect(lambda plugged, percentage: events.append((plugged, percentage)))
        monitor.refresh()
        self.assertEqual(events, [])
        power.on_battery = False
        monitor.refresh()
        monitor.refresh()
        self.assertEqual(events, [(True, 68)])
        power.on_battery = True
        monitor.refresh()
        self.assertEqual(events[-1], (False, 68))

    def test_primary_selection_ignores_disabled_outputs(self):
        outputs = [
            {"name": "disabled", "enabled": False, "connected": True, "priority": 1},
            {"name": "secondary", "enabled": True, "connected": True, "priority": 2},
            {"name": "primary", "enabled": True, "connected": True, "priority": 1}
        ]
        self.assertEqual(select_primary_output(outputs), "primary")
        self.assertEqual(select_primary_output([], "fallback"), "fallback")

    def test_qml_states_and_media_click(self):
        engine = QQmlApplicationEngine()
        qml_root = Path(__file__).resolve().parents[1] / "src/dynamicisland/qml"
        engine.addImportPath(str(qml_root))
        engine.addImageProvider("island", self.art)
        engine.addImageProvider("icon", ThemeIconProvider())
        tools = WindowTools(self.owner)
        strings = Strings(self.owner, "zh_CN")
        for key, value in {"Cfg": self.config, "Controller": self.controller,
            "Notifications": self.model, "Desktop": self.desktop,
            "WindowTools": tools, "Strings": strings}.items():
            engine.rootContext().setContextProperty(key, value)
        engine.loadData(b'''import QtQuick
import QtQuick.Window
import DynamicIsland
Window {
    width: 760; height: 420; visible: true; color: "#b7bbc4"
    Island { id: island; objectName: "island"; anchors.horizontalCenter: parent.horizontalCenter }
}''', QUrl.fromLocalFile(str(qml_root / "Preview.qml")))
        self.assertTrue(engine.rootObjects())
        window = engine.rootObjects()[0]
        island = window.findChild(QObject, "island")
        display = window.findChild(QObject, "presentation")
        QTest.qWait(650)
        self.assertAlmostEqual(island.property("width"), 112, delta=1)
        artifacts = Path(os.environ.get("ISLAND_ARTIFACTS", TEST_ROOT))
        artifacts.mkdir(parents=True, exist_ok=True)
        window.grabWindow().save(str(artifacts / "idle.png"))
        QTest.mouseMove(window, QPoint(380, 14))
        QTest.qWait(1000)
        self.assertEqual(display.property("mode"), "history")
        self.assertTrue(display.property("expanded"))
        window.grabWindow().save(str(artifacts / "idle-expanded.png"))
        QTest.mouseMove(window, QPoint(30, 350))
        QTest.qWait(1400)
        self.assertFalse(display.property("expanded"))
        self.assertAlmostEqual(island.property("width"), 112, delta=2)
        track = Track("org.mpris.MediaPlayer2.test")
        track.title = "Midnight City"; track.artist = "M83"; track.playing = True
        commands = self.media.commands
        self.media.publish(track)
        QTest.qWait(1100)
        self.assertAlmostEqual(island.property("width"), 264, delta=2)
        window.grabWindow().save(str(artifacts / "music-compact.png"))
        QTest.mouseMove(window, QPoint(380, 14))
        QTest.qWait(1400)
        self.assertEqual(display.property("mode"), "music")
        self.assertTrue(display.property("expanded"))
        self.assertAlmostEqual(island.property("width"), 390, delta=2)
        window.grabWindow().save(str(artifacts / "music-expanded.png"))
        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)
        transport = next((item for item in visual_items(window.contentItem())
                          if item.objectName() == "transport-Next"), None)
        self.assertIsNotNone(transport)
        location = transport.mapToScene(QPointF(23, 23)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, location)
        self.assertEqual(commands, [(track.bus_name, "Next")])
        QTest.mouseMove(window, QPoint(30, 350))
        QTest.qWait(1400)
        self.assertFalse(display.property("expanded"))
        self.assertAlmostEqual(island.property("width"), 264, delta=2)
        QTest.mouseMove(window, QPoint(380, 14))
        QTest.qWait(1000)
        self.assertEqual(display.property("mode"), "music")
        self.assertTrue(display.property("expanded"))
        actions = []
        self.service.emit_action = lambda nid, key: actions.append((nid, key))
        self.notify(22, "设计已准备好", timeout=0, actions=["open", "打开"])
        QTest.qWait(1100)
        self.assertEqual(display.property("mode"), "notification")
        self.assertTrue(display.property("expanded"))
        window.grabWindow().save(str(artifacts / "notification.png"))
        action = next(obj for obj in visual_items(window.contentItem()) if obj.property("label") == "打开")
        location = action.mapToScene(QPointF(action.width() / 2, action.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, location)
        self.assertEqual(actions, [(22, "open")])
        self.assertIsNone(self.model.get(22))
        QTest.mouseClick(window, Qt.RightButton, Qt.NoModifier, QPoint(380, 14))
        QTest.qWait(1100)
        self.assertEqual(display.property("mode"), "history")
        self.assertTrue(display.property("expanded"))
        window.grabWindow().save(str(artifacts / "history.png"))
        QTest.mouseMove(window, QPoint(30, 350))
        QTest.qWait(1000)
        self.assertFalse(display.property("expanded"))
        self.assertFalse(display.property("expanded"))
        window.close()
        engine.deleteLater()
        APPLICATION.processEvents()


if __name__ == "__main__":
    unittest.main()
