import QtQuick
import QtQuick.Effects
import DynamicIsland

Item {
    id: root
    property var media: ({})
    property bool active: false
    signal commandRequested(string member)
    implicitHeight: Theme.musicDetailsHeight
    opacity: active ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    Rectangle {
        x: 22; y: 22; width: 58; height: 58; radius: 13; color: "#18181b"; clip: true
        Image { anchors.fill: parent; source: root.media.cover || ""; fillMode: Image.PreserveAspectCrop; asynchronous: true }
        Text { anchors.centerIn: parent; text: "♪"; color: "white"; font.pixelSize: 28; visible: !root.media.cover }
    }
    Column {
        x: 95; y: 29; width: parent.width - 120; spacing: 6
        Text { width: parent.width; text: root.media.title || ""; color: "white"; font.pixelSize: 16; font.weight: Font.DemiBold; elide: Text.ElideRight }
        Text { width: parent.width; text: root.media.artist || root.media.player || ""; color: "#8e8e96"; font.pixelSize: 12; elide: Text.ElideRight }
    }
    Row {
        anchors.horizontalCenter: parent.horizontalCenter; y: 100; spacing: 30
        Repeater {
            model: ["Previous", "PlayPause", "Next"]
            Item {
                required property string modelData
                objectName: "transport-" + modelData
                width: 46; height: 46
                Rectangle { anchors.fill: parent; radius: 23; color: controlMouse.pressed ? "#303035" : controlMouse.containsMouse ? "#19191c" : "transparent" }
                // Geometric transport icons remain crisp without icon-font dependencies.
                Canvas {
                    anchors.centerIn: parent; width: 26; height: 24
                    property bool playing: !!root.media.playing
                    onPlayingChanged: requestPaint()
                    onPaint: {
                        const c = getContext("2d"); c.reset(); c.fillStyle = "white"
                        if (modelData === "PlayPause") {
                            if (playing) { c.fillRect(6, 3, 5, 18); c.fillRect(16, 3, 5, 18) }
                            else { c.beginPath(); c.moveTo(7,2); c.lineTo(23,12); c.lineTo(7,22); c.closePath(); c.fill() }
                        } else {
                            c.save()
                            if (modelData === "Previous") { c.translate(26,0); c.scale(-1,1) }
                            c.beginPath(); c.moveTo(2,4); c.lineTo(13,12); c.lineTo(2,20); c.closePath(); c.fill()
                            c.beginPath(); c.moveTo(12,4); c.lineTo(23,12); c.lineTo(12,20); c.closePath(); c.fill(); c.restore()
                        }
                    }
                }
                MouseArea { id: controlMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.commandRequested(modelData) }
            }
        }
    }
}
