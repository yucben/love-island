import QtQuick
import QtQuick.Effects
import DynamicIsland

Item {
    id: root
    property var entries: []
    property bool active: false
    signal clearRequested()
    signal closeRequested()
    signal openRequested(int index)
    visible: active
    Text { x: 22; y: 19; text: "通知中心"; color: "white"; font.pixelSize: 16; font.weight: Font.DemiBold }
    Text {
        x: 22; y: 76; visible: !root.entries.length
        text: "暂时没有通知"; color: "#777780"; font.pixelSize: 13
    }
    Row {
        anchors.right: parent.right; anchors.rightMargin: 18; y: 15; spacing: 6
        Repeater {
            model: ["清空", "关闭"]
            Rectangle {
                required property string modelData
                width: 44; height: 28; radius: 14; color: historyButton.containsMouse ? "#29292e" : "#17171b"
                Text { anchors.centerIn: parent; text: modelData; color: "#b8b8c0"; font.pixelSize: 11 }
                MouseArea { id: historyButton; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { if (modelData === "清空") root.clearRequested(); else root.closeRequested() } }
            }
        }
    }
    ListView {
        x: 14; y: 57; width: parent.width - 28; height: 244
        visible: root.entries.length > 0
        clip: true; spacing: 6; model: root.entries
        delegate: Rectangle {
            required property var modelData
            required property int index
            width: ListView.view.width; height: lines.implicitHeight + 24
            radius: 16; color: historyMouse.containsMouse ? "#202024" : "#131316"
            Column {
                id: lines; x: 14; y: 12; width: parent.width - 28; spacing: 4
                Text { width: parent.width; text: modelData.appName || "通知"; color: "#8d8d98"; font.pixelSize: 10; elide: Text.ElideRight }
                Text { width: parent.width; text: modelData.summary || ""; color: "#f0f0f4"; font.pixelSize: 12; font.weight: Font.Medium; maximumLineCount: 2; wrapMode: Text.Wrap; elide: Text.ElideRight; textFormat: Text.PlainText }
                Text { width: parent.width; text: (modelData.body || "").replace(/<[^>]*>/g, ""); color: "#9a9aa4"; font.pixelSize: 11; maximumLineCount: 2; wrapMode: Text.Wrap; elide: Text.ElideRight; visible: text.length > 0; textFormat: Text.PlainText }
            }
            MouseArea { id: historyMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { root.openRequested(index) } }
        }
    }
}
