import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Any

from .models import LmsPlayer

logger = logging.getLogger(__name__)


def _direct_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


class JsonClient:
    def __init__(self, host: str, port: int = 9000, timeout: float = 5.0):
        self._base = f"http://{host}:{port}/jsonrpc.js"
        self._timeout = timeout
        self._req_id = 0

    def _request(self, method: str, params: list) -> Optional[dict[str, Any]]:
        self._req_id += 1
        payload = json.dumps({
            "id": self._req_id,
            "method": "slim.request",
            "params": params,
        }).encode("utf-8")
        req = urllib.request.Request(
            self._base, data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            # Bypass any globally installed proxy — LMS is always on LAN
            resp = _direct_opener().open(req, timeout=self._timeout)
            data = json.loads(resp.read().decode("utf-8"))
            return data
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
            logger.warning("JSON API request failed: %s", e)
            return None

    def server_status(self) -> Optional[dict]:
        return self._request("slim.request", ["", ["serverstatus", 0, 99]])

    def get_players(self) -> list[LmsPlayer]:
        data = self._request("slim.request", ["", ["playerstatus", 0, 99]])
        if not data:
            return []
        result = data.get("result", {})
        players_loop = result.get("players_loop", [])
        players = []
        for p in players_loop:
            players.append(LmsPlayer(
                playerid=p.get("playerid", ""),
                name=p.get("name", ""),
                ip=p.get("ip", ""),
                model=p.get("model", ""),
                displaytype=p.get("displaytype", ""),
                is_master=not p.get("sync_master", ""),
                sync_master=p.get("sync_master", ""),
                volume=p.get("mixer volume", 100),
                connected=True,
            ))
        return players

    def player_status(self, player_id: str) -> Optional[dict]:
        data = self._request("slim.request", [player_id, ["status", 0, 99]])
        if data:
            return data.get("result")
        return None

    def sync_players(self, player_ids: list[str], master_id: str) -> bool:
        for pid in player_ids:
            if pid == master_id:
                continue
            data = self._request("slim.request", [pid, ["sync", master_id]])
            if not data:
                return False
        return True

    def unsync_players(self, player_ids: list[str]) -> bool:
        for pid in player_ids:
            data = self._request("slim.request", [pid, ["sync", "-"]])
            if not data:
                return False
        return True

    def test_connection(self) -> bool:
        data = self.server_status()
        return data is not None
