import logging
import socket
import struct
import threading
import time
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal, QTimer

logger = logging.getLogger(__name__)


# SlimProto opcodes
OPCODES = {
    "HELO": b"h",
    "BYE!": b"b",
    "STRM": b"s",
    "STAT": b"t",
    "VOLU": b"v",
    "PAUS": b"p",
    "STOP": b"x",
    "DSCO": b"d",
    "AUDI": b"a",
}


def _make_header(opcode: bytes, length: int) -> bytes:
    return opcode + struct.pack("!I", length)


def _build_helo(mac: bytes, uuid: bytes) -> bytes:
    device_id = 12  # squeezeplay
    revision = 0
    # HELO: mac(6) + device_id(1) + revision(1) + uuid(16) + reserved(12) = 36
    payload = struct.pack(
        "!6s B B 16s 12s",
        mac[:6],
        device_id,
        revision,
        uuid[:16],
        b"\x00" * 12,
    )
    # Capabilities string after the 36-byte header
    caps = b"aac,flc,oog,pcm,syn2"
    return _make_header(OPCODES["HELO"], len(payload) + len(caps)) + payload + caps


def _parse_strm(data: bytes) -> Optional[dict]:
    # STRM payload: autostart(1) + transition(1) + reserved(2) +
    #               num_timestamps(1) + reserved_ts(3) + server_port(2) +
    #               server_ip(4) + udp_port(2) + udp_delay(2) +
    #               reserved_tcp(4) + threshold(4) + url(null-term)
    if len(data) < 26:
        return None
    offset = 0
    autostart = data[offset]
    offset += 1
    transition = data[offset]
    offset += 1
    offset += 2  # reserved
    num_ts = data[offset]
    offset += 1
    offset += 3  # reserved_ts
    server_port = struct.unpack("!H", data[offset:offset+2])[0]
    offset += 2
    server_ip = socket.inet_ntoa(data[offset:offset+4])
    offset += 4
    udp_port = struct.unpack("!H", data[offset:offset+2])[0]
    offset += 2
    offset += 2  # udp_delay
    offset += 4  # reserved_tcp
    threshold = struct.unpack("!I", data[offset:offset+4])[0]
    offset += 4
    url = data[offset:].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    return {
        "autostart": autostart,
        "transition": transition,
        "server_port": server_port,
        "server_ip": server_ip,
        "udp_port": udp_port,
        "threshold": threshold,
        "url": url,
    }


class SlimProtoClient(QObject):
    stream_ready = pyqtSignal(str, str, str)  # url, codec, name
    volume_changed = pyqtSignal(int)
    pause_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, host: str, port: int = 3483, mac: bytes = None, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._mac = mac or b"\x00\x00\x00\x00\x00\x01"
        self._uuid = self._mac + b"\x00" * 10
        self._sock: Optional[socket.socket] = None
        self._running = False
        self._connected = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.timeout.connect(self._try_reconnect)
        self._reconnect_timer.setInterval(30000)
        self._current_volume = 100
        self._current_url = ""
        self._mode = "stop"

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect_to_server(self):
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def disconnect_from_server(self):
        self._running = False
        self._stop_event.set()
        self._reconnect_timer.stop()
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        self._connected = False

    def _try_reconnect(self):
        if self._connected or not self._running:
            return
        logger.info("SlimProto attempting reconnect to %s:%d", self._host, self._port)
        self.connect_to_server()

    def _run(self):
        while self._running and not self._stop_event.is_set():
            try:
                self._sock = socket.create_connection(
                    (self._host, self._port), timeout=10.0
                )
                self._sock.settimeout(10.0)
                self._send_helo()
                self._connected = True
                self._reconnect_timer.stop()
                logger.info("SlimProto connected to %s:%d", self._host, self._port)
                self._receive_loop()
            except (OSError, socket.timeout) as e:
                logger.warning("SlimProto connection failed: %s", e)
                self._connected = False
                with self._lock:
                    if self._sock:
                        try:
                            self._sock.close()
                        except Exception:
                            pass
                        self._sock = None
                if self._running and not self._stop_event.is_set():
                    self._reconnect_timer.start()
                    break
            except Exception as e:
                logger.error("SlimProto error: %s", e)
                self._connected = False
                break
        self._connected = False

    def _send_helo(self):
        if not self._sock:
            return
        helo = _build_helo(self._mac, self._uuid)
        try:
            self._sock.sendall(helo)
        except Exception as e:
            logger.warning("SlimProto HELO send failed: %s", e)
            raise

    def _receive_loop(self):
        while self._running and not self._stop_event.is_set():
            try:
                header = self._recv_exact(5)
                if not header or len(header) < 5:
                    break
                opcode = header[0:1]
                length = struct.unpack("!I", header[1:5])[0]
                data = self._recv_exact(length) if length > 0 else b""
                self._handle_opcode(opcode, data)
            except socket.timeout:
                self._send_stat()
                continue
            except (OSError, ConnectionError) as e:
                logger.warning("SlimProto receive error: %s", e)
                break

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            if not self._sock:
                return buf
            try:
                chunk = self._sock.recv(n - len(buf))
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
        return buf

    def _handle_opcode(self, opcode: bytes, data: bytes):
        if opcode == OPCODES.get("STRM"):
            info = _parse_strm(data)
            if info and info["url"]:
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(info["url"]).query)
                codec = qs.get("codec", [""])[0]
                name = qs.get("name", [""])[0]
                self._current_url = info["url"]
                self._mode = "play"
                self.stream_ready.emit(info["url"], codec, name)
        elif opcode == OPCODES.get("VOLU"):
            if len(data) >= 2:
                vol = struct.unpack("!H", data[:2])[0]
                self._current_volume = vol
                self.volume_changed.emit(vol)
        elif opcode == OPCODES.get("PAUS"):
            self._mode = "pause"
            self.pause_requested.emit()
        elif opcode == OPCODES.get("STOP"):
            self._mode = "stop"
            self.stop_requested.emit()
        elif opcode == OPCODES.get("BYE!") or opcode == b"b":
            logger.info("SlimProto server sent BYE!")
            self._connected = False
            self.disconnected.emit()

    def _send_stat(self):
        if not self._sock or not self._connected:
            return
        # STAT: mode(4) + mask(4) + threshold(4) + timestamp(4) +
        #       dest_ip(4) + dest_port(2) + reserved(2) + buf_size(2) +
        #       lost(2) + delay(4) + jitter(4) + bytes_received(4) +
        #       signal_strength(1) + jiffies(1) + output_buf_size(2) +
        #       reserved2(12) + elap(4) + elapsed_sec(4) + elapsed_mm(4) +
        #       timestamp_ms(4) + reserved3(36)
        mode = self._mode.encode("utf-8", errors="replace").ljust(4, b"\x00")[:4]
        vol_bytes = struct.pack("!H", self._current_volume)
        # Build a minimal STAT (much simpler than full spec)
        payload = mode
        payload += struct.pack("!I", 0)  # mask
        payload += struct.pack("!I", 0)  # threshold
        payload += struct.pack("!I", int(time.time()))  # timestamp
        payload += b"\x00" * 64  # minimal padding to reach typical size
        stat = _make_header(OPCODES["STAT"], len(payload)) + payload
        try:
            self._sock.sendall(stat)
        except Exception:
            pass

    def set_mode(self, mode: str):
        self._mode = mode

    def send_volume(self, volume: int):
        self._current_volume = volume
        volu = _make_header(OPCODES["VOLU"], 2) + struct.pack("!H", volume)
        try:
            if self._sock and self._connected:
                self._sock.sendall(volu)
        except Exception:
            pass
