import QtQuick
import DynamicIsland

// One owner for which details are open. Renderers never mutate display state.
QtObject {
    id: root
    required property var settings
    property var notification: ({})
    property bool mediaAvailable: false
    property int historyCount: 0
    property bool blocked: false
    property real viewportWidth: 760
    property real notificationHeight: 0

    property string _details: "collapsed"
    property int _eventId: -1
    property bool _hovered: false

    readonly property bool hasEvent: notification && notification.notificationId !== undefined
    readonly property string eventMode: hasEvent && notification.kind === "osd" ? "status" : "notification"
    readonly property string mode: _details === "history" ? "history"
        : hasEvent ? eventMode : mediaAvailable ? "music" : "idle"
    readonly property bool expanded: _details !== "collapsed"
    readonly property real availableWidth: Math.max(200, viewportWidth - 32)
    readonly property real cardWidth: Math.min(settings.expandedWidth, availableWidth)
    readonly property real targetWidth: expanded
        ? mode === "status" ? Math.min(Theme.statusWidth, cardWidth) : cardWidth
        : hasEvent ? Math.min(Theme.eventCompactWidth, availableWidth)
        : mediaAvailable ? Math.min(Theme.mediaCompactWidth, settings.compactMaxWidth, availableWidth)
        : Math.min(settings.compactMinWidth, availableWidth)
    readonly property real targetHeight: !expanded ? settings.compactHeight
        : mode === "status" ? Theme.statusHeight
        : mode === "notification" ? Math.min(settings.maxHeight, notificationHeight + 8)
        : mode === "history" ? historyCount ? Theme.historyHeight : Theme.emptyHistoryHeight
        : Theme.musicDetailsHeight

    function enter() {
        _hovered = true
        closeDelay.stop()
        if (!blocked) openDelay.restart()
    }
    function leave() {
        _hovered = false
        openDelay.stop()
        closeDelay.restart()
    }
    function showDetails() {
        if (blocked) return
        _details = hasEvent ? eventMode : mediaAvailable ? "music" : "history"
    }
    function showHistory() {
        if (blocked) return
        openDelay.stop()
        eventDelay.stop()
        _details = "history"
    }
    function collapse() {
        openDelay.stop()
        eventDelay.stop()
        _details = "collapsed"
    }
    function reconcileEvent() {
        // Read the changed input directly: derived QML bindings may still be
        // queued when onNotificationChanged runs.
        const next = notification && notification.notificationId !== undefined
            ? notification.notificationId : -1
        if (next === _eventId) return
        _eventId = next
        collapse()
        if (next !== -1 && !blocked) eventDelay.restart()
        else if (_hovered) showDetails()
    }

    onNotificationChanged: reconcileEvent()
    onMediaAvailableChanged: {
        if (_hovered && !hasEvent) showDetails()
        else if (_details === "music" && !mediaAvailable) collapse()
    }
    onBlockedChanged: {
        if (blocked) { closeDelay.stop(); collapse() }
        else if (_hovered) showDetails()
    }
    Component.onCompleted: reconcileEvent()

    property Timer _openDelay: Timer {
        id: openDelay
        interval: Theme.hoverOpenDelay
        onTriggered: if (root._hovered) root.showDetails()
    }
    property Timer _closeDelay: Timer {
        id: closeDelay
        interval: Theme.hoverCloseDelay
        onTriggered: if (!root._hovered) root.collapse()
    }
    property Timer _eventDelay: Timer {
        id: eventDelay
        interval: Theme.eventRevealDelay
        onTriggered: if (root.hasEvent && !root.blocked) root.showDetails()
    }
}
