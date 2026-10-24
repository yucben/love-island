"""Persistent player selection, cover lifetime and media commands.

An MPRIS adapter supplies ``current()``, changed/replaced signals and command().
Callers see one snapshot regardless of which player or cover transport is used.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import apps

MEDIA_ART_ID = 2_000_000_003


class PlaybackSession(QObject):
    changed = Signal()

    def __init__(self, provider, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._source = None
        self._track = None
        self._cover = ""
        self._serial = 0
        self._covers = {}
        self._network = None
        self._paused_visible = False
        self._hovered = False
        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.setInterval(3000)
        self._pause_timer.timeout.connect(self._hide_paused)

    def attach(self, source):
        self._source = source
        source.changed.connect(self._changed)
        source.replaced.connect(self._replaced)
        self._select(source.current(), announce_pause=False)

    def _changed(self, track):
        self._select(self._source.current(), announce_pause=True)

    def _replaced(self, track):
        self._select(track, announce_pause=False)

    def _select(self, track, announce_pause):
        self._pause_timer.stop()
        self._track = track
        self._paused_visible = bool(track and (track.playing or announce_pause))
        if track is None:
            self._set_cover(QImage())
        else:
            self._load_cover(track.art_url)
            if not track.playing and announce_pause:
                self._pause_timer.start()
        self.changed.emit()

    def set_hovered(self, hovered):
        self._hovered = hovered

    def _hide_paused(self):
        if self._hovered:
            self._pause_timer.start()
        else:
            self._paused_visible = False
            self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def snapshot(self):
        track = self._track
        if track is None:
            return {"visible": False}
        return {"title": track.title, "artist": track.artist, "cover": self._cover,
                "playing": bool(track.playing), "player": track.identity,
                "visible": bool(track.playing or self._paused_visible)}

    def command(self, member):
        if member in ("Previous", "PlayPause", "Next") and self._source and self._track:
            self._source.command(self._track.bus_name, member)

    def activate(self):
        if self._track:
            apps.show(self._track.desktop_entry, self._track.identity)

    def _load_cover(self, url):
        if not url:
            self._set_cover(QImage())
        elif url in self._covers:
            self._set_cover(self._covers[url])
        elif url.startswith(("https://", "http://")):
            self._set_cover(QImage())
            if self._network is None:
                self._network = QNetworkAccessManager(self)
            reply = self._network.get(QNetworkRequest(QUrl(url)))
            reply.finished.connect(lambda: self._downloaded(url, reply))
        else:
            path = QUrl(url).toLocalFile() if url.startswith("file://") else url
            self._remember(url, QImage(path))
            self._set_cover(self._covers[url])

    def _downloaded(self, url, reply):
        image = QImage()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            image.loadFromData(reply.readAll())
        reply.deleteLater()
        self._remember(url, image)
        if self._track and self._track.art_url == url:
            self._set_cover(image)
            self.changed.emit()

    def _remember(self, url, image):
        if url not in self._covers and len(self._covers) >= 32:
            self._covers.pop(next(iter(self._covers)))
        self._covers[url] = image

    def _set_cover(self, image):
        if image.isNull():
            self._provider.drop(MEDIA_ART_ID)
            self._cover = ""
        else:
            self._serial += 1
            self._provider.put(MEDIA_ART_ID, image)
            self._cover = f"image://island/{MEDIA_ART_ID}?{self._serial}"
