import logging
import socket
import ssl
import threading
import urllib.request
from typing import Optional, Callable
from threading import Lock

import miniaudio
from miniaudio import FileFormat, SampleFormat, PlaybackDevice, IceCastClient


def get_output_devices() -> list[dict]:
    devices = [{"name": "(System Default)", "id": None}]
    try:
        for d in miniaudio.Devices().get_playbacks():
            devices.append({"name": d["name"], "id": d["id"]})
    except Exception:
        pass
    return devices


def find_device_id(name: str):
    if not name:
        return None
    try:
        for d in miniaudio.Devices().get_playbacks():
            if d["name"] == name:
                return d["id"]
    except Exception:
        pass
    return None

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QThread

logger = logging.getLogger(__name__)

_SUPPORTED_FORMATS = {FileFormat.MP3, FileFormat.FLAC, FileFormat.VORBIS, FileFormat.WAV}
_STREAM_TIMEOUT = 15
_AAC_READ_CHUNK = 8192
_AAC_PCM_THRESHOLD = 131072


def _ct_to_codec(content_type: str) -> Optional[str]:
    ct = content_type.split(";")[0].strip().lower()
    mapping = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/ogg": "vorbis",
        "audio/vorbis": "vorbis",
        "audio/flac": "flac",
        "audio/wav": "wav",
        "audio/wave": "wav",
        "audio/x-wav": "wav",
        "audio/aac": "aac",
        "audio/aacp": "aac",
        "audio/x-aac": "aac",
        "audio/mp4": "aac",
        "audio/x-m4a": "aac",
    }
    return mapping.get(ct)


def _parse_icy_meta(data: bytes, title_cb: Callable = None):
    if not data or not title_cb:
        return
    try:
        text = data.decode("utf-8", errors="replace").strip("\x00").strip()
        for part in text.split(";"):
            part = part.strip()
            if part.lower().startswith("streamtitle="):
                val = part.split("=", 1)[1].strip("'\"")
                if val:
                    title_cb(val)
    except Exception:
        pass


def _av_stream_iter(url: str, title_cb: Callable = None):
    import av
    import numpy as np
    from queue import Queue

    resp = urllib.request.urlopen(url)
    icy_metaint = int(resp.headers.get("icy-metaint", 0))

    # Detect codec from Content-Type
    ct = resp.headers.get("Content-Type", "")
    codec_name = _ct_to_codec(ct)

    if not codec_name:
        peek = resp.read(4096)
        for try_name in ("aac", "mp3", "vorbis", "flac", "opus"):
            try:
                c = av.CodecContext.create(try_name, "r")
                pkts = c.parse(peek)
                if pkts:
                    codec_name = try_name
                    break
            except Exception:
                continue
        if not codec_name:
            raise RuntimeError(f"Cannot detect audio codec (Content-Type: {ct})")
    else:
        peek = b""

    codec = av.CodecContext.create(codec_name, "r")
    resampler = av.AudioResampler(
        format="s16",
        layout="stereo",
        rate=44100,
    )

    # Background reader thread feeds an unbounded queue so the generator never blocks on I/O
    _queue = Queue()
    _reader_stop = threading.Event()

    def _reader():
        try:
            if peek:
                _queue.put(peek)
            while not _reader_stop.is_set():
                try:
                    raw = resp.read(_AAC_READ_CHUNK)
                except Exception:
                    break
                if not raw:
                    break
                _queue.put(raw)
        except Exception:
            pass
        finally:
            try:
                _queue.put_nowait(None)
            except Exception:
                pass

    _reader_thread = threading.Thread(target=_reader, daemon=True)
    _reader_thread.start()

    bytes_since_meta = 0
    meta_buf = b""
    pcm_buf = b""
    eof = False

    def _abort():
        _reader_stop.set()
        try:
            resp.close()
        except Exception:
            pass

    def gen():
        nonlocal bytes_since_meta, meta_buf, pcm_buf, eof, resampler
        from queue import Empty as _QueueEmpty

        want_frames = yield  # receive framecount (or None on first next())

        while True:
            # Decode more PCM if buffer is low
            if not eof and len(pcm_buf) < _AAC_PCM_THRESHOLD:
                had_data = True
                while had_data and len(pcm_buf) < _AAC_PCM_THRESHOLD:
                    try:
                        raw = _queue.get_nowait()
                    except _QueueEmpty:
                        break
                    had_data = True
                    if raw is None:
                        eof = True
                        break
                    if icy_metaint:
                        meta_buf += raw
                        clean = b""
                        while meta_buf:
                            avail = icy_metaint - bytes_since_meta
                            if avail > 0 and len(meta_buf) >= avail:
                                clean += meta_buf[:avail]
                                meta_buf = meta_buf[avail:]
                                bytes_since_meta += avail
                            elif avail > 0:
                                break
                            if bytes_since_meta >= icy_metaint:
                                if meta_buf:
                                    meta_len = meta_buf[0] * 16
                                    meta_buf = meta_buf[1:]
                                    if meta_len > 0 and len(meta_buf) >= meta_len:
                                        _parse_icy_meta(meta_buf[:meta_len], title_cb)
                                        meta_buf = meta_buf[meta_len:]
                                    bytes_since_meta = 0
                        raw = clean
                    else:
                        meta_buf = b""

                    packets = codec.parse(raw)
                    for packet in packets:
                        try:
                            for frame in codec.decode(packet):
                                for out in resampler.resample(frame):
                                    pcm_buf += out.to_ndarray().tobytes()
                        except Exception:
                            pass

                if eof:
                    # Flush remaining packets from the decoder
                    packets = codec.parse(b"")
                    for packet in packets:
                        try:
                            for frame in codec.decode(packet):
                                for out in resampler.resample(frame):
                                    pcm_buf += out.to_ndarray().tobytes()
                        except Exception:
                            pass
                    try:
                        for frame in codec.decode(None):
                            for out in resampler.resample(frame):
                                pcm_buf += out.to_ndarray().tobytes()
                        for out in resampler.resample(None):
                            pcm_buf += out.to_ndarray().tobytes()
                    except Exception:
                        pass

            # Yield requested amount
            if want_frames is None:
                want_frames = 2048
            need = want_frames * 4  # 2 channels * 2 bytes
            if len(pcm_buf) >= need:
                out = pcm_buf[:need]
                pcm_buf = pcm_buf[need:]
            else:
                out = pcm_buf
                pcm_buf = b""

            want_frames = yield out

            if eof and not pcm_buf and not out:
                return

    class _AvStreamWrapper:
        def __init__(self):
            self._gen = gen()
            self._abort = _abort
            next(self._gen)

        def send(self, value):
            return self._gen.send(value)

        def __next__(self):
            return next(self._gen)

        def close(self):
            self._gen.close()

        def __iter__(self):
            return self

    return _AvStreamWrapper()


def _av_container_stream(url: str, title_cb: Callable = None):
    import av
    import numpy as np

    container = av.open(url, timeout=30)
    resampler = av.AudioResampler(
        format="s16",
        layout="stereo",
        rate=44100,
    )

    _abort = threading.Event()
    pcm_buf = b""

    def abort():
        _abort.set()
        try:
            container.close()
        except Exception:
            pass

    def gen():
        nonlocal pcm_buf
        want_frames = yield
        while True:
            if not _abort.is_set() and len(pcm_buf) < 131072:
                try:
                    for packet in container.demux():
                        if _abort.is_set():
                            break
                        for frame in packet.decode():
                            for out in resampler.resample(frame):
                                pcm_buf += out.to_ndarray().tobytes()
                            if len(pcm_buf) >= 131072:
                                break
                        if len(pcm_buf) >= 131072:
                            break
                except Exception:
                    pass

            if want_frames is None:
                want_frames = 2048
            need = want_frames * 4
            if len(pcm_buf) >= need:
                out = pcm_buf[:need]
                pcm_buf = pcm_buf[need:]
            else:
                out = pcm_buf
                pcm_buf = b""
            want_frames = yield out
            if not out and _abort.is_set():
                return

    wrapper = type("_AvContainerWrapper", (), {})()
    wrapper._gen = gen()
    wrapper._abort = abort
    wrapper.send = wrapper._gen.send
    wrapper.__next__ = lambda: next(wrapper._gen)
    next(wrapper._gen)
    return wrapper


class PlayWorker(QThread):
    ready = pyqtSignal(object, object, object)
    error = pyqtSignal(str)

    def __init__(self, url: str, codec_hint: str = "", title_cb=None, device_name: str = ""):
        super().__init__()
        self._url = url
        self._codec_hint = codec_hint
        self._title_cb = title_cb
        self._device_name = device_name

    def _make_device(self):
        device_id = find_device_id(self._device_name)
        return PlaybackDevice(device_id=device_id)

    def run(self):
        try:
            socket.setdefaulttimeout(_STREAM_TIMEOUT)
            codec = self._codec_hint.lower() if self._codec_hint else ""

            if self.isInterruptionRequested():
                return

            # Skip IceCastClient entirely for codecs miniaudio can't handle
            if codec and not any(
                s in codec for s in ("mp3", "mpeg", "flac", "vorbis", "ogg", "wav")
            ):
                stream = _av_stream_iter(self._url, title_cb=self._title_cb)
                if self.isInterruptionRequested():
                    return
                device = self._make_device()
                device.start(stream)
                self.ready.emit(None, stream, device)
                return

            client = IceCastClient(self._url, update_stream_title=lambda c, t: self._title_cb(t))
            fmt = client.audio_format

            if self.isInterruptionRequested():
                client._stop_stream = True
                return

            if fmt in _SUPPORTED_FORMATS:
                try:
                    stream = miniaudio.stream_any(
                        client,
                        source_format=fmt,
                        output_format=SampleFormat.SIGNED16,
                        nchannels=2,
                        sample_rate=44100,
                    )
                    device = self._make_device()
                    device.start(stream)
                except Exception:
                    if client is not None:
                        client._stop_stream = True
                    try:
                        stream = _av_container_stream(self._url, title_cb=self._title_cb)
                    except Exception:
                        stream = _av_stream_iter(self._url, title_cb=self._title_cb)
                    if self.isInterruptionRequested():
                        return
                    device = self._make_device()
                    device.start(stream)
                    self.ready.emit(None, stream, device)
                    return
                self.ready.emit(client, stream, device)
            else:
                client._stop_stream = True
                try:
                    stream = _av_stream_iter(self._url, title_cb=self._title_cb)
                    if self.isInterruptionRequested():
                        return
                    device = self._make_device()
                    device.start(stream)
                    self.ready.emit(None, stream, device)
                except Exception as av_err:
                    raise RuntimeError(
                        f"Unsupported audio format (miniaudio: {fmt}, PyAV: {av_err})"
                    )
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
        self._stream_gen: Optional[object] = None
        self._current_url: Optional[str] = None
        self._playing = False
        self._volume = 100
        self._lock = Lock()
        self._worker: Optional[PlayWorker] = None
        self._play_seq = 0
        self._shutdown_done = False
        self._old_workers: list[PlayWorker] = []
        self._reap_timer = QTimer(self)
        self._reap_timer.timeout.connect(self._reap_zombies)
        self._reap_timer.start(5000)
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_state)
        self._poll.start(200)

    def _poll_state(self):
        was = self._playing
        is_now = bool(self._device and self._device.running)
        if is_now != was:
            self._playing = is_now
            self.state_changed.emit("playing" if is_now else "stopped")

    def _on_stream_title(self, title: str):
        self.song_changed.emit(title)

    def get_station_info(self) -> dict:
        if not self._client:
            return {}
        return {
            "icy-name": getattr(self._client, "station_name", ""),
            "icy-genre": getattr(self._client, "station_genre", ""),
        }

    def set_proxy(self, proxy_url: Optional[str]):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        https_handler = urllib.request.HTTPSHandler(context=ctx)
        if proxy_url:
            proxy_handler = urllib.request.ProxyHandler({
                "http": proxy_url, "https": proxy_url,
            })
            opener = urllib.request.build_opener(proxy_handler, https_handler)
        else:
            opener = urllib.request.build_opener(https_handler)
        opener.addheaders = [("User-Agent", "TrayRadio/1.0")]
        urllib.request.install_opener(opener)

    def _on_play_ready(self, client, stream, device):
        with self._lock:
            seq = getattr(self.sender(), "_seq", -1) if self.sender() else -1
            if seq != self._play_seq:
                if client is not None:
                    client._stop_stream = True
                if device is not None:
                    try:
                        device.stop()
                    except Exception:
                        pass
                if stream is not None:
                    try:
                        abort = getattr(stream, "_abort", None)
                        if abort:
                            abort()
                    except Exception:
                        pass
                return
            # Worker's thread is done — deleteLater will fire via finished
            # connection (from play()).  Keeping self._worker past this point
            # would leave a dangling C++ reference once deleteLater processes.
            self._worker = None
            self._client = client
            self._stream = stream
            self._device = device
            self._stream_gen = stream
            self._playing = True
            self.media_changed.emit(self._current_url or "")
            self.station_info_changed.emit(self.get_station_info())
            name = client.station_name if client else ""
            logger.info(f"Playing: {name or self._current_url}")
            # Emit directly so "Now playing" notification fires reliably
            # (_poll_state relies on a race with _device being set first)
            self.state_changed.emit("playing")

    def _on_play_error(self, msg: str):
        with self._lock:
            seq = getattr(self.sender(), "_seq", -1) if self.sender() else -1
            if seq != self._play_seq:
                return
            self._current_url = None
            self._playing = False
        logger.error(f"Play failed: {msg}")
        self.error_occurred.emit(msg)

    def play(self, url: str, codec_hint: str = "", output_device: str = ""):
        with self._lock:
            self._cancel_worker()
            self._cleanup()
            self._current_url = url
            self._play_seq += 1
            self._worker = PlayWorker(url, codec_hint=codec_hint, title_cb=self._on_stream_title, device_name=output_device)
            self._worker._seq = self._play_seq
            self._worker.ready.connect(self._on_play_ready)
            self._worker.error.connect(self._on_play_error)
            self._worker.start()

    def _cancel_worker(self):
        if not self._worker:
            return
        w = self._worker
        self._worker = None
        try:
            if w.isRunning():
                w.requestInterruption()
        except RuntimeError:
            return
        # Always stash — prevents Python GC from destroying the C++ QThread
        # before the event loop processes its finished signal.
        self._stash_worker(w)

    def _stash_worker(self, w: PlayWorker):
        self._old_workers.append(w)

    def _reap_zombies(self):
        alive = []
        for w in self._old_workers:
            try:
                if w.isRunning():
                    alive.append(w)
            except RuntimeError:
                pass
        self._old_workers = alive

    def _cleanup(self):
        if self._stream_gen is not None:
            try:
                abort = getattr(self._stream_gen, "_abort", None)
                if abort:
                    abort()
            except Exception:
                pass
            self._stream_gen = None
        if self._device:
            try:
                t = threading.Thread(target=self._device.stop, daemon=True)
                t.start()
                t.join(2.0)
            except Exception:
                pass
            self._device = None
        if self._client is not None:
            self._client._stop_stream = True
            self._client = None
        self._stream = None
        self._playing = False

    def shutdown(self):
        if self._shutdown_done:
            return
        with self._lock:
            self._shutdown_done = True
            self._play_seq += 1
            self._cancel_worker()
            self._cleanup()

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


