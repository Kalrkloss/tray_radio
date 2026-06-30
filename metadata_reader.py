import re
import time
import logging
import threading
from typing import Optional, Callable
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


STREAM_TITLE_RE = re.compile(rb"StreamTitle='([^']*)';")


class MetadataReader:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._on_song_change: Optional[Callable[[str], None]] = None
        self._on_station_info: Optional[Callable[[dict], None]] = None
        self._current_song: str = ""
        self._proxies: Optional[dict] = None

    def set_song_change_callback(self, cb: Callable[[str], None]):
        self._on_song_change = cb

    def set_station_info_callback(self, cb: Callable[[dict], None]):
        self._on_station_info = cb

    def set_proxy(self, proxy_url: Optional[str]):
        self._proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    def start(self, url: str):
        self.stop()
        self._stop_event.clear()
        self._current_song = ""
        resolved_url = self._resolve_url(url)
        if resolved_url:
            self._thread = threading.Thread(
                target=self._read_metadata_loop,
                args=(resolved_url,),
                daemon=True,
            )
            self._thread.start()
        else:
            resolved_url = url
            self._thread = threading.Thread(
                target=self._read_metadata_loop,
                args=(resolved_url,),
                daemon=True,
            )
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
            self._thread = None

    def _resolve_url(self, url: str) -> Optional[str]:
        try:
            resp = requests.get(
                url,
                stream=True,
                timeout=5,
                allow_redirects=True,
                headers={
                    "User-Agent": "TrayRadio/1.0",
                    "Icy-MetaData": "1",
                },
                proxies=self._proxies,
            )
            return resp.url
        except Exception:
            return None

    def _read_metadata_loop(self, url: str):
        session = requests.Session()
        session.proxies.update(self._proxies or {})
        while not self._stop_event.is_set():
            try:
                resp = session.get(
                    url,
                    stream=True,
                    timeout=10,
                    headers={
                        "User-Agent": "TrayRadio/1.0",
                        "Icy-MetaData": "1",
                    },
                )
                if not resp.ok:
                    logger.warning(f"Metadata request failed: {resp.status_code}")
                    time.sleep(5)
                    continue

                station_info = {}
                for key in ("icy-name", "icy-genre", "icy-description", "icy-url",
                            "icy-br", "content-type"):
                    val = resp.headers.get(key)
                    if val:
                        station_info[key] = val

                if station_info and self._on_station_info:
                    self._on_station_info(station_info)

                metaint_str = resp.headers.get("icy-metaint")
                if not metaint_str:
                    logger.debug("No icy-metaint, stream does not support metadata")
                    break

                metaint = int(metaint_str)
                stream = resp.raw

                while not self._stop_event.is_set():
                    try:
                        audio_data = stream.read(metaint)
                        if not audio_data:
                            break
                        meta_byte = stream.read(1)
                        if not meta_byte:
                            break

                        meta_length = ord(meta_byte) * 16
                        if meta_length > 0:
                            meta_data = stream.read(meta_length)
                            title_match = STREAM_TITLE_RE.search(meta_data)
                            if title_match:
                                song = title_match.group(1).decode("utf-8", errors="replace")
                                if song and song != self._current_song:
                                    self._current_song = song
                                    if self._on_song_change:
                                        self._on_song_change(song)
                    except Exception as e:
                        logger.debug(f"Metadata read error: {e}")
                        break
            except requests.RequestException as e:
                logger.warning(f"Metadata connection error: {e}")
                self._stop_event.wait(5)
                continue
            except Exception as e:
                logger.error(f"Metadata loop error: {e}")
                self._stop_event.wait(5)
                continue

        session.close()
