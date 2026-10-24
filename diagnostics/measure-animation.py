#!/usr/bin/env python3
"""Native Wayland feedback loop for island morph cadence and settling time.

Uses a private config/history and never claims the notification service.
"""
import argparse
import atexit
import json
import os
import statistics
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
parser.add_argument("--no-mask", action="store_true")
parser.add_argument("--minimal", action="store_true")
parser.add_argument("--target-fps", type=float, default=0,
    help="require p95 <= 1.1 frame budgets and no frame > two budgets")
parser.add_argument("--linear-minimal", action="store_true")
parser.add_argument("--cycles", type=int, default=3)
parser.add_argument("--exclusive", action="store_true",
    help="temporarily hand notifications to Plasma, then restore the island")
args = parser.parse_args()
if args.cycles < 1 or args.target_fps < 0:
    parser.error("cycles must be positive and target-fps must be nonnegative")
original_environment = dict(os.environ)
manager = Path(shutil.which("love-island-session") or (Path.home() / ".local/bin/island-session"))
service_unit = "love-island.service" if manager.name == "love-island-session" else "dynamic-island.service"
if args.exclusive:
    subprocess.run([str(manager), "restore"], check=True)
    atexit.register(lambda: subprocess.run([str(manager), "start"], env=original_environment, check=False))
elif subprocess.run(["systemctl", "--user", "is-active", "--quiet", service_unit]).returncode == 0:
    parser.error("Use --exclusive: overlapping layer-shell surfaces invalidate frame measurements.")
temporary = tempfile.TemporaryDirectory(prefix="island-animation-")
os.environ["XDG_CONFIG_HOME"] = temporary.name + "/config"
os.environ["XDG_DATA_HOME"] = temporary.name + "/data"
os.environ["QT_WAYLAND_SHELL_INTEGRATION"] = "layer-shell"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QObject, Property, QMetaObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from dbus.mainloop.glib import DBusGMainLoop
from dynamicisland.artwork import ArtworkProvider, ThemeIconProvider
from dynamicisland.config import Config
from dynamicisland.controller import IslandController
from dynamicisland.model import NotificationModel
from dynamicisland.server import NotificationService
from dynamicisland.strings import Strings
from dynamicisland.window import WindowTools

DBusGMainLoop(set_as_default=True)
app = QGuiApplication([])
app.setQuitOnLastWindowClosed(False)
class Desktop(QObject):
    changed = Signal()
    powerChanged = Signal(bool, int)
    @Property(bool, notify=changed)
    def blocked(self): return False
    @Property(bool, notify=changed)
    def doNotDisturb(self): return False
    @Slot(bool)
    def setDoNotDisturb(self, value): pass

config = Config()
config.merge({"soundEnabled": False, "screen": "primary"})
model = NotificationModel()
artwork = ArtworkProvider()
controller = IslandController(config, model, NotificationService(claim=False), artwork)
desktop = Desktop()
tools = WindowTools()
engine = QQmlApplicationEngine()
qml = Path(__file__).resolve().parents[1] / "src/dynamicisland/qml"
engine.addImportPath(str(qml))
engine.addImageProvider("island", artwork)
engine.addImageProvider("icon", ThemeIconProvider())
strings = Strings(preferred="zh_CN")
for key, value in {"Cfg": config, "Controller": controller, "Notifications": model,
                   "Desktop": desktop, "WindowTools": tools, "Strings": strings}.items():
    engine.rootContext().setContextProperty(key, value)
# Load the real layer-shell scene. A separate scope makes the measurement
# surface independent of the running island's notification ownership.
source = (qml / "main.qml").read_text().replace('scope: "dynamic-island"', 'scope: "island-frame-probe"')
if args.minimal or args.linear_minimal:
    source = '''import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell
Window {
    id: root
    visible: true; color: "transparent"; width: Screen.width; height: 360
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    LayerShell.Window.scope: "island-frame-probe"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft | LayerShell.Window.AnchorRight
    LayerShell.Window.exclusionZone: -1
    Rectangle {
        id: island
        anchors.horizontalCenter: parent.horizontalCenter
        property bool historyOpen: false
        width: historyOpen ? 390 : 112; height: historyOpen ? 152 : 28
        color: "black"; radius: 20
        Behavior on width { SpringAnimation { spring: 4.2; damping: 0.78; mass: 1; epsilon: 0.15 } }
        Behavior on height { SpringAnimation { spring: 4.8; damping: 0.9; mass: 1; epsilon: 0.15 } }
    }
}'''
    if args.linear_minimal:
        source = source.replace("SpringAnimation { spring: 4.2; damping: 0.78; mass: 1; epsilon: 0.15 }", "NumberAnimation { duration: 340; easing.type: Easing.OutCubic }")
        source = source.replace("SpringAnimation { spring: 4.8; damping: 0.9; mass: 1; epsilon: 0.15 }", "NumberAnimation { duration: 300; easing.type: Easing.OutCubic }")
source = source.replace('id: root', '''id: root
    property var perfFrames: []
    property var perfUpdates: []
    onFrameSwapped: perfFrames.push(Date.now())
    Connections {
        target: island
        function onWidthChanged() { root.perfUpdates.push({t: Date.now(), w: island.width}) }
    }''', 1)
source = source.replace("Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint",
    "Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput")
engine.loadData(source.encode(), QUrl.fromLocalFile(str(qml / "FrameProbe.qml")))
if not engine.rootObjects(): sys.exit("QML failed to load")
window = engine.rootObjects()[0]
if not args.no_mask: tools.attach(window)
def visual_items(item):
    yield item
    for child in item.childItems(): yield from visual_items(child)
island = next(item for item in visual_items(window.contentItem())
              if item.metaObject().indexOfProperty("presentation") >= 0
              or item.metaObject().indexOfProperty("historyOpen") >= 0)
presentation = window.findChild(QObject, "presentation")
start = time.time()
transitions = []
def toggle(opened):
    transitions.append((time.time(), config.get("expandedWidth") if opened else config.get("compactMinWidth")))
    if presentation is not None:
        QMetaObject.invokeMethod(presentation, "enter" if opened else "leave")
    else:
        island.setProperty("historyOpen", opened)
schedule = [(500 + i*1100, i % 2 == 0) for i in range(args.cycles)]
finish_ms = schedule[-1][0] + 900
for milliseconds, opened in schedule:
    QTimer.singleShot(milliseconds, lambda value=opened: toggle(value))
QTimer.singleShot(finish_ms, app.quit)
app.exec()
frames = [value/1000 for value in window.property("perfFrames").toVariant()]
updates = [(value["t"]/1000, value["w"]) for value in window.property("perfUpdates").toVariant()]

def intervals(values): return [(b-a)*1000 for a,b in zip(values, values[1:])]
def summary(values):
    if not values: return {}
    ordered=sorted(values)
    return {"count": len(values), "p50_ms": round(statistics.median(values), 2),
            "p95_ms": round(ordered[int((len(ordered)-1)*.95)], 2),
            "p99_ms": round(ordered[int((len(ordered)-1)*.99)], 2), "max_ms": round(max(values),2)}

# Measure the actual morph interval, excluding hover debounce and settled idle.
render_steps=[]; shape_steps=[]; settled=[]
for index, (at, target) in enumerate(transitions):
    end=transitions[index+1][0] if index+1<len(transitions) else start+finish_ms/1000
    tail=[(t,w) for t,w in updates if at <= t < end]
    if tail:
        first,last=tail[0][0],tail[-1][0]
        render_steps.extend(intervals([t for t in frames if first <= t <= last]))
        shape_steps.extend(intervals([t for t,w in tail]))
    last_outside=max((t for t,w in tail if abs(w-target)>1), default=at)
    settled.append(round((last_outside-at)*1000, 1))
result={"metric": "application-frame-ready (not hardware presentation)", "refresh_hz": window.screen().refreshRate(), "render_api": str(window.rendererInterface().graphicsApi()),
        "frames": summary(render_steps), "shape_updates": summary(shape_steps),
        "settle_ms": settled, "mask_enabled": not (args.no_mask or args.minimal or args.linear_minimal)}
print(json.dumps(result, indent=2))
refresh=window.screen().refreshRate()
cadence=statistics.median(shape_steps) if shape_steps else 1000
passed=cadence <= (1000/refresh)*1.6 and max(settled or [9999]) <= 650
if args.target_fps:
    budget = 1000/args.target_fps
    passed = bool(render_steps and shape_steps) and all(
        sorted(steps)[int((len(steps)-1)*.95)] <= budget*1.1
        and max(steps) <= budget*2 for steps in (render_steps, shape_steps))
    print("PASS" if passed else "FAIL", f"stable {args.target_fps:g}fps frame budget")
else:
    print("PASS" if passed else "FAIL", "native-refresh morph and <=650ms settling")
window.close()
sys.exit(0 if passed or not args.check else 1)
