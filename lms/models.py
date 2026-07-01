from dataclasses import dataclass
from typing import Optional


@dataclass
class LmsServer:
    host: str
    port: int = 9000
    name: str = ""
    version: str = ""
    is_alive: bool = False


@dataclass
class LmsPlayer:
    playerid: str
    name: str
    ip: str
    model: str
    displaytype: str = ""
    is_master: bool = True
    sync_master: str = ""
    sync_slaves: list = None
    volume: int = 100
    connected: bool = False

    def __post_init__(self):
        if self.sync_slaves is None:
            self.sync_slaves = []

    @property
    def url_encoded_id(self) -> str:
        return self.playerid.replace(":", "%3A")


@dataclass
class LmsPlaylist:
    id: str
    name: str
    track_count: int = 0


@dataclass
class LmsTrack:
    id: int
    title: str
    artist: str = ""
    album: str = ""
    duration: float = 0.0
    url: str = ""
