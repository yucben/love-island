import QtQuick
import QtQuick.Effects
import DynamicIsland

Item {
    id: root
    property var notification: ({})
    property bool active: false
    implicitHeight: Theme.statusHeight
    opacity: active ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 170 } }
    Image { id: osdIcon; x: 21; y: 17; width: 24; height: 24; sourceSize.width: 48; sourceSize.height: 48; source: root.notification && root.notification.iconSource ? root.notification.iconSource : ""; fillMode: Image.PreserveAspectFit; visible: false }
    MultiEffect { anchors.fill: osdIcon; source: osdIcon; brightness: 1.0; colorization: 1.0; colorizationColor: "#f5f5f7" }
    Text {
        x: 59; y: 15; width: parent.width - 82
        text: root.notification ? ((root.notification.appName ? root.notification.appName + "  " : "") + (root.notification.summary || "")) : ""
        color: "#f5f5f7"; font.pixelSize: 13; font.weight: Font.Medium; elide: Text.ElideRight
    }
    Rectangle {
        x: 59; y: 44; width: parent.width - 82; height: 4; radius: 2
        visible: root.notification && root.notification.progress >= 0; color: "#333337"
        Rectangle {
            width: parent.width * Math.max(0, Math.min(100, root.notification && root.notification.progress !== undefined ? root.notification.progress : 0)) / 100
            height: 4; radius: 2; color: "#f0f0f5"
            Behavior on width { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        }
    }
}
