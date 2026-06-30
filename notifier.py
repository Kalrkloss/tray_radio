import logging
import subprocess
import threading
import xml.sax.saxutils as saxutils

logger = logging.getLogger(__name__)

_PS_LOAD_TYPES = (
    "[Windows.UI.Notifications.ToastNotificationManager,"
    " Windows.UI.Notifications, ContentType = WindowsRuntime]"
    " | Out-Null\n"
    "[Windows.Data.Xml.Dom.XmlDocument,"
    " Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]"
    " | Out-Null\n"
)

_PS_TOAST = (
    "$x = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
    "$x.LoadXml('{xml}')\n"
    "$n = New-Object Windows.UI.Notifications.ToastNotification($x)\n"
    "$n.Tag = 'trayradio'\n"
    "[Windows.UI.Notifications.ToastNotificationManager]::"
    "CreateToastNotifier('TrayRadio').Show($n) | Out-Null\n"
)

_PS_TOAST_XML = (
    '<toast duration="long" scenario="reminder">'
    '<visual><binding template="ToastText02">'
    '<text id="1">{title}</text>'
    '<text id="2">{message}</text>'
    '</binding></visual>'
    '<audio silent="true"/>'
    '</toast>'
)


class SilentToastNotifier:
    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._started = False

    def start(self):
        with self._lock:
            if self._started:
                return
            try:
                self._proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", "-"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=0x08000000,
                )
                self._write(_PS_LOAD_TYPES)
                self._started = True
                logger.info("Silent toast notifier started")
            except Exception as e:
                logger.warning("Failed to start silent toast notifier: %s", e)
                self._proc = None
                self._started = False

    def _build_xml(self, title: str, message: str) -> str:
        title = saxutils.escape(title)
        message = saxutils.escape(message)
        return _PS_TOAST_XML.format(title=title, message=message)

    def notify(self, title: str, message: str):
        if not self._started or not self._proc:
            return False
        xml = self._build_xml(title, message)
        cmd = _PS_TOAST.format(xml=xml)
        try:
            with self._lock:
                if self._proc and self._proc.poll() is None:
                    self._write(cmd)
                    return True
                else:
                    logger.warning("PowerShell process died, restarting")
                    self._started = False
                    self.start()
                    if self._started:
                        self._write(cmd)
                        return True
        except Exception as e:
            logger.warning("Toast notification failed: %s", e)
        return False

    def _write(self, text):
        data = (text + "\n").encode("utf-8")
        self._proc.stdin.write(data)
        self._proc.stdin.flush()

    def shutdown(self):
        with self._lock:
            if self._proc:
                try:
                    self._proc.stdin.close()
                    self._proc.terminate()
                    self._proc.wait(timeout=2)
                except Exception:
                    pass
                self._proc = None
            self._started = False
