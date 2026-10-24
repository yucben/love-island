"""FIFO delivery with an interrupting status card and foreground-only timeouts.

The controller supplies normalised messages and their display durations. This
module owns ordering, capacity and countdowns; it never touches D-Bus or history.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal


class _Countdown:
    def __init__(self, owner, duration, expired):
        self.remaining = duration
        self.started = 0.0
        self.timer = QTimer(owner)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(expired)

    def pause(self):
        if self.timer.isActive():
            self.remaining = max(0, self.remaining - int((time.monotonic() - self.started) * 1000))
            self.timer.stop()

    def resume(self):
        if not self.timer.isActive():
            self.started = time.monotonic()
            self.timer.start(max(1, self.remaining))

    def dispose(self):
        self.timer.stop()
        self.timer.deleteLater()


class NotificationQueue(QObject):
    """A message's timeout runs only while it is in front and not paused.

``expired`` covers timeout and capacity eviction. Its receiver removes the
message, archives it and acknowledges the sending application as appropriate.
"""
    expired = Signal(int)

    def __init__(self, model, capacity=100, parent=None):
        super().__init__(parent)
        self._model = model
        self._capacity = capacity
        self._timers = {}
        self._paused = False

    def put(self, notification, duration):
        self._cancel(notification.id)
        self._model.put(notification)
        for notification_id in self._model.ids()[self._capacity:]:
            self.expired.emit(notification_id)
        if self._model.get(notification.id) is not None and duration > 0:
            self._timers[notification.id] = _Countdown(
                self, duration, lambda nid=notification.id: self.expired.emit(nid)
            )
        self._sync()

    def remove(self, notification_id):
        self._cancel(notification_id)
        notification = self._model.get(notification_id)
        self._model.remove(notification_id)
        self._sync()
        return notification

    def set_paused(self, paused):
        self._paused = paused
        self._sync()

    def _cancel(self, notification_id):
        timer = self._timers.pop(notification_id, None)
        if timer is not None:
            timer.dispose()

    def _sync(self):
        ids = self._model.ids()
        front = ids[0] if ids else None
        for notification_id, timer in self._timers.items():
            if notification_id == front and not self._paused:
                timer.resume()
            else:
                timer.pause()
