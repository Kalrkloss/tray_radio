import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable

import requests

from pls_resolver import is_pls_url, resolve_pls_url

logger = logging.getLogger(__name__)


_KNOWN_BAD_CT = {"text/html", "text/plain", "application/xml", "text/xml", "audio/x-scpls"}
_SUPPORTED_CODECS = {"mp3", "mpeg", "ogg", "vorbis", "flac", "wav", "aac", "aac+"}

_KNOWN_AD_DOMAINS = {
    "ad.doubleclick.net",
    "doubleclick.net",
    "ads.pubmatic.com",
    "adsrvr.org",
    "adzerk.net",
    "servedbyadbutler.com",
    "exoclick.com",
    "trafficfactory.com",
    "popads.net",
    "propellerads.com",
    "admost.com",
    "adcolony.com",
    "chartboost.com",
    "vungle.com",
    "tapjoy.com",
    "inmobi.com",
    "startapp.com",
    "applovin.com",
    "unityads.unity3d.com",
    "admarvel.com",
    "smartadserver.com",
    "criteo.com",
    "criteo.net",
    "casalemedia.com",
    "openx.net",
    "rubiconproject.com",
    "pubmatic.com",
    "indexww.com",
    "soopro.com",
    "adnxs.com",
    "adsafeprotected.com",
    "moatads.com",
    "amazon-adsystem.com",
    "adform.net",
}


def _is_supported_codec(codec: str) -> bool:
    c = codec.strip().lower()
    if c in _SUPPORTED_CODECS or c.startswith("aac"):
        return True
    return False


def _check_redirects_for_ads(resp: requests.Response) -> bool:
    for hist in resp.history:
        url = hist.url.lower()
        for domain in _KNOWN_AD_DOMAINS:
            if domain in url:
                logger.debug("Ad domain in redirect: %s", hist.url)
                return True
    url = resp.url.lower()
    for domain in _KNOWN_AD_DOMAINS:
        if domain in url:
            logger.debug("Ad domain in final URL: %s", resp.url)
            return True
    return False


def _detect_audio_transitions(data: bytes, windows: int = 20) -> bool:
    if len(data) < 4096:
        return False
    chunk_size = max(len(data) // windows, 512)
    energies = []
    for i in range(0, len(data), chunk_size):
        chunk = data[i : i + chunk_size]
        if len(chunk) < 128:
            break
        s = sum(b * b for b in chunk) / len(chunk)
        energies.append(s)

    transitions = 0
    for i in range(1, len(energies)):
        prev = energies[i - 1]
        cur = energies[i]
        if prev > 0 and cur > 0:
            ratio = max(prev, cur) / min(prev, cur)
            if ratio > 4.0:
                transitions += 1

    return transitions >= 2


def _check_stream(
    station: dict,
    session: requests.Session,
    commercials: bool = False,
) -> dict:
    result = dict(station, responsive=False)
    codec = station.get("codec", "")
    if codec and not _is_supported_codec(codec):
        return result
    url = station.get("url_resolved") or station.get("url", "")
    if not url:
        return result
    if is_pls_url(url):
        pls = resolve_pls_url(url, session, timeout=5)
        if pls and pls.get("url"):
            station["url_resolved"] = pls["url"]
            url = pls["url"]
            if pls.get("name") and not station.get("name"):
                station["name"] = pls["name"]
        else:
            return result
    try:
        resp = session.get(
            url,
            stream=True,
            timeout=5,
            headers={"User-Agent": "TrayRadio/1.0"},
        )
        if resp.status_code in (200, 206):
            ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ct == "audio/x-scpls":
                content = resp.content.decode("utf-8", errors="replace")
                resp.close()
                from pls_resolver import parse_pls
                pls = parse_pls(content)
                if pls and pls.get("url"):
                    station["url_resolved"] = pls["url"]
                    url = pls["url"]
                    if pls.get("name") and not station.get("name"):
                        station["name"] = pls["name"]
                    resp = session.get(
                        url,
                        stream=True,
                        timeout=5,
                        headers={"User-Agent": "TrayRadio/1.0"},
                    )
                    if resp.status_code not in (200, 206):
                        resp.close()
                        return result
                    ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                else:
                    return result
            if ct and ct not in _KNOWN_BAD_CT:
                chunk = resp.raw.read(1024)
                if chunk:
                    result["responsive"] = True
                    result["_content_type"] = ct
                    if commercials:
                        commercial = False
                        if _check_redirects_for_ads(resp):
                            commercial = True
                        else:
                            more = chunk + resp.raw.read(80896)
                            if _detect_audio_transitions(more):
                                commercial = True
                        result["has_commercial"] = commercial
        resp.close()
    except Exception:
        pass
    return result


def scan_streams(
    stations: list,
    max_workers: int = 5,
    proxies: Optional[dict] = None,
    progress_cb: Optional[Callable] = None,
    responsive_cb: Optional[Callable] = None,
    commercials: bool = False,
) -> list:
    if not stations:
        return []

    session = requests.Session()
    session.headers.update({"User-Agent": "TrayRadio/1.0"})
    if proxies:
        session.proxies.update(proxies)

    stations = [s for s in stations if not s.get("codec") or _is_supported_codec(s.get("codec", ""))]

    total = len(stations)
    checked = 0
    responsive = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_check_stream, s, session, commercials): i
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
                    f"{' AD' if r.get('has_commercial') else ''}"
                )
            except Exception as e:
                results[idx] = dict(stations[idx], responsive=False)
                checked += 1
                if progress_cb:
                    progress_cb(checked, total)
                logger.debug(f"Scan {checked}/{total}: exception -> {e}")

    session.close()
    filtered = [s for s in results if s.get("responsive")]
    logger.info(f"Scan done: {responsive}/{total} responsive")
    return filtered
