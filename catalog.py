import abc
import json
import os
import sys
import random
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_MEIPASS = getattr(sys, '_MEIPASS', None)


class CatalogBase(abc.ABC):
    @property
    @abc.abstractmethod
    def id(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...

    @abc.abstractmethod
    def search(self, name: str = "", tag: str = "", country: str = "",
               limit: int = 50) -> list[dict]:
        ...

    @abc.abstractmethod
    def station_to_stream(self, data: dict) -> dict:
        ...

    def click_station(self, uuid: str):
        pass


_RADIOBROWSER_CANDIDATES = [
    "https://de1.api.radio-browser.info",
    "https://de2.api.radio-browser.info",
    "https://fr1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
]


def _discover_server(session: requests.Session) -> Optional[str]:
    try:
        resp = session.get(
            "https://api.radio-browser.info/json/servers",
            timeout=5,
        )
        if resp.ok:
            servers = resp.json()
            if servers:
                random.shuffle(servers)
                return f"https://{servers[0]}"
    except Exception:
        pass
    for fb in _RADIOBROWSER_CANDIDATES:
        try:
            resp = session.get(f"{fb}/json/servers", timeout=5)
            if resp.ok:
                return fb
        except Exception:
            continue
    return None


class RadioBrowserCatalog(CatalogBase):
    def __init__(self, session: requests.Session, base_url: str = None):
        self.session = session
        self.base_url = base_url

    @property
    def id(self) -> str:
        return "radio-browser"

    @property
    def name(self) -> str:
        return "radio-browser.info"

    def discover(self) -> bool:
        server = _discover_server(self.session)
        if server:
            self.base_url = server.rstrip("/")
            return True
        return False

    def _get(self, path: str, params: dict = None, timeout: int = 10):
        if not self.base_url:
            raise RuntimeError("No radio-browser server discovered")
        url = f"{self.base_url}{path}"
        return self.session.get(url, params=params, timeout=timeout)

    def search(self, name: str = "", tag: str = "", country: str = "",
               limit: int = 50) -> list[dict]:
        params = {"limit": limit}
        if name:
            params["name"] = name
        if tag:
            params["tag"] = tag
        if country:
            params["country"] = country
        resp = self._get("/json/stations/search", params=params)
        if resp.ok:
            return resp.json()
        return []

    def click_station(self, uuid: str):
        try:
            self._get(f"/json/url/{uuid}", timeout=3)
        except Exception:
            pass

    def station_to_stream(self, data: dict) -> dict:
        return {
            "uuid": data.get("stationuuid", ""),
            "name": data.get("name", ""),
            "url": data.get("url", ""),
            "url_resolved": data.get("url_resolved", ""),
            "homepage": data.get("homepage", ""),
            "favicon": data.get("favicon", ""),
            "tags": data.get("tags", ""),
            "country": data.get("country", ""),
            "language": data.get("language", ""),
            "description": "",
            "codec": data.get("codec", ""),
            "bitrate": data.get("bitrate", 0),
        }


def _find_stations_path() -> str:
    candidates = [
        os.path.join(os.path.dirname(__file__), "stations.json"),
        os.path.join(os.getcwd(), "stations.json"),
    ]
    if _MEIPASS:
        candidates.insert(0, os.path.join(_MEIPASS, "stations.json"))
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""


def _load_stations() -> list[dict]:
    path = _find_stations_path()
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load stations.json: %s", e)
        return []


class LocalCatalog(CatalogBase):
    def __init__(self):
        self._stations = _load_stations()

    @property
    def id(self) -> str:
        return "local"

    @property
    def name(self) -> str:
        return "Curated Stations"

    def search(self, name: str = "", tag: str = "", country: str = "",
               limit: int = 50) -> list[dict]:
        results = list(self._stations)
        if name:
            q = name.lower()
            results = [s for s in results if q in s.get("name", "").lower()]
        if tag:
            q = tag.lower()
            results = [s for s in results if q in s.get("tags", "").lower()]
        if country:
            q = country.lower()
            results = [s for s in results if q in s.get("country", "").lower()]
        return results[:limit]

    def station_to_stream(self, data: dict) -> dict:
        return {
            "uuid": data.get("uuid", ""),
            "name": data.get("name", ""),
            "url": data.get("url", ""),
            "url_resolved": data.get("url_resolved", ""),
            "homepage": data.get("homepage", ""),
            "favicon": data.get("favicon", ""),
            "tags": data.get("tags", ""),
            "country": data.get("country", ""),
            "language": data.get("language", ""),
            "description": data.get("description", ""),
            "codec": data.get("codec", ""),
            "bitrate": data.get("bitrate", 0),
        }


def probe_catalogs(session: requests.Session) -> list[CatalogBase]:
    catalogs: list[CatalogBase] = []

    rb = RadioBrowserCatalog(session)
    if rb.discover():
        catalogs.append(rb)
        logger.info("radio-browser.info reachable at %s", rb.base_url)
    else:
        logger.warning("radio-browser.info unreachable")

    local = LocalCatalog()
    if local._stations:
        catalogs.append(local)
        logger.info("Curated Stations catalog loaded (%d stations)", len(local._stations))

    return catalogs
