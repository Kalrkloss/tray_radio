import socket, time
from urllib.parse import unquote

s = socket.create_connection(("192.168.1.90", 9090), timeout=5)
s.settimeout(2)
# Read banner (empty line)
try:
    while True:
        if s.recv(1) == b"\n":
            break
except socket.timeout:
    pass
s.sendall(b"players 0 99\n")
time.sleep(0.3)
resp = b""
try:
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        resp += chunk
except socket.timeout:
    pass
s.close()
text = resp.decode("utf-8", errors="replace")
tokens = text.split()
current = {}
players = []
for tok in tokens[1:]:
    if "%3A" not in tok:
        continue
    key, _, raw = tok.partition("%3A")
    val = unquote(raw)
    if key == "playerindex":
        if current and "playerid" in current:
            players.append(current)
        current = {}
    current[key] = val
if current and "playerid" in current:
    players.append(current)
for p in players:
    name = p.get("name", "?")
    mac = p.get("playerid", "?")
    ip = p.get("ip", "?").split(":")[0]
    model = p.get("model", "?")
    power = p.get("power", "?")
    print(f"  {name:20s} MAC={mac}  IP={ip}  model={model}  power={power}")
print(f"Total: {len(players)} players")
