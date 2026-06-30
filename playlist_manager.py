import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Stream:
    uuid: str
    name: str
    url: str
    url_resolved: str = ""
    homepage: str = ""
    favicon: str = ""
    tags: str = ""
    country: str = ""
    language: str = ""
    description: str = ""
    codec: str = ""
    bitrate: int = 0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: data.get(k, "") for k in cls.__dataclass_fields__})


@dataclass
class Playlist:
    name: str
    streams: list = field(default_factory=list)

    def to_dict(self):
        return {"name": self.name, "streams": [s.to_dict() for s in self.streams]}

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data["name"],
            streams=[Stream.from_dict(s) for s in data.get("streams", [])],
        )


class PlaylistManager:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.filepath = os.path.join(config_dir, "playlists.json")
        self.playlists: list[Playlist] = []
        self.current_playlist_index: int = -1
        self.current_stream_uuid: Optional[str] = None
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.playlists = [
                    Playlist.from_dict(p) for p in data.get("playlists", [])
                ]
                self.current_playlist_index = data.get("current_playlist_index", -1)
                self.current_stream_uuid = data.get("current_stream_uuid")
            except Exception:
                self._init_default()
        else:
            self._init_default()

    def _init_default(self):
        self.playlists = [Playlist(name="Favorites")]
        self.current_playlist_index = 0
        self.current_stream_uuid = None
        self.save()

    def save(self):
        os.makedirs(self.config_dir, exist_ok=True)
        data = {
            "playlists": [p.to_dict() for p in self.playlists],
            "current_playlist_index": self.current_playlist_index,
            "current_stream_uuid": self.current_stream_uuid,
        }
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def create_playlist(self, name: str):
        self.playlists.append(Playlist(name=name))
        self.save()

    def rename_playlist(self, index: int, new_name: str):
        if 0 <= index < len(self.playlists):
            self.playlists[index].name = new_name
            self.save()

    def delete_playlist(self, index: int):
        if 0 <= index < len(self.playlists):
            del self.playlists[index]
            if self.current_playlist_index >= len(self.playlists):
                self.current_playlist_index = max(0, len(self.playlists) - 1) if self.playlists else -1
            self.save()

    def add_stream(self, playlist_index: int, stream: Stream):
        if 0 <= playlist_index < len(self.playlists):
            self.playlists[playlist_index].streams.append(stream)
            self.save()

    def remove_stream(self, playlist_index: int, stream_index: int):
        if 0 <= playlist_index < len(self.playlists):
            pl = self.playlists[playlist_index]
            if 0 <= stream_index < len(pl.streams):
                removed = pl.streams.pop(stream_index)
                if self.current_stream_uuid == removed.uuid:
                    self.current_stream_uuid = None
                self.save()

    def move_stream(self, from_playlist: int, stream_index: int, to_playlist: int):
        if from_playlist == to_playlist:
            return
        if 0 <= from_playlist < len(self.playlists) and 0 <= to_playlist < len(self.playlists):
            src = self.playlists[from_playlist]
            if 0 <= stream_index < len(src.streams):
                stream = src.streams.pop(stream_index)
                self.playlists[to_playlist].streams.append(stream)
                self.save()

    def get_current_stream(self) -> Optional[Stream]:
        if self.current_playlist_index < 0 or self.current_playlist_index >= len(self.playlists):
            return None
        pl = self.playlists[self.current_playlist_index]
        for s in pl.streams:
            if s.uuid == self.current_stream_uuid:
                return s
        return None

    def set_current_stream(self, uuid: str):
        self.current_stream_uuid = uuid
        self.save()

    def get_stream_by_uuid(self, uuid: str) -> Optional[Stream]:
        for pl in self.playlists:
            for s in pl.streams:
                if s.uuid == uuid:
                    return s
        return None

    def find_playlist_for_stream(self, uuid: str) -> Optional[int]:
        for i, pl in enumerate(self.playlists):
            for s in pl.streams:
                if s.uuid == uuid:
                    return i
        return None
