import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests

logger = logging.getLogger(__name__)


_KNOWN_BAD_CT = {"text/html", "text/plain", "application/xml", "text/xml"}
_SUPPORTED_CODECS = {"mp3", "mpeg", "ogg", "vorbis", "flac", "wav", "aac", "aac+"}


def _is_supported_codec(codec: str) -> bool:
    c = codec.strip().lower()
    if c in _SUPPORTED_CODECS or c.startswith("aac"):
        return True
    return False


def _check_stream(station: dict, session: requests.Session) -> dict:
    result = dict(station, responsive=False)
    codec = station.get("codec", "")
    if codec and not _is_supported_codec(codec):
        return result
    url = station.get("url_resolved") or station.get("url", "")
    if not url:
        return result
    try:
        resp = session.get(
            url,
            stream=True,
            timeout=5,
            headers={
                "User-Agent": "TrayRadio/1.0",
            },
        )
        if resp.status_code in (200, 206):
            ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ct and ct not in _KNOWN_BAD_CT:
                chunk = resp.raw.read(1024)
                if chunk:
                    result["responsive"] = True
                    result["_content_type"] = ct
        resp.close()
    except Exception:
        pass
    return result


def scan_streams(
    stations: list,
    max_workers: int = 5,
    proxies: Optional[dict] = None,
    progress_cb: callable = None,
    responsive_cb: callable = None,
) -> list:
    if not stations:
        return []

    session = requests.Session()
    session.headers.update({"User-Agent": "TrayRadio/1.0"})
    if proxies:
        session.proxies.update(proxies)

    # Pre-filter unsupported codecs to avoid wasted HTTP requests
    stations = [s for s in stations if not s.get("codec") or _is_supported_codec(s.get("codec", ""))]

    total = len(stations)
    checked = 0
    responsive = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_check_stream, s, session): i
            for i, s in enumerate(stations)
        }
        results = [None] * total
        for future in as_completed(futures):
            idx = futures[future]
            try:
                r = future.result()
                results[idx] = r
                checked += 1
                if r.get("responsive"):
                    responsive += 1
                    if responsive_cb:
                        responsive_cb(r)
                if progress_cb:
                    progress_cb(checked, total)
                logger.debug(
                    f"Scan {checked}/{total}: {r.get('name','?')} -> "
                    f"{'OK' if r.get('responsive') else 'FAIL'}"
                )
            except Exception as e:
                results[idx] = dict(stations[idx], responsive=False)
                checked += 1
                if progress_cb:
                    progress_cb(checked, total)
                logger.debug(f"Scan {checked}/{total}: exception -> {e}")

    session.close()
    filtered = [s for s in results if s.get("responsive")]
    logger.info(
        f"Scan done: {responsive}/{total} responsive"
    )
    return filtered
