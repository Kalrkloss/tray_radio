import logging
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_PLS_ENTRY_RE = re.compile(r"^(File|Title|Length)(\d+)\s*=\s*(.+)$", re.IGNORECASE)


def is_pls_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith(".pls"):
        return True
    return False


def parse_pls(content: str) -> dict:
    entries = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("[") or line.startswith("#"):
            continue
        m = _PLS_ENTRY_RE.match(line)
        if m:
            key, num, val = m.group(1).lower(), int(m.group(2)), m.group(3).strip()
            if num not in entries:
                entries[num] = {}
            entries[num][key] = val
    if not entries:
        return {}
    first = entries[min(entries.keys())]
    result = {}
    result["url"] = first.get("file", "")
    if "title" in first:
        result["name"] = first["title"]
    return result


def resolve_pls_url(url: str, session=None, timeout: int = 15) -> Optional[dict]:
    try:
        if session is None:
            import urllib.request
            resp = urllib.request.urlopen(url, timeout=timeout)
            content = resp.read().decode("utf-8", errors="replace")
            resp.close()
        else:
            resp = session.get(url, timeout=timeout, headers={"User-Agent": "TrayRadio/1.0"})
            if not resp.ok:
                return None
            content = resp.text
        result = parse_pls(content)
        if result and result.get("url"):
            return result
    except Exception as e:
        logger.debug("PLS resolve failed for %s: %s", url, e)
    return None
