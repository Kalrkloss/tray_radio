import json
import logging
import socket
import struct
import threading
import time
import urllib.request
import urllib.error
from typing import Optional

from .models import LmsServer

logger = logging.getLogger(__name__)


def _direct_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def probe_http(host: str, port: int = 9000, timeout: float = 3.0) -> Optional[LmsServer]:
    url = f"http://{host}:{port}/jsonrpc.js"
    payload = json.dumps({
        "id": 1, "method": "slim.request",
        "params": ["", ["serverstatus", 0, 0]],
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        # Bypass any globally installed proxy — LMS is always on LAN
        resp = _direct_opener().open(req, timeout=timeout)
        data = json.loads(resp.read().decode("utf-8"))
        result = data.get("result", {})
        server_name = result.get("servername", "") or f"LMS@{host}"
        version = result.get("version", "")
        return LmsServer(host=host, port=port, name=server_name, version=version, is_alive=True)
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.debug("HTTP probe %s:%d failed: %s", host, port, e)
        return None


def probe_ports(host: str, timeout: float = 1.0) -> list[int]:
    open_ports = []
    for port in (9000, 9001, 9002, 9090):
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            open_ports.append(port)
        except (OSError, socket.timeout):
            continue
    return open_ports


def discover(timeout: float = 2.0) -> list[LmsServer]:
    found: list[LmsServer] = []
    # Phase 1: UDP broadcast to port 3483
    mac = b"\x00\x00\x00\x00\x00\x01"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    try:
        sock.sendto(b"d" + mac, ("255.255.255.255", 3483))
        start = time.time()
        while time.time() - start < timeout:
            try:
                data, addr = sock.recvfrom(1024)
                if data and data[0:1] == b"D":
                    host = addr[0]
                    # LMS typically responds on port 3483; probe HTTP on common ports
                    logger.info("UDP discovery: found LMS at %s", host)
                    server = probe_http(host, 9000, timeout=1.0)
                    if server:
                        found.append(server)
                    else:
                        found.append(LmsServer(host=host, port=9000, name=f"LMS@{host}", is_alive=False))
            except socket.timeout:
                break
            except Exception:
                continue
    except Exception as e:
        logger.debug("UDP broadcast failed: %s", e)
    finally:
        sock.close()

    # Phase 2: try some common local IPs if nothing found
    if not found:
        for candidate in ("192.168.1.1", "192.168.0.1", "10.0.0.1", "192.168.1.90", "192.168.1.95"):
            server = probe_http(candidate, 9000, timeout=0.5)
            if server:
                found.append(server)
                break

    return found
