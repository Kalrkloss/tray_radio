import sys, os, tempfile, array, math, wave
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QTimer

rate = 22050
duration = 10
tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
samples = array.array("h", [int(16000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate * duration)])
with wave.open(tmp.name, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(samples.tobytes())

app = QApplication(sys.argv)
wmp = QAxWidget("{6BF52A52-394A-11D3-B153-00C04F79FAA6}")
wmp.setVisible(True)
wmp.setGeometry(-1000, -1000, 1, 1)
wmp.dynamicCall("uiMode", "none")
wmp.dynamicCall("windowlessVideo", True)
wmp.dynamicCall("URL", tmp.name)
wmp.dynamicCall("settings.volume", 100)
print("WMP ready, state:", wmp.dynamicCall("playState"), flush=True)

def try_play():
    print("Calling play()...", flush=True)
    state = wmp.dynamicCall("playState")
    print("Pre-play state:", state, flush=True)
    # Try: stop, then reopen and play
    wmp.dynamicCall("controls.stop()")
    wmp.dynamicCall("controls.currentPosition", 0)
    QTimer.singleShot(200, lambda: wmp.dynamicCall("controls.play()"))
    QTimer.singleShot(1000, check)

def check():
    s = wmp.dynamicCall("playState")
    print(f"State: {s}  Status: {wmp.dynamicCall('status')}", flush=True)
    if s == 3:
        print("PLAYING!", flush=True)
        app.quit()
    elif s == 1:
        print("STOPPED", flush=True)
        app.quit()
    else:
        QTimer.singleShot(1000, check)

QTimer.singleShot(500, try_play)
app.exec_()
wmp.dynamicCall("controls.stop()")
os.unlink(tmp.name)
