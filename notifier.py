import logging
import subprocess
import threading
import uuid

logger = logging.getLogger(__name__)

_PS_INIT = (
    'Add-Type -AssemblyName System.Runtime.WindowsRuntime\n'
    '$n = [Windows.UI.Notifications.ToastNotificationManager,'
    ' Windows.UI.Notifications, ContentType = WindowsRuntime]\n'
)

_PS_TOAST_TEMPLATE = (
    "$t = [Windows.UI.Notifications.ToastNotificationManager]::"
    "GetTemplateContent(0)\n"
    "$x = [Windows.Data.Xml.Dom.XmlDocument]::New()\n"
    "$x.LoadXml($t.GetXml())\n"
    "$ns = $x.SelectNodes('//text')\n"
    "if ($ns.Length -ge 1) {{"
    "$ns[0].AppendChild($x.CreateTextNode('{title}')) | Out-Null}}\n"
    "if ($ns.Length -ge 2) {{"
    "$ns[1].AppendChild($x.CreateTextNode('{message}')) | Out-Null}}\n"
    "$a = $x.CreateElement('audio')\n"
    "$a.SetAttribute('silent','true')\n"
    "$x.SelectSingleNode('//toast').AppendChild($a) | Out-Null\n"
    "$n = [Windows.UI.Notifications.ToastNotification]::New($x)\n"
    "$n.Tag = '{tag}'\n"
    "[Windows.UI.Notifications.ToastNotificationManager]::"
    "CreateToastNotifier('TrayRadio').Show($n)\n"
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
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000,
                )
                self._write(_PS_INIT)
                self._started = True
                logger.info("Silent toast notifier started")
            except Exception as e:
                logger.warning("Failed to start silent toast notifier: %s", e)
                self._proc = None
                self._started = False

    def notify(self, title, message):
        if not self._started or not self._proc:
            return False
        tag = uuid.uuid4().hex[:8]
        title_esc = title.replace("'", "''")
        msg_esc = message.replace("'", "''")
        cmd = _PS_TOAST_TEMPLATE.format(
            title=title_esc, message=msg_esc, tag=tag
        )
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
        data = (text + "\n").encode("utf-16-le")
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
