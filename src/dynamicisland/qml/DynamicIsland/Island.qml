import QtQuick
import DynamicIsland

// Surface geometry, pointer routing and wiring. Each card only renders inputs.
Item {
    id: root
    readonly property var presentation: display
    readonly property bool expanded: display.expanded
    readonly property bool wantsKeyboard: display.mode === "notification" && display.expanded && card.replying
    width: display.targetWidth
    height: display.targetHeight

    IslandPresentation {
        id: display
        objectName: "presentation"
        settings: Cfg.values
        notification: Notifications.front
        mediaAvailable: !!Controller.media.visible
        historyCount: Controller.history.length
        blocked: Desktop.blocked
        viewportWidth: root.parent ? root.parent.width : 760
        notificationHeight: card.implicitHeight
    }

    Behavior on width {
        NumberAnimation {
            duration: display.expanded ? Theme.openWidthDuration : Theme.closeWidthDuration
            easing.type: display.expanded ? Easing.OutBack : Easing.InOutCubic
            easing.overshoot: 0.45
        }
    }
    Behavior on height {
        NumberAnimation {
            duration: display.expanded ? Theme.openHeightDuration : Theme.closeHeightDuration
            easing.type: display.expanded ? Easing.OutCubic : Easing.InOutCubic
        }
    }

    function syncInputRegion() { Qt.callLater(root.applyInputRegion) }
    function applyInputRegion() {
        if (Desktop.blocked) { WindowTools.clearInputRegion(); return }
        WindowTools.setInputRegion(Math.round(x), Math.round(y), Math.ceil(width), Math.ceil(height + 1))
    }
    onXChanged: syncInputRegion()
    onYChanged: syncInputRegion()
    onWidthChanged: syncInputRegion()
    onHeightChanged: syncInputRegion()
    Component.onCompleted: syncInputRegion()
    Connections { target: Desktop; function onChanged() { root.syncInputRegion() } }

    HoverHandler {
        id: hover
        onHoveredChanged: {
            Controller.setHovered(hovered)
            if (hovered) display.enter()
            else display.leave()
        }
    }
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        property real startY: 0
        property bool moved: false
        onPressed: mouse => { startY = mapToItem(null, mouse.x, mouse.y).y; moved = false }
        onPositionChanged: mouse => {
            if (pressed && Math.abs(mapToItem(null, mouse.x, mouse.y).y - startY) > 5) moved = true
        }
        onReleased: mouse => {
            const delta = mapToItem(null, mouse.x, mouse.y).y - startY
            if (moved) {
                if (delta < -Cfg.values.dismissThreshold) {
                    if (display.hasEvent) Controller.dismiss(display.notification.notificationId)
                    display.collapse()
                }
            } else if (mouse.button === Qt.RightButton) {
                Controller.dismissAll()
                display.showHistory()
            } else if (display.hasEvent) {
                if (mouse.button === Qt.MiddleButton) Controller.dismiss(display.notification.notificationId)
                else Controller.activateDefault(display.notification.notificationId)
            } else display.showDetails()
        }
    }

    Rectangle {
        anchors.fill: parent
        anchors.topMargin: -Theme.surfaceOverhang
        radius: display.expanded ? Cfg.values.expandedRadius : Cfg.values.compactHeight / 2 + 3
        color: "#000000"
        border.width: display.expanded ? 1 : 0
        border.color: "#202024"
        clip: true
        Behavior on radius { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }

        Item {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: Theme.surfaceOverhang / 2
            width: 34; height: 10
            visible: display.mode === "idle"
            Rectangle { x: 0; y: 2; width: 18; height: 6; radius: 3; color: "#0a0a0b" }
            Rectangle {
                x: 25; width: 10; height: 10; radius: 5; color: "#0c0d12"
                Rectangle { x: 3; y: 2; width: 3; height: 3; radius: 2; color: "#181e31" }
            }
        }
        Text {
            x: 16; y: Theme.surfaceOverhang; width: parent.width - 32; height: Cfg.values.compactHeight
            visible: display.hasEvent && !display.expanded
            text: display.hasEvent ? (display.mode === "status" ? display.notification.summary : display.notification.appName || "通知") : ""
            color: "#d5d5dc"; font.pixelSize: 11; font.weight: Font.Medium
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        CompactMusic {
            media: Controller.media
            active: display.mode === "music" && !display.expanded && !Desktop.blocked
        }
        MusicPlayer {
            x: 0; y: Theme.surfaceOverhang; width: display.cardWidth; height: implicitHeight
            media: Controller.media
            active: display.mode === "music" && display.expanded
            onCommandRequested: member => Controller.mediaCommand(member)
        }
        StatusCard {
            x: 0; y: Theme.surfaceOverhang; width: Math.min(Theme.statusWidth, display.cardWidth); height: implicitHeight
            notification: display.notification
            active: display.mode === "status" && display.expanded
        }
        NotificationCard {
            id: card
            x: 0; y: Theme.surfaceOverhang + 4; width: display.cardWidth
            notification: display.notification
            accent: display.notification.accent || "#9999a3"
            showClose: hover.hovered && display.expanded
            leaving: !display.hasEvent
            opacity: display.mode === "notification" && display.hasEvent && display.expanded ? 1 : 0
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: 200 } }
            onDismissRequested: if (display.hasEvent) Controller.dismiss(display.notification.notificationId)
            onActionRequested: key => { if (display.hasEvent) Controller.invokeAction(display.notification.notificationId, key) }
            onReplyRequested: text => { if (display.hasEvent) Controller.sendReply(display.notification.notificationId, text) }
        }
        NotificationHistory {
            x: 0; y: Theme.surfaceOverhang; width: display.cardWidth; height: root.height
            entries: Controller.history
            active: display.mode === "history" && display.expanded
            onClearRequested: Controller.clearHistory()
            onCloseRequested: display.collapse()
            onOpenRequested: index => { Controller.openHistoryEntry(index); display.collapse() }
        }
    }
}
