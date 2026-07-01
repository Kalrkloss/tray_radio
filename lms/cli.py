import logging
import socket
import threading
import time
from typing import Optional

from .models import LmsPlayer, LmsPlaylist, LmsTrack

logger = logging.getLogger(__name__)


class TelnetClient:
    def __init__(self, host: str, port: int = 9090, timeout: float = 5.0):
        self._host = host
        self._port = port
        self._timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._connected = False

    def connect(self) -> bool:
        try:
            self.disconnect()
            self._sock = socket.create_connection(
                (self._host, self._port), timeout=self._timeout
            )
            self._sock.settimeout(self._timeout)
            banner = self._recv_line()
            if banner is not None:
                self._connected = True
                logger.info("CLI connected to %s:%d — %s", self._host, self._port, banner.strip())
                return True
        except Exception as e:
            logger.warning("CLI connect to %s:%d failed: %s", self._host, self._port, e)
        self._connected = False
        return False

    def disconnect(self):
        with self._lock:
            self._connected = False
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _recv_line(self, sock: Optional[socket.socket] = None) -> Optional[str]:
        s = sock or self._sock
        if not s:
            return None
        buf = b""
        try:
            while True:
                c = s.recv(1)
                if not c:
                    break
                if c == b"\n":
                    break
                buf += c
        except socket.timeout:
            pass
        except Exception:
            return None
        return buf.decode("utf-8", errors="replace") if buf else ""

    def _recv_response(self, expected_lines: int = 0) -> list[str]:
        lines = []
        while True:
            line = self._recv_line()
            if line is None:
                break
            if line == "":
                break
            lines.append(line)
            if expected_lines and len(lines) >= expected_lines:
                break
        return lines

    def _send_cmd(self, cmd: str) -> Optional[list[str]]:
        with self._lock:
            if not self._connected or not self._sock:
                return None
            try:
                self._sock.sendall((cmd + "\n").encode("utf-8"))
                time.sleep(0.05)
                return self._recv_response()
            except Exception as e:
                logger.warning("CLI send failed: %s", e)
                self._connected = False
                return None

    @staticmethod
    def _player_from_dict(d: dict) -> LmsPlayer:
        ip_raw = d.get("ip", "")
        return LmsPlayer(
            playerid=d.get("playerid", ""),
            name=d.get("name", ""),
            ip=ip_raw.split(":")[0] if ip_raw else "",
            model=d.get("model", ""),
        )

    def get_players(self) -> list[LmsPlayer]:
        resp = self._send_cmd("players 0 99")
        if not resp:
            return []
        from urllib.parse import unquote as uq
        players = []
        for line in resp:
            # Format: key%3Avalue key%3Avalue ...
            # First token is echo "players 0 99"
            tokens = line.strip().split()
            current = {}
            for tok in tokens[1:]:
                if "%3A" not in tok:
                    continue
                key, _, raw_value = tok.partition("%3A")
                value = uq(raw_value)
                if key == "playerindex":
                    if current and "playerid" in current:
                        players.append(self._player_from_dict(current))
                    current = {}
                current[key] = value
            if current and "playerid" in current:
                players.append(self._player_from_dict(current))
        return players

    def get_playlists(self) -> list[LmsPlaylist]:
        resp = self._send_cmd("playlists 0 99")
        if not resp:
            return []
        playlists = []
        for line in resp:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                playlists.append(LmsPlaylist(id=parts[0], name=parts[1]))
            elif line.strip():
                playlists.append(LmsPlaylist(id="", name=line.strip()))
        return playlists

    def get_playlist_tracks(self, playlist_id: str) -> list[LmsTrack]:
        resp = self._send_cmd(f"playlists tracks {playlist_id} 0 99")
        if not resp:
            return []
        tracks = []
        for line in resp:
            parts = line.strip().split("\t")
            if parts:
                track_id = parts[0] if parts[0].isdigit() else 0
                title = parts[1] if len(parts) > 1 else ""
                artist = parts[2] if len(parts) > 2 else ""
                album = parts[3] if len(parts) > 3 else ""
                duration = float(parts[4]) if len(parts) > 4 and parts[4] else 0.0
                tracks.append(LmsTrack(
                    id=int(track_id) if isinstance(track_id, str) and track_id.isdigit() else 0,
                    title=title, artist=artist, album=album, duration=duration,
                ))
        return tracks

    def player_play(self, player_id: str):
        eid = player_id.replace(":", "%3A")
        self._send_cmd(f"{eid} play")

    def player_stop(self, player_id: str):
        eid = player_id.replace(":", "%3A")
        self._send_cmd(f"{eid} stop")

    def player_pause(self, player_id: str):
        eid = player_id.replace(":", "%3A")
        self._send_cmd(f"{eid} pause")

    def player_volume(self, player_id: str, level: int):
        eid = player_id.replace(":", "%3A")
        self._send_cmd(f"{eid} volume {max(0, min(100, level))}")

    def player_sync(self, player_id: str, master_id: str):
        eid = player_id.replace(":", "%3A")
        meid = master_id.replace(":", "%3A")
        self._send_cmd(f"{eid} sync {meid}")

    def player_unsync(self, player_id: str):
        eid = player_id.replace(":", "%3A")
        self._send_cmd(f"{eid} sync -")

    def playlist_add_url(self, player_id: str, url: str, name: str = ""):
        eid = player_id.replace(":", "%3A")
        escaped = url.replace(":", "%3A")
        cmd = f"{eid} playlist add {escaped}"
        if name:
            escaped_name = name.replace(":", "%3A")
            cmd += f" {escaped_name}"
        self._send_cmd(cmd)

    def status(self, player_id: str) -> dict:
        eid = player_id.replace(":", "%3A")
        resp = self._send_cmd(f"{eid} status 0 99")
        result = {}
        if resp:
            for line in resp:
                if ":" in line:
                    key, _, val = line.partition(":")
                    result[key.strip()] = val.strip()
        return result

    def player_name(self, player_id: str, name: str) -> bool:
        eid = player_id.replace(":", "%3A")
        resp = self._send_cmd(f"{eid} name {name}")
        return resp is not None
