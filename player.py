import logging
import socket
import urllib.request
from typing import Optional
from threading import Lock

import miniaudio
from miniaudio import FileFormat, SampleFormat, PlaybackDevice, IceCastClient

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QThread

logger = logging.getLogger(__name__)

_SUPPORTED_FORMATS = {FileFormat.MP3, FileFormat.FLAC, FileFormat.VORBIS, FileFormat.WAV}
_STREAM_TIMEOUT = 15


class PlayWorker(QThread):
    ready = pyqtSignal(object, object, object)
    error = pyqtSignal(str)

    def __init__(self, url: str, title_cb=None):
        super().__init__()
        self._url = url
        self._title_cb = title_cb

    def run(self):
        try:
            socket.setdefaulttimeout(_STREAM_TIMEOUT)
            client = IceCastClient(self._url, update_stream_title=self._title_cb)
            fmt = client.audio_format
            if fmt == FileFormat.UNKNOWN:
                raise RuntimeError(
                    "Unsupported audio format (only MP3, FLAC, Ogg Vorbis, WAV supported)"
                )
            if fmt not in _SUPPORTED_FORMATS:
                raise RuntimeError(f"Unsupported audio format: {fmt}")

            stream = miniaudio.stream_any(
                client,
                source_format=fmt,
                output_format=SampleFormat.SIGNED16,
                nchannels=2,
                sample_rate=44100,
            )
            device = PlaybackDevice()
            device.start(stream)
            self.ready.emit(client, stream, device)
        except Exception as e:
            self.error.emit(str(e))


class Player(QObject):
    state_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    media_changed = pyqtSignal(str)
    song_changed = pyqtSignal(str)
    station_info_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._device: Optional[PlaybackDevice] = None
        self._client: Optional[IceCastClient] = None
        self._current_url: Optional[str] = None
        self._playing = False
        self._volume = 100
        self._lock = Lock()
        self._worker: Optional[PlayWorker] = None
        self._play_seq = 0

        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_state)
        self._poll.start(200)

    def _poll_state(self):
        was = self._playing
        is_now = bool(self._device and self._device.running)
        if is_now != was:
            self._playing = is_now
            self.state_changed.emit("playing" if is_now else "stopped")

    def _on_stream_title(self, client, title: str):
        self.song_changed.emit(title)

    def get_station_info(self) -> dict:
        if not self._client:
            return {}
        return {
            "icy-name": self._client.station_name,
            "icy-genre": self._client.station_genre,
        }

    def set_proxy(self, proxy_url: Optional[str]):
        if proxy_url:
            handler = urllib.request.ProxyHandler({
                "http": proxy_url, "https": proxy_url,
            })
            opener = urllib.request.build_opener(handler)
        else:
            opener = urllib.request.build_opener()
        opener.addheaders = [("User-Agent", "TrayRadio/1.0")]
        urllib.request.install_opener(opener)

    def _on_play_ready(self, client, stream, device):
        with self._lock:
            seq = getattr(self.sender(), "_seq", -1) if self.sender() else -1
            if seq != self._play_seq:
                client._stop_stream = True
                return
            self._worker = None
            self._client = client
            self._stream = stream
            self._device = device
            self._playing = True
            self.media_changed.emit(self._current_url or "")
            self.station_info_changed.emit(self.get_station_info())
            self.state_changed.emit("playing")
            logger.info(f"Playing: {client.station_name}")

    def _on_play_error(self, msg: str):
        with self._lock:
            seq = getattr(self.sender(), "_seq", -1) if self.sender() else -1
            if seq != self._play_seq:
                return
            self._worker = None
            self._current_url = None
            self._playing = False
        logger.error(f"Play failed: {msg}")
        self.error_occurred.emit(msg)

    def play(self, url: str):
        with self._lock:
            self._cancel_worker()
            self._cleanup()
            self._current_url = url
            self._play_seq += 1
            self._worker = PlayWorker(url, title_cb=self._on_stream_title)
            self._worker._seq = self._play_seq
            self._worker.ready.connect(self._on_play_ready)
            self._worker.error.connect(self._on_play_error)
            self._worker.finished.connect(self._worker.deleteLater)
            self._worker.start()

    def _cancel_worker(self):
        if self._worker and self._worker.isRunning():
            self._worker.ready.disconnect()
            self._worker.error.disconnect()
            self._worker.terminate()
            self._worker.wait(2000)
            self._worker.deleteLater()
            self._worker = None

    def _cleanup(self):
        if self._device:
            try:
                self._device.stop()
            except Exception:
                pass
            self._device = None
        if self._client:
            self._client._stop_stream = True
            self._client = None
        self._stream = None
        self._playing = False

    def stop(self):
        with self._lock:
            self._cancel_worker()
            self._cleanup()
        self._current_url = None
        self.state_changed.emit("stopped")

    def pause(self):
        with self._lock:
            if self._device and self._device.running:
                self._device.stop()
                self._playing = False
                self.state_changed.emit("paused")

    def resume(self):
        if self._current_url:
            self.play(self._current_url)

    def toggle_play_pause(self):
        if self._playing:
            self.pause()
        elif self._current_url:
            self.resume()

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def current_url(self) -> Optional[str]:
        return self._current_url

    def set_volume(self, volume: int):
        self._volume = max(0, min(100, volume))

    def get_volume(self) -> int:
        return self._volume


