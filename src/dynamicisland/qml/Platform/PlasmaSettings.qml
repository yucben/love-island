import QtQuick
import org.kde.notificationmanager as NotificationManager

// Qt's native KConfig watcher is kept at the platform adapter, outside views.
QtObject {
    id: root
    required property var desktop
    function sync() {
        const until = settings.notificationsInhibitedUntil
        desktop.setDoNotDisturb(!!until && until.getTime() > Date.now())
    }
    property QtObject _settings: NotificationManager.Settings {
        id: settings
        onSettingsChanged: root.sync()
    }
    property Timer _expiry: Timer {
        interval: 1000
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: root.sync()
    }
    Component.onCompleted: sync()
}
