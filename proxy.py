import ctypes
import ctypes.wintypes
import winreg
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from pypac import PACSession, get_pac

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    mode: str = "system"  # "off", "system", "manual"
    server: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    workers: int = 5

    def to_dict(self):
        return {
            "mode": self.mode,
            "server": self.server,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "workers": self.workers,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            mode=data.get("mode", "system"),
            server=data.get("server", ""),
            port=data.get("port", 0),
            username=data.get("username", ""),
            password=data.get("password", ""),
            workers=data.get("workers", 5),
        )

    def get_proxy_url(self) -> Optional[str]:
        if self.mode == "off":
            return None
        if self.mode == "system":
            return detect_system_proxy()
        if self.mode == "manual":
            if self.server and self.port:
                auth = ""
                if self.username:
                    pw = f":{self.password}" if self.password else ""
                    auth = f"{self.username}{pw}@"
                return f"http://{auth}{self.server}:{self.port}"
        return None

    def create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": "TrayRadio/1.0"})
        if self.mode == "off":
            return session
        if self.mode == "system":
            sys_proxy = detect_system_proxy()
            if sys_proxy:
                session.proxies.update({"http": sys_proxy, "https": sys_proxy})
            pac_url = get_system_pac_url()
            if pac_url:
                try:
                    pac = get_pac(url=pac_url)
                    ps = PACSession(pac=pac)
                    session = ps
                    session.headers.update({"User-Agent": "TrayRadio/1.0"})
                except Exception as e:
                    logger.warning(f"PAC session failed: {e}")
        if self.mode == "manual":
            proxy_url = self.get_proxy_url()
            if proxy_url:
                session.proxies.update({"http": proxy_url, "https": proxy_url})
        return session


_WINHTTP_CURRENT_USER_IE_PROXY_CONFIG = None
_WINHTTP_AUTOPROXY_OPTIONS = None
_WINHTTP_PROXY_INFO = None


def _get_winhttp_types():
    global _WINHTTP_CURRENT_USER_IE_PROXY_CONFIG, _WINHTTP_AUTOPROXY_OPTIONS, _WINHTTP_PROXY_INFO

    class WINHTTP_CURRENT_USER_IE_PROXY_CONFIG(ctypes.Structure):
        _fields_ = [
            ("fAutoDetect", ctypes.wintypes.BOOL),
            ("lpszAutoConfigUrl", ctypes.wintypes.LPCWSTR),
            ("lpszProxy", ctypes.wintypes.LPCWSTR),
            ("lpszProxyBypass", ctypes.wintypes.LPCWSTR),
        ]

    class WINHTTP_AUTOPROXY_OPTIONS(ctypes.Structure):
        _fields_ = [
            ("dwFlags", ctypes.wintypes.DWORD),
            ("dwAutoDetectFlags", ctypes.wintypes.DWORD),
            ("lpszAutoConfigUrl", ctypes.wintypes.LPCWSTR),
            ("lpvReserved", ctypes.c_void_p),
            ("dwReserved", ctypes.wintypes.DWORD),
            ("fAutoLogonIfChallenged", ctypes.wintypes.BOOL),
        ]

    class WINHTTP_PROXY_INFO(ctypes.Structure):
        _fields_ = [
            ("dwAccessType", ctypes.wintypes.DWORD),
            ("lpszProxy", ctypes.wintypes.LPCWSTR),
            ("lpszProxyBypass", ctypes.wintypes.LPCWSTR),
        ]

    _WINHTTP_CURRENT_USER_IE_PROXY_CONFIG = WINHTTP_CURRENT_USER_IE_PROXY_CONFIG
    _WINHTTP_AUTOPROXY_OPTIONS = WINHTTP_AUTOPROXY_OPTIONS
    _WINHTTP_PROXY_INFO = WINHTTP_PROXY_INFO

    return (
        WINHTTP_CURRENT_USER_IE_PROXY_CONFIG,
        WINHTTP_AUTOPROXY_OPTIONS,
        WINHTTP_PROXY_INFO,
    )


WINHTTP_AUTOPROXY_AUTO_DETECT = 0x00000001
WINHTTP_AUTOPROXY_CONFIG_URL = 0x00000002
WINHTTP_AUTO_DETECT_TYPE_DHCP = 0x00000001
WINHTTP_AUTO_DETECT_TYPE_DNS_A = 0x00000002
WINHTTP_ACCESS_TYPE_NAMED_PROXY = 3
WINHTTP_ACCESS_TYPE_NO_PROXY = 1
WINHTTP_ACCESS_TYPE_DEFAULT_PROXY = 0


def get_ie_proxy_config_raw():
    try:
        types = _get_winhttp_types()
        ProxyCfg = types[0]
        winhttp = ctypes.windll.winhttp
        config = ProxyCfg()
        if winhttp.WinHttpGetIEProxyConfigForCurrentUser(ctypes.byref(config)):
            return config
    except Exception as e:
        logger.debug(f"WinHttpGetIEProxyConfigForCurrentUser failed: {e}")
    return None


def get_system_pac_url() -> Optional[str]:
    config = get_ie_proxy_config_raw()
    if config and config.lpszAutoConfigUrl:
        return config.lpszAutoConfigUrl
    return None


def get_system_auto_detect() -> bool:
    config = get_ie_proxy_config_raw()
    return bool(config and config.fAutoDetect)


def detect_system_proxy() -> Optional[str]:
    config = get_ie_proxy_config_raw()
    if config:
        if config.lpszProxy:
            proxy = config.lpszProxy
            if "=" in proxy:
                parts = proxy.split(";")
                for part in parts:
                    part = part.strip()
                    if part.lower().startswith("http="):
                        return part.split("=", 1)[1].strip()
                for part in parts:
                    part = part.strip()
                    if "=" not in part:
                        return part
            return proxy
    return detect_system_proxy_registry()


def detect_system_proxy_registry() -> Optional[str]:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
        if proxy_enable:
            proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            return proxy_server
    except Exception:
        pass
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
        if proxy_enable:
            proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            return proxy_server
    except Exception:
        pass
    return None


def resolve_proxy_for_url(url: str) -> Optional[str]:
    import time as _time
    _start = _time.time()
    logger.info(f"resolve_proxy_for_url: starting for {url}")

    config = get_ie_proxy_config_raw()
    if not config:
        logger.info("resolve_proxy_for_url: no IE proxy config")
        return None

    winhttp = ctypes.windll.winhttp
    types = _get_winhttp_types()
    AutoProxyOpts = types[1]
    ProxyInfo = types[2]

    session = winhttp.WinHttpOpen(
        "TrayRadio/1.0",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        None, None, 0,
    )
    if not session:
        logger.debug("WinHttpOpen failed")
        return None

    try:
        auto_opts = AutoProxyOpts()
        auto_opts.fAutoLogonIfChallenged = True

        if config.lpszAutoConfigUrl:
            auto_opts.dwFlags = WINHTTP_AUTOPROXY_CONFIG_URL
            auto_opts.lpszAutoConfigUrl = config.lpszAutoConfigUrl
        elif config.fAutoDetect:
            auto_opts.dwFlags = WINHTTP_AUTOPROXY_AUTO_DETECT
            auto_opts.dwAutoDetectFlags = (
                WINHTTP_AUTO_DETECT_TYPE_DHCP | WINHTTP_AUTO_DETECT_TYPE_DNS_A
            )
        else:
            if config.lpszProxy:
                proxy = config.lpszProxy
                if "=" in proxy:
                    parts = proxy.split(";")
                    for part in parts:
                        part = part.strip()
                        if part.lower().startswith("http="):
                            return part.split("=", 1)[1].strip()
                    for part in parts:
                        part = part.strip()
                        if "=" not in part:
                            return part
                return proxy
            return None

        proxy_info = ProxyInfo()
        if winhttp.WinHttpGetProxyForUrl(
            session,
            ctypes.byref(auto_opts),
            url,
            ctypes.byref(proxy_info),
        ):
            if proxy_info.dwAccessType == WINHTTP_ACCESS_TYPE_NAMED_PROXY:
                result = proxy_info.lpszProxy
                logger.info(f"resolve_proxy_for_url: done in {_time.time()-_start:.1f}s, proxy={result}")
                return result
        else:
            err = ctypes.windll.kernel32.GetLastError()
            logger.info(f"resolve_proxy_for_url: WinHttpGetProxyForUrl failed (error {err}) in {_time.time()-_start:.1f}s")
            if config.lpszProxy:
                fallback = config.lpszProxy
                logger.info(f"resolve_proxy_for_url: using fallback proxy {fallback}")
                return fallback
    finally:
        winhttp.WinHttpCloseHandle(session)

    logger.info(f"resolve_proxy_for_url: no proxy found in {_time.time()-_start:.1f}s")
    return None
