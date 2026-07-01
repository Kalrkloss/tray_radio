import logging
import socket
import struct
import threading
import time
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal, QTimer

logger = logging.getLogger(__name__)


# SlimProto uses 4-byte opcodes
OPCODE_HELO = b"HELO"
OPCODE_BYE  = b"BYE!"
OPCODE_STRM = b"strm"
OPCODE_STAT = b"STAT"
OPCODE_VOLU = b"VOLU"
OPCODE_SETD = b"setd"
OPCODE_AUDG = b"audg"
OPCODE_GRFE = b"grfe"
OPCODE_GRFB = b"grfb"


def _build_helo(mac: bytes, caps: bytes = b"") -> bytes:
    device_id = 5
    revision = 2
    uuid = mac + b"\x00" * 10
    payload = struct.pack(
        "!B B 6s H 16s I I 2s",
        device_id,
        revision,
        mac[:6],
        0,    # wlan_channellist
        uuid[:16],
        0,    # bytes_received_H
        0,    # bytes_received_L
        b"",  # lang
    )
    caps_str = b"Model=squeezelite,AccuratePlayPoints=1,HasDigitalOut=1," \
               b"Firmware=1.0,aac,flc,oog,pcm,syn2" + caps
    return payload + caps_str


def _build_stat(event: bytes, now_ms: int = 0, elapsed_seconds: int = 0,
                server_timestamp: int = 0) -> bytes:
    ev = event[:4].ljust(4, b"\x00")
    ms_played = elapsed_seconds * 1000
    return struct.pack(
        "!4s"      # event
        "BBB"      # num_crlf, mas_initialized, mas_mode
        "II"       # stream_buffer_size, stream_buffer_fullness
        "II"       # bytes_received_H, bytes_received_L
        "H"        # signal_strength
        "I"        # jiffies
        "II"       # output_buffer_size, output_buffer_fullness
        "H"        # elapsed_seconds (server reads n = 2 bytes)
        "I"        # voltage (server reads N = 4 bytes)
        "I"        # elapsed_milliseconds
        "H"        # server_timestamp (server reads n = 2 bytes)
        "H"        # error_code
        "BB",      # padding to 53 bytes (server accepts 53 or 57)
        ev,
        0, 0, 0,            # num_crlf=0, mas_initialized=0, mas_mode=0
        400000,             # stream_buffer_size
        0,                  # stream_buffer_fullness
        0,                  # bytes_received_H
        0,                  # bytes_received_L
        0xffff,             # signal_strength
        now_ms,             # jiffies
        400000,             # output_buffer_size
        0,                  # output_buffer_fullness
        elapsed_seconds & 0xFFFF,  # elapsed_seconds (16-bit)
        0,                  # voltage
        ms_played,          # elapsed_milliseconds
        server_timestamp & 0xFFFF, # server_timestamp (16-bit)
        0,                  # error_code
        0, 0,               # padding
    )


def _build_volu(volume: int) -> bytes:
    return struct.pack("!H", max(0, min(100, volume)))


def _extract_url_from_strm(data: bytes) -> str:
    for pattern in [b"GET ", b"get ", b"icy ", b"ICY "]:
        idx = data.find(pattern)
        if idx >= 0:
            line_end = data.find(b"\r\n", idx)
            if line_end < 0:
                line_end = data.find(b"\n", idx)
            if line_end < 0:
                line_end = len(data)
            line = data[idx:line_end].decode("utf-8", errors="replace")
            parts = line.split(" ")
            if len(parts) >= 2:
                return parts[1]
    for pattern in [b"http://", b"https://", b"HTTP://", b"HTTPS://"]:
        idx = data.find(pattern)
        if idx >= 0:
            line_end = data.find(b"\x00", idx)
            if line_end < 0:
                line_end = len(data)
            url = data[idx:line_end].decode("utf-8", errors="replace")
            url = url.rstrip("\x00\r\n\t ")
            return url
    return ""


def _parse_strm(data: bytes) -> Optional[dict]:
    if len(data) < 4:
        return None
    command = chr(data[0]) if 0 <= data[0] < 128 else "?"
    autostart = chr(data[1]) if 0 <= data[1] < 128 else "?"
    fmt = chr(data[2]) if 0 <= data[2] < 128 else "?"
    replay_gain = struct.unpack("!I", data[14:18])[0] if len(data) >= 18 else 0
    if len(data) >= 22:
        server_port = struct.unpack("!H", data[18:20])[0]
        server_ip = socket.inet_ntoa(data[20:24])
    else:
        server_port = 0
        server_ip = "0.0.0.0"
    url = _extract_url_from_strm(data)
    return {
        "command": command,
        "autostart": autostart,
        "format": fmt,
        "server_port": server_port,
        "server_ip": server_ip,
        "url": url,
        "replay_gain": replay_gain,
    }


def _parse_audg(data: bytes) -> int:
    if len(data) >= 16:
        return struct.unpack("!I", data[12:16])[0]
    return -1


class SlimProtoClient(QObject):
    stream_ready = pyqtSignal(str, str, str)
    volume_changed = pyqtSignal(int)
    pause_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, host: str, port: int = 3483, mac: bytes = None, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._mac = mac or b"\x00\x00\x00\x00\x00\x01"
        self._sock: Optional[socket.socket] = None
        self._running = False
        self._connected = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._stat_timer = QTimer(self)
        self._stat_timer.timeout.connect(self._send_heartbeat)
        self._stat_timer.setInterval(5000)
        self._current_volume = 100
        self._current_url = ""
        self._mode = "stop"
        self._last_replay_gain = 0
        self._stream_start_time = 0.0
        self._start_time = 0.0

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect_to_server(self):
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._stat_timer.start()
        self._thread = threading.Thread(target=self._connect_run, daemon=True)
        self._thread.start()

    def disconnect_from_server(self):
        self._running = False
        self._stop_event.set()
        QTimer.singleShot(0, self._stat_timer.stop)
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        self._connected = False

    def _connect_run(self):
        try:
            self._sock = socket.create_connection(
                (self._host, self._port), timeout=10.0
            )
            self._sock.settimeout(10.0)
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._connected = True
            self._start_time = time.time()
            logger.info("SlimProto connected to %s:%d", self._host, self._port)
            self._send_helo()
            self._receive_loop()
            logger.info("SlimProto receive loop ended")
        except (OSError, socket.timeout) as e:
            logger.warning("SlimProto connection failed: %s", e)
        except Exception as e:
            logger.error("SlimProto error: %s", e)
        self._connected = False
        self._running = False
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        self.disconnected.emit()

    def _send_helo(self):
        if not self._sock:
            return
        helo_payload = _build_helo(self._mac)
        msg = OPCODE_HELO + struct.pack("!I", len(helo_payload)) + helo_payload
        try:
            self._sock.sendall(msg)
        except Exception as e:
            logger.warning("SlimProto HELO send failed: %s", e)
            raise

    def _receive_loop(self):
        while self._running and not self._stop_event.is_set():
            try:
                raw_len = self._recv_exact(2)
                if not raw_len or len(raw_len) < 2:
                    logger.debug("SlimProto recv header returned %d bytes", len(raw_len) if raw_len else 0)
                    break
                body_len = struct.unpack("!H", raw_len)[0]
                if body_len < 4:
                    logger.warning("SlimProto body length too small: %d", body_len)
                    break
                body = self._recv_exact(body_len)
                if not body or len(body) < body_len:
                    logger.debug("SlimProto recv body got %d/%d bytes", len(body) if body else 0, body_len)
                    break
                opcode = body[:4]
                data = body[4:]
                self._handle_msg(opcode, data)
            except socket.timeout:
                self._send_heartbeat()
                continue
            except (OSError, ConnectionError) as e:
                logger.warning("SlimProto receive error: %s (type=%s)", e, type(e).__name__)
                break
            except Exception as e:
                logger.error("SlimProto unexpected receive error: %s (type=%s)", e, type(e).__name__)
                break

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            if not self._sock:
                return buf
            try:
                chunk = self._sock.recv(n - len(buf))
            except socket.timeout:
                raise
            except Exception as e:
                logger.warning("SlimProto recv_exact error (read %d/%d): %s", len(buf), n, e)
                break
            if not chunk:
                logger.debug("SlimProto recv_exact: connection closed by peer (read %d/%d)", len(buf), n)
                break
            buf += chunk
        return buf

    def _handle_msg(self, opcode: bytes, data: bytes):
        if opcode == OPCODE_STRM:
            info = _parse_strm(data)
            if info:
                self._handle_strm(info)
        elif opcode == OPCODE_AUDG:
            vol = _parse_audg(data)
            if vol >= 0:
                self._current_volume = vol
                self.volume_changed.emit(vol)
        elif opcode == OPCODE_BYE:
            logger.info("SlimProto server sent BYE!")
            self._connected = False
            self.disconnected.emit()
        elif opcode == OPCODE_SETD:
            pass
        else:
            pass

    _FMT_TO_CODEC = {
        "p": "pcm", "f": "flac", "m": "mp3", "o": "vorbis", "a": "aac",
    }

    def _handle_strm(self, info: dict):
        cmd = info["command"]
        rg = info.get("replay_gain", 0)
        self._last_replay_gain = rg
        logger.info("STRM cmd=%s url=%s", cmd, info.get("url", "")[:80])
        if cmd == "s":
            url = info.get("url", "")
            if url and not url.startswith("http"):
                ip = info["server_ip"]
                port = info["server_port"]
                if ip == "0.0.0.0":
                    ip = self._host
                url = f"http://{ip}:{port}{url}"
            if not url:
                ip = info["server_ip"] if info["server_ip"] != "0.0.0.0" else self._host
                url = f"http://{ip}:{info['server_port']}/"
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(url).query)
            codec = qs.get("codec", [""])[0]
            name = qs.get("name", [""])[0]
            if not codec:
                codec = self._FMT_TO_CODEC.get(info.get("format", ""), "")
            self._current_url = url
            self._mode = "play"
            self._stream_start_time = time.time()
            logger.info("STRM start: url=%s codec=%s name=%s", url, codec, name)
            self.stream_ready.emit(url, codec, name)
            self._send_stat(b"STMc", rg)
            self._send_stat(b"STMt", rg)
        elif cmd == "t":
            self._send_stat(b"STMt", rg)
        elif cmd == "q" or cmd == "f":
            self._mode = "stop"
            self._send_stat(b"STMt", rg)
            self.stop_requested.emit()
        elif cmd == "p":
            self._mode = "pause"
            self._send_stat(b"STMp", rg)
            self.pause_requested.emit()
        elif cmd == "u":
            self._mode = "play"
            self._send_stat(b"STMr", rg)
        else:
            logger.debug("SlimProto unhandled STRM command: %s", cmd)

    def _send_stat(self, event: bytes = b"STMt", server_timestamp: int = 0):
        if not self._sock or not self._connected:
            return
        now = time.time()
        now_ms = int(now * 1000) & 0xFFFFFFFF
        elapsed = int(now - self._start_time) if self._start_time else 0
        payload = _build_stat(event[:4], now_ms, elapsed, server_timestamp)
        msg = OPCODE_STAT + struct.pack("!I", len(payload)) + payload
        logger.info("SlimProto sending STAT event=%s hex=%s", event[:4], msg[:8].hex())
        with self._send_lock:
            try:
                self._sock.sendall(msg)
            except Exception as e:
                logger.warning("SlimProto sendall failed: %s", e)

    def set_mode(self, mode: str):
        self._mode = mode

    def send_volume(self, volume: int):
        self._current_volume = volume
        payload = _build_volu(volume)
        msg = OPCODE_VOLU + struct.pack("!I", len(payload)) + payload
        with self._send_lock:
            try:
                if self._sock and self._connected:
                    self._sock.sendall(msg)
            except Exception:
                pass

    def _send_heartbeat(self):
        self._send_stat(b"STMt")
