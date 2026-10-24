"""Application policy for notification delivery, history and user actions.

Queue countdowns, persistent playback and desktop observation have separate
owners. This controller translates service events into those public interfaces.
"""

from __future__ import annotations

from html import escape
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtGui import QImage

from . import apps, artwork, debug, sound
from .config import Config
from .history import HistoryStore
from .model import (
    CLOSED_BY_CALL,
    CLOSED_DISMISSED,
    CLOSED_EXPIRED,
    CLOSED_UNDEFINED,
    JOB_HINT,
    MEDIA_HINT,
    MEDIA_INFO_HINT,
    OSD_HINT,
    URGENCY_CRITICAL,
    URGENCY_LOW,
    URGENCY_NORMAL,
    Notification,
    NotificationModel,
)
from .server import NotificationService
from .strings import Strings
from .notification_queue import NotificationQueue
from .playback import PlaybackSession

#: Job cards live in the same model as notifications but never on the bus, so
#: their ids are kept far away from the ones the server hands out.
JOB_ID_BASE = 1_000_000_001

#: The on-screen displays share one card: a second volume tap replaces the
#: first rather than stacking behind it.
OSD_ID = 2_000_000_001

#: Same idea for what is playing: one card, replaced on every track change.
MEDIA_ID = 2_000_000_002

class IslandController(QObject):
    """Coordinates notification delivery, playback and desktop event adapters."""

    hoveredChanged = Signal()
    inhibitedChanged = Signal()
    mediaChanged = Signal()
    historyChanged = Signal()

    def __init__(
        self,
        config: Config,
        model: NotificationModel,
        service: NotificationService,
        provider: artwork.ArtworkProvider,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._model = model
        self._service = service
        self._provider = provider
        self._queue = NotificationQueue(model, parent=self)
        self._queue.expired.connect(lambda nid: self._close(nid, CLOSED_EXPIRED))
        self._playback = PlaybackSession(provider, self)
        self._playback.changed.connect(self.mediaChanged.emit)
        self._desktop = None
        self._hovered = False
        self._history = HistoryStore(int(config.get("historyLength")), self)
        self._history.changed.connect(self.historyChanged.emit)
        self._strings = Strings(self, str(config.get("language") or ""))
        #: notification id -> the JobView behind it
        self._jobs: dict[int, Any] = {}
        self._job_ids: dict[str, int] = {}
        self._next_job_id = JOB_ID_BASE
        self._sources = None

        # The language is a setting like any other, and the words this side
        # produces — the volume label, the buttons on a copy — have to follow
        # it without a restart.
        config.changed.connect(
            lambda: self._strings.follow(str(config.get("language") or ""))
        )

        service.notify_handler = self.receive
        service.close_handler = self._on_close_requested
        service.clear_history_handler = self._history.clear
        # The applet hands over whatever the history entry stored — a desktop
        # file, a desktop entry or a bare application name — so it goes in as
        # both halves of the lookup.
        service.open_handler = lambda entry: apps.show(entry, entry)
        service.start_handler = apps.start
        service.inhibitedChanged.connect(lambda _: self.inhibitedChanged.emit())

    def attach_media(self, watcher) -> None:
        self._playback.attach(watcher)

    @Property("QVariantMap", notify=mediaChanged)
    def media(self):
        return self._playback.snapshot

    @Slot(str)
    def mediaCommand(self, member):
        self._playback.command(member)

    def _media_payload(self):
        snapshot = self._playback.snapshot
        return snapshot if snapshot.get("title") else {}

    def _media_actions(self):
        snapshot = self._playback.snapshot
        if not snapshot.get("title"):
            return []
        return ["media-previous", "\u23ee", "media-playpause",
                "\u23f8" if snapshot.get("playing") else "\u25b6", "media-next", "\u23ed"]

    @Property("QVariantList", notify=historyChanged)
    def history(self):
        return self._history.entries()

    @Slot()
    def clearHistory(self):
        self._history.clear()

    @Slot(int)
    def openHistoryEntry(self, index):
        entries = self._history.entries()
        if not 0 <= index < len(entries):
            return
        entry = entries[index]
        url = entry.get("url", "")
        if url.startswith(("https://", "http://")):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(url))
        else:
            apps.show(entry.get("desktopEntry") or entry.get("desktopFile") or entry.get("appName", ""))

    def attach_desktop(self, desktop):
        self._desktop = desktop
        desktop.changed.connect(self._desktop_changed)
        desktop.powerChanged.connect(self._power_changed)

    def _desktop_changed(self):
        if self._desktop.blocked or self._desktop.doNotDisturb:
            # Do not replay a burst on leaving fullscreen, lock or DND.
            for notification_id in list(self._model.ids()):
                self._close(notification_id, CLOSED_EXPIRED)

    def _power_changed(self, plugged, percentage):
        title = "已接通电源" if plugged else "正在使用电池"
        icon = "battery-charging" if plugged else "battery"
        suffix = f" · {percentage}%" if percentage >= 0 else ""
        self.show_status("power", icon, -1, title + suffix)

    # -- feeds, endpoints and webhooks -------------------------------------
    def attach_sources(self, manager) -> None:
        """Let the configured sources put cards up like any application."""
        self._sources = manager
        manager.notify.connect(self.receive)

    # -- on-screen displays -----------------------------------------------
    def attach_osd(self, watcher) -> None:
        """Show what Plasma would have drawn in the middle of the screen."""
        watcher.shown.connect(self.show_status)
        watcher.hidden.connect(lambda: self._close(OSD_ID, CLOSED_EXPIRED))

    def show_status(self, kind: str, icon: str, percent: int, text: str) -> None:
        """One card for all of them, replaced in place.

        Holding the volume key down must move the bar inside the banner that is
        already there rather than stack a new one behind it — which is what
        reusing OSD_ID does: the model treats it as a replacement.
        """
        try:
            label = self._strings.word(kind)
        except KeyError:
            label = ""

        if percent >= 0:
            summary = f"{percent} %"
        else:
            summary = text or label
            label = "" if summary == label else label

        hints: dict[str, Any] = {
            "urgency": URGENCY_LOW,
            "suppress-sound": True,
            "transient": True,
            OSD_HINT: True,
        }
        # A layout switch or a toggle has nothing to fill a bar with; only ask
        # for one when there is a number behind it.
        if percent >= 0:
            hints["value"] = percent
        # Turning the volume down while music runs is about that music, so the
        # banner carries it and the card can draw a small player below the bar.
        media = self._media_payload()
        actions: list[str] = []
        if media:
            hints[MEDIA_INFO_HINT] = media
            # Seeing what is playing is half of it; the buttons belong with it.
            actions = self._media_actions()

        self.receive(
            label,  # the kind sits where an application name would
            OSD_ID,
            icon,
            summary,
            text if text and text != summary else "",
            actions,
            hints,
            int(self._config.get("osdTimeout")),
        )

    # -- file operations --------------------------------------------------
    def attach_jobs(self, service) -> None:
        """Show copy/move/delete progress in the island as well."""
        service.changed.connect(self._on_job_changed)
        service.finished.connect(self._on_job_finished)

    def _on_job_changed(self, job) -> None:
        notification_id = self._job_ids.get(job.path)
        if notification_id is None:
            # Counted up, not derived from how many jobs are open: a finished
            # job leaves the dict, so the length goes back down and the next
            # copy would be handed the id of one that is still running — and
            # would take over its card and its pause and cancel buttons.
            notification_id = self._next_job_id
            self._next_job_id += 1
            self._job_ids[job.path] = notification_id
        self._jobs[notification_id] = job

        actions: list[str] = []
        if job.suspendable:
            actions += [
                "job-suspend",
                self._strings.word("resume" if job.suspended else "pause"),
            ]
        if job.killable:
            actions += ["job-cancel", self._strings.word("cancel")]

        # A job carries no icon of its own; the desktop entry is what artwork
        # needs to find the sending application's.
        self.receive(
            job.app_name or job.desktop_entry or self._strings.word("job"),
            notification_id,
            job.icon_name,
            self._job_summary(job),
            self._job_body(job),
            actions,
            {
                "desktop-entry": job.desktop_entry,
                "value": job.percent,
                "urgency": URGENCY_NORMAL,
                "suppress-sound": True,
                "resident": True,
                JOB_HINT: True,
            },
            0,  # stays until the job is over
        )

    def _on_job_finished(self, job) -> None:
        notification_id = self._job_ids.pop(job.path, None)
        if notification_id is None:
            return
        self._jobs.pop(notification_id, None)
        self._close(notification_id, CLOSED_EXPIRED)

    def _job_summary(self, job) -> str:
        """What the operation calls itself: "Copying", "Moving", "Deleting"."""
        return (
            job.info_message
            or getattr(job, "title", "")
            or job.app_name
            or self._strings.word("job")
        )

    @staticmethod
    def _job_body(job) -> str:
        """The description fields, in the order the sender numbered them.

        The card renders its body as styled text, where a newline is just
        whitespace — hence <br>, and hence the escaping around it.
        """
        lines = []
        for _, (label, value) in sorted(job.descriptions.items()):
            if not value:
                continue
            text = escape(str(value))
            lines.append(f"{escape(str(label))}: {text}" if label else text)
        return "<br>".join(lines)

    # -- incoming -------------------------------------------------------
    def receive(
        self,
        app_name: str,
        notification_id: int,
        app_icon: str,
        summary: str,
        body: str,
        raw_actions: list,
        hints: dict[str, Any],
        expire_timeout: int,
        image: QImage | None = None,
    ) -> None:
        urgency = self._urgency(hints)
        reason = self._suppression_reason(app_name, hints, urgency)
        if reason:
            # Dropping a notification without a word is how they go missing, so
            # say so — an inhibition in particular is otherwise invisible.
            print(f"[dynamic-island] suppressed {app_name!r} notification: {reason}")
            # Tell the sender it is gone rather than leaving it waiting for a
            # close that would never come. A file operation has no sender on
            # this bus, so there is nobody to tell.
            # Construct the message below so suppressed notifications remain
            # available in history. Internal status cards are not history.

        # A progress update replacing an existing notification must not beep
        # again on every step.
        is_replacement = self._model.row_of(notification_id) >= 0

        actions, default_action = self._split_actions(raw_actions)
        desktop_entry = str(hints.get("desktop-entry", "") or "")
        # A caller that already holds the artwork — the media card with its
        # downloaded cover — hands it over instead of having it looked up.
        if image is None or image.isNull():
            image = artwork.resolve(hints, app_icon, desktop_entry, app_name=app_name)

        notification = Notification(
            id=notification_id,
            app_name=str(hints.get("x-kde-display-appname", "") or app_name),
            desktop_entry=desktop_entry,
            summary=summary,
            body=body,
            actions=actions,
            default_action=default_action,
            hints=hints,
            urgency=urgency,
            timeout=expire_timeout,
            has_image=not image.isNull(),
            reply_placeholder=self._reply_placeholder(hints, raw_actions),
            resident=bool(hints.get("resident", False)),
            transient=bool(hints.get("transient", False)),
            progress=self._progress(hints),
        )
        notification.accent = (
            artwork.accent_color(image, str(self._config.get("fallbackAccent")))
            if self._config.get("accentFromIcon")
            else str(self._config.get("fallbackAccent"))
        )

        if reason:
            if not any(hints.get(key) for key in (JOB_HINT, OSD_HINT, MEDIA_HINT)):
                self._history.add(notification, image)
                self._service.emit_closed(notification_id, CLOSED_UNDEFINED)
            return

        if notification.has_image:
            self._provider.put(notification_id, image)

        self._queue.put(notification, self._duration_for(notification))

        if not is_replacement and self._config.get("soundEnabled"):
            sound.play_for(hints, str(self._config.get("defaultSound") or ""))

    def _on_close_requested(self, notification_id: int) -> None:
        self._close(notification_id, CLOSED_BY_CALL)

    # -- lifetime -------------------------------------------------------

    def _duration_for(self, notification: Notification) -> int:
        if notification.timeout > 0:
            return notification.timeout
        if notification.timeout == 0:
            return 0  # the sender asked us to keep it until dismissed
        if notification.urgency == URGENCY_CRITICAL and self._config.get(
            "criticalNeverExpires"
        ):
            return 0
        key = "lowUrgencyTimeout" if notification.urgency == URGENCY_LOW else "defaultTimeout"
        return int(self._config.get(key))

    def _close(self, notification_id: int, reason: int) -> None:
        notification = self._queue.remove(notification_id)
        if notification is None:
            return
        # Which card went away, and why. Notifications arrive faster than a
        # person can follow, so "it disappeared" is otherwise unattributable —
        # and it is what the selftest asserts on.
        debug(f"closed #{notification_id} reason={reason}")
        # A file operation was never a notification: nobody is waiting for a
        # NotificationClosed with this id, and a finished copy is not something
        # to keep in the history either.
        is_job = notification is not None and bool(
            notification.hints.get(JOB_HINT)
            or notification.hints.get(OSD_HINT)
            or notification.hints.get(MEDIA_HINT)
        )

        if notification is not None and not is_job:
            self._history.add(notification, self._provider.get(notification_id))
        self._provider.drop(notification_id)
        if not is_job:
            self._service.emit_closed(notification_id, reason)

    # -- filtering ------------------------------------------------------
    def _suppression_reason(
        self, app_name: str, hints: dict[str, Any], urgency: int
    ) -> str:
        """Why this notification is not shown — empty string means it is."""
        if self._desktop and self._desktop.blocked:
            return "fullscreen or locked"
        if hints.get(OSD_HINT):
            return ""  # user-operated controls still respond during DND
        if self._desktop and self._desktop.doNotDisturb:
            return "do not disturb"
        if self._config.get("doNotDisturb"):
            return "do not disturb is on"
        if self._service.inhibited:
            return "another application is holding a notification inhibition"
        if urgency == URGENCY_CRITICAL:
            return ""
        blacklist = {str(entry).lower() for entry in self._config.get("blacklist") or []}
        candidates = {
            app_name.lower(),
            str(hints.get("desktop-entry", "")).lower(),
        }
        if blacklist & candidates:
            return "the sender is on the blacklist"
        return ""

    # -- normalisation ---------------------------------------------------
    @staticmethod
    def _urgency(hints: dict[str, Any]) -> int:
        try:
            value = int(hints.get("urgency", URGENCY_NORMAL))
        except (TypeError, ValueError):
            return URGENCY_NORMAL
        return value if value in (URGENCY_LOW, URGENCY_NORMAL, URGENCY_CRITICAL) else URGENCY_NORMAL

    @staticmethod
    def _split_actions(raw: list) -> tuple[list[dict[str, str]], str]:
        """``[key, label, key, label…]`` → button list plus the default action."""
        actions: list[dict[str, str]] = []
        default_action = ""
        pairs = list(zip(raw[::2], raw[1::2]))
        for key, label in pairs:
            key, label = str(key), str(label)
            if key == "default":
                default_action = key
                continue
            if key == "inline-reply":
                continue  # rendered as the reply field, not as a button
            actions.append({"key": key, "label": label or key})
        return actions, default_action

    @staticmethod
    def _reply_placeholder(hints: dict[str, Any], raw_actions: list) -> str:
        keys = {str(key) for key in raw_actions[::2]}
        if "inline-reply" not in keys:
            return ""
        return str(hints.get("x-kde-reply-placeholder-text", "") or "Reply…")

    @staticmethod
    def _progress(hints: dict[str, Any]) -> int:
        if "value" not in hints:
            return -1
        try:
            return max(0, min(100, int(hints["value"])))
        except (TypeError, ValueError):
            return -1

    # -- QML API ---------------------------------------------------------
    @Slot(int)
    def dismiss(self, notification_id: int) -> None:
        self._close(notification_id, CLOSED_DISMISSED)

    @Slot()
    def dismissAll(self) -> None:
        for notification_id in self._model.ids():
            self._close(notification_id, CLOSED_DISMISSED)

    @Slot(int, str)
    def invokeAction(self, notification_id: int, action_key: str) -> None:
        notification = self._model.get(notification_id)
        if notification is None:
            return

        # The player buttons ride along on the volume banner too, so route by
        # the key rather than by which card it was drawn on.
        member = {
            "media-previous": "Previous",
            "media-playpause": "PlayPause",
            "media-next": "Next",
        }.get(action_key)
        if member is not None:
            self._playback.command(member)
            return

        # A card from a feed, an endpoint or a webhook carries its buttons in
        # the manager rather than on the bus: there is no sender to tell.
        if self._sources is not None and self._sources.owns(notification_id):
            self._sources.handle_action(notification_id, action_key)
            if not notification.resident:
                self._close(notification_id, CLOSED_DISMISSED)
            return

        job = self._jobs.get(notification_id)
        if job is not None:
            # The buttons on a file operation talk to the copying application,
            # not to the notification bus. The card stays: the sender answers
            # by suspending or terminating, and that is what redraws it.
            if action_key == "job-cancel":
                job.request_cancel()
            elif action_key == "job-suspend":
                job.request_resume() if job.suspended else job.request_suspend()
            return

        self._service.emit_action(notification_id, action_key)
        if not notification.resident:
            self._close(notification_id, CLOSED_DISMISSED)

    @Slot(int)
    def activateDefault(self, notification_id: int) -> None:
        notification = self._model.get(notification_id)
        if notification is None:
            return
        # The track banner, and the volume display while it carries one: a
        # click on either means the player. The card stays — its buttons are
        # what a click on it is usually for, and losing the banner because you
        # reached for the wrong pixel is rude.
        plays_media = notification_id == MEDIA_ID or (
            notification_id == OSD_ID and bool(notification.hints.get(MEDIA_INFO_HINT))
        )
        if plays_media:
            self._playback.activate()
            return

        if notification_id == OSD_ID:
            self.dismiss(notification_id)  # a volume bar has nothing to open
            return

        if notification_id in self._jobs:
            # A stray click must not disturb a running copy; the card has its
            # own buttons, and swiping still gets rid of it.
            return

        if self._sources is not None and self._sources.owns(notification_id):
            # A feed entry or a webhook card. Its click opens the link it
            # carried, and there is no application behind it to bring
            # forward — "heise online" is not something to look for a window
            # of, however much the card says it came from there.
            if notification.default_action:
                self.invokeAction(notification_id, notification.default_action)
            else:
                self.dismiss(notification_id)
            return

        if notification.default_action:
            self.invokeAction(notification_id, notification.default_action)
            # And bring the sender forward ourselves. The action tells the
            # application which message the click was about — Discord opens
            # that channel, a mail client that mail — but the window it
            # happens in cannot come to the front on its own: on Wayland only
            # the holder of an activation token may raise a window, and the
            # spec's way of handing one over (the ActivationToken signal)
            # needs a token from the compositor that KWin only gives to
            # surfaces, not over the bus. Without this the application does
            # the right thing where nobody can see it.
            self._raise_sender(notification)
            return

        # Nothing declared, so do what a person expects from a click: bring up
        # whoever is talking. Most applications are single-instance and raise
        # their existing window rather than starting a second one.
        self._raise_sender(notification)
        self.dismiss(notification_id)

    @staticmethod
    def _raise_sender(notification) -> None:
        """Show the application behind a notification, if we can name it.

        Both names go in: the desktop entry is the reliable one, the app name
        is what is left when the sender did not send an entry — and "Firefox"
        still finds firefox.desktop.
        """
        apps.show(notification.desktop_entry, notification.app_name)

    @Slot(int, str)
    def sendReply(self, notification_id: int, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._service.emit_reply(notification_id, text)
        self._close(notification_id, CLOSED_DISMISSED)

    @Slot(bool)
    def setHovered(self, hovered: bool) -> None:
        if hovered == self._hovered:
            return
        self._hovered = hovered
        self.hoveredChanged.emit()
        self._playback.set_hovered(hovered)
        self._queue.set_paused(hovered and bool(self._config.get("pauseOnHover")))

    def _is_hovered(self) -> bool:
        return self._hovered

    def _is_inhibited(self) -> bool:
        return self._service.inhibited

    hovered = Property(bool, _is_hovered, notify=hoveredChanged)
    inhibited = Property(bool, _is_inhibited, notify=inhibitedChanged)
