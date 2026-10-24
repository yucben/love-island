import QtQuick
import QtQuick.Effects
import DynamicIsland

Item {
    id: root
    property var media: ({})
    property bool active: false
    anchors.fill: parent
    anchors.topMargin: Theme.surfaceOverhang
    opacity: active ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 140 } }
    Rectangle {
        x: 7; anchors.verticalCenter: parent.verticalCenter
        width: 20; height: 20; radius: 5; color: "#19191c"; clip: true
        Image { anchors.fill: parent; source: root.media.cover || ""; fillMode: Image.PreserveAspectCrop; asynchronous: true }
        Text { anchors.centerIn: parent; text: "♪"; color: "#d0d0d5"; visible: !root.media.cover; font.pixelSize: 14 }
    }
    Text {
        x: 36; width: parent.width - 78; anchors.verticalCenter: parent.verticalCenter
        text: root.media.title || ""; elide: Text.ElideRight
        color: "#eeeeef"; font.pixelSize: 11; font.weight: Font.Medium
    }
    Row {
        anchors.right: parent.right; anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter; spacing: 2; height: 16
        Repeater {
            model: 4
            Rectangle {
                required property int index
                width: 2; height: 5 + index % 3 * 3; radius: 1
                anchors.verticalCenter: parent.verticalCenter
                color: "#c5b7fb"
                SequentialAnimation on height {
                    running: !!root.media.playing && root.visible && root.active
                    loops: Animation.Infinite
                    NumberAnimation { to: 4; duration: 300 + index * 110; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 7 + (3 - index) * 2; duration: 290 + index * 80; easing.type: Easing.InOutSine }
                }
            }
        }
    }
}
