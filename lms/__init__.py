import logging
import os
import uuid
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from .cli import TelnetClient
from .jsonapi import JsonClient
from .slimproto import SlimProtoClient
from .discovery import discover, probe_http
from .models import LmsServer, LmsPlayer

logger = logging.getLogger(__name__)


class LmsService(QObject):
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    player_stream = pyqtSignal(str, str, str)  # url, codec, name
    volume_changed = pyqtSignal(int)
    pause_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, config_dir: str, parent=None):
        super().__init__(parent)
        self._config_dir = config_dir
        self._cli: Optional[TelnetClient] = None
        self._json: Optional[JsonClient] = None
        self._slim: Optional[SlimProtoClient] = None
        self._server: Optional[LmsServer] = None
        self._players: list[LmsPlayer] = []
        self._player_mac = self._load_mac()
        self._retry_timer = QTimer(self)
        self._retry_timer.timeout.connect(self._auto_reconnect)
        self._retry_timer.setInterval(60000)
        self._auto_connect = True

    def _mac_path(self) -> str:
        return os.path.join(self._config_dir, "lms_mac.txt")

    def _load_mac(self) -> bytes:
        path = self._mac_path()
        try:
            with open(path, "rb") as f:
                data = f.read(6)
                if len(data) == 6:
                    return data
        except FileNotFoundError:
            pass
        mac = uuid.uuid4().bytes[:6]
        mac = bytes([mac[0] & 0xFE | 0x02, mac[1], mac[2], mac[3], mac[4], mac[5]])
        os.makedirs(self._config_dir, exist_ok=True)
        with open(path, "wb") as f:
            f.write(mac)
        return mac

    def configure(self, host: str, port: int = 9000, player_name: str = "TrayRadio", auto_connect: bool = True):
        self._server = LmsServer(host=host, port=port, name=player_name)
        self._auto_connect = auto_connect

    def start(self):
        if self._server and self._auto_connect:
            self._connect()

    def stop(self):
        self._retry_timer.stop()
        self._disconnect_slim()
        self._disconnect_cli()

    def _connect(self):
        if not self._server:
            return
        host = self._server.host
        port = self._server.port
        cli_port = 9090 if port == 9000 else port + 90
        self._connect_cli(host, cli_port)
        self._connect_json(host, port)
        self._connect_slim(host)

    def _connect_cli(self, host: str, port: int):
        self._cli = TelnetClient(host, port)
        if self._cli.connect():
            logger.info("CLI connected to %s:%d", host, port)
            self._refresh_players()
        else:
            logger.warning("CLI connect failed to %s:%d", host, port)

    def _connect_json(self, host: str, port: int):
        self._json = JsonClient(host, port)
        if self._json.test_connection():
            logger.info("JSON API connected to %s:%d", host, port)
        else:
            logger.warning("JSON API connect failed to %s:%d", host, port)

    def _connect_slim(self, host: str):
        if self._slim:
            self._slim.disconnect_from_server()
        self._slim = SlimProtoClient(host, mac=self._player_mac)
        self._slim.stream_ready.connect(self._on_slim_stream)
        self._slim.volume_changed.connect(self._on_slim_volume)
        self._slim.pause_requested.connect(self._on_slim_pause)
        self._slim.stop_requested.connect(self._on_slim_stop)
        self._slim.disconnected.connect(self._on_slim_disconnect)
        self._slim.connect_to_server()
        self.connected.emit()

    def _disconnect_slim(self):
        if self._slim:
            self._slim.disconnect_from_server()
            self._slim = None

    def _disconnect_cli(self):
        if self._cli:
            self._cli.disconnect()
            self._cli = None

    def _refresh_players(self):
        if not self._cli or not self._cli.is_connected:
            return
        self._players = self._cli.get_players()
        logger.info("Found %d LMS players", len(self._players))

    def _on_slim_stream(self, url: str, codec: str, name: str):
        self.player_stream.emit(url, codec, name)

    def _on_slim_volume(self, volume: int):
        self.volume_changed.emit(volume)

    def _on_slim_pause(self):
        self.pause_requested.emit()

    def _on_slim_stop(self):
        self.stop_requested.emit()

    def _on_slim_disconnect(self):
        self.disconnected.emit()
        if self._auto_connect:
            self._retry_timer.start()

    def _auto_reconnect(self):
        if not self._server:
            return
        logger.info("Attempting LMS reconnect to %s:%d", self._server.host, self._server.port)
        self.stop()
        self._connect()

    def rescan_network(self) -> list[dict]:
        servers = discover(timeout=2.0)
        return [
            {"host": s.host, "port": s.port, "name": s.name, "alive": s.is_alive}
            for s in servers
        ]

    def test_server(self, host: str, port: int = 9000) -> Optional[str]:
        server = probe_http(host, port, timeout=3.0)
        if server:
            server.is_alive = True
            return server.name
        return None

    def get_players(self) -> list[LmsPlayer]:
        if self._cli and self._cli.is_connected:
            self._refresh_players()
        return self._players

    def reconnect(self):
        if self._server:
            self._connect_slim(self._server.host)

    def set_server(self, host: str, port: int):
        self.stop()
        self._server = LmsServer(host=host, port=port, name="", is_alive=False)
        self._connect()

    @property
    def slim_proto(self):
        return self._slim

    def set_volume(self, volume: int):
        if self._slim:
            self._slim.send_volume(volume)

    @property
    def is_connected(self) -> bool:
        return bool(self._slim and self._slim.is_connected)

    @property
    def server(self) -> Optional[LmsServer]:
        return self._server

    @property
    def cli(self) -> Optional[TelnetClient]:
        return self._cli

    @property
    def json_api(self) -> Optional[JsonClient]:
        return self._json

    @property
    def player_mac(self) -> bytes:
        return self._player_mac
