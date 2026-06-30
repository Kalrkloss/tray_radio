import random
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


CATALOG_CANDIDATES = [
    "https://de1.api.radio-browser.info",
    "https://de2.api.radio-browser.info",
    "https://fr1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
    "https://www.radio-browser.info",
    "https://dir.xiph.org",
]


def probe_catalogs(session: requests.Session) -> list[dict]:
    results = []
    for url in CATALOG_CANDIDATES:
        try:
            resp = session.get(
                f"{url}/json/servers" if "radio-browser" in url else url,
                timeout=5,
            )
            results.append({
                "url": url,
                "reachable": resp.ok,
                "status": resp.status_code,
                "type": "radio-browser" if "radio-browser" in url else "other",
            })
        except Exception as e:
            results.append({
                "url": url,
                "reachable": False,
                "status": str(e),
                "type": "radio-browser" if "radio-browser" in url else "other",
            })
    return results


def discover_server(session: requests.Session) -> Optional[str]:
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
    fallbacks = [
        "https://de1.api.radio-browser.info",
        "https://de2.api.radio-browser.info",
    ]
    for fb in fallbacks:
        try:
            resp = session.get(f"{fb}/json/servers", timeout=5)
            if resp.ok:
                return fb
        except Exception:
            continue
    return None


class RadioBrowserClient:
    def __init__(self, session: requests.Session):
        self.session = session
        self.session.headers.update({"User-Agent": "TrayRadio/1.0"})
        self.base_url = None

    def discover(self) -> bool:
        server = discover_server(self.session)
        if server:
            self.base_url = server.rstrip("/")
            return True
        return False

    def _get(self, path: str, params: dict = None, timeout: int = 10):
        if not self.base_url:
            raise RuntimeError("No radio-browser server discovered")
        url = f"{self.base_url}{path}"
        return self.session.get(url, params=params, timeout=timeout)

    def search_stations(
        self,
        name: str = "",
        tag: str = "",
        country: str = "",
        language: str = "",
        limit: int = 50,
        offset: int = 0,
    ):
        params = {"limit": limit, "offset": offset}
        if name:
            params["name"] = name
        if tag:
            params["tag"] = tag
        if country:
            params["country"] = country
        if language:
            params["language"] = language
        resp = self._get("/json/stations/search", params=params)
        if resp.ok:
            return resp.json()
        return []

    def get_station_by_uuid(self, uuid: str):
        resp = self._get(f"/json/stations/{uuid}")
        if resp.ok:
            data = resp.json()
            return data[0] if data else None
        return None

    def click_station(self, uuid: str):
        try:
            self._get(f"/json/url/{uuid}", timeout=3)
        except Exception:
            pass

    def get_tags(self, limit: int = 100):
        resp = self._get("/json/tags", params={"limit": limit, "order": "stationcount"})
        if resp.ok:
            return resp.json()
        return []

    def get_countries(self, limit: int = 100):
        resp = self._get(
            "/json/countries", params={"limit": limit, "order": "stationcount"}
        )
        if resp.ok:
            return resp.json()
        return []

    def get_languages(self, limit: int = 100):
        resp = self._get(
            "/json/languages", params={"limit": limit, "order": "stationcount"}
        )
        if resp.ok:
            return resp.json()
        return []

    @staticmethod
    def station_to_stream(data: dict) -> dict:
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
