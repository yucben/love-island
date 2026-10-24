"""Display policy is exercised through the same interface as pointer routing."""
import unittest
from pathlib import Path

from PySide6.QtCore import QMetaObject, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from support import APPLICATION
from dynamicisland.config import DEFAULTS


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.engine = QQmlEngine()
        qml = Path(__file__).resolve().parents[1] / "src/dynamicisland/qml"
        self.engine.addImportPath(str(qml))
        self.component = QQmlComponent(self.engine)
        self.component.setData(b'import QtQuick\nimport DynamicIsland\nIslandPresentation {}',
                               QUrl.fromLocalFile(str(qml / "PolicyTest.qml")))
        self.view = self.component.createWithInitialProperties({"settings": dict(DEFAULTS)})
        self.assertIsNotNone(self.view, [str(error) for error in self.component.errors()])

    def tearDown(self):
        self.view.deleteLater()
        self.engine.deleteLater()
        APPLICATION.processEvents()

    def call(self, member):
        self.assertTrue(QMetaObject.invokeMethod(self.view, member))

    def test_hover_chooses_history_or_music_and_leaving_collapses(self):
        self.assertEqual(self.view.property("mode"), "idle")
        self.call("enter")
        QTest.qWait(110)
        self.assertEqual(self.view.property("mode"), "history")
        self.assertTrue(self.view.property("expanded"))
        self.view.setProperty("mediaAvailable", True)
        self.assertEqual(self.view.property("mode"), "music")
        self.call("leave")
        QTest.qWait(150)
        self.assertFalse(self.view.property("expanded"))

    def test_status_interrupts_and_replacements_do_not_restart_reveal(self):
        self.view.setProperty("notification", {"notificationId": 1, "kind": "notification"})
        QTest.qWait(190)
        self.assertEqual(self.view.property("mode"), "notification")
        self.assertTrue(self.view.property("expanded"))
        self.view.setProperty("notification", {"notificationId": 2, "kind": "osd", "progress": 40})
        self.assertFalse(self.view.property("expanded"))
        QTest.qWait(190)
        self.assertEqual(self.view.property("mode"), "status")
        self.view.setProperty("notification", {"notificationId": 2, "kind": "osd", "progress": 50})
        self.assertTrue(self.view.property("expanded"))

    def test_history_is_one_exclusive_display_mode(self):
        self.view.setProperty("notification", {"notificationId": 1, "kind": "notification"})
        self.call("showHistory")
        QTest.qWait(190)
        self.assertEqual(self.view.property("mode"), "history")
        self.assertTrue(self.view.property("expanded"))

    def test_blocking_cancels_pending_expansion(self):
        self.call("enter")
        self.view.setProperty("blocked", True)
        self.view.setProperty("notification", {"notificationId": 3, "kind": "notification"})
        QTest.qWait(220)
        self.assertFalse(self.view.property("expanded"))

    def test_geometry_obeys_configured_compact_dimensions(self):
        settings = dict(DEFAULTS, compactHeight=36, compactMinWidth=126, compactMaxWidth=220)
        self.view.setProperty("settings", settings)
        self.assertEqual(self.view.property("targetWidth"), 126)
        self.assertEqual(self.view.property("targetHeight"), 36)
        self.view.setProperty("mediaAvailable", True)
        self.assertEqual(self.view.property("targetWidth"), 220)
