# Tray Radio

A Windows 11 system tray internet radio player. Plays MP3, AAC/AAC+, FLAC, OGG Vorbis, and WAV streams. Features a station browser, playlist management, autostart, and audio output device selection.

## Screenshots

| Tray Icon | Now Playing Notification |
|---|---|
| ![Tray Icon](screenshots/01_tray_icon.png) | ![Notification](screenshots/02_notification.png) |

| Station Browser | Settings |
|---|---|
| ![Station Browser](screenshots/03_station_browser.png) | ![Settings](screenshots/04_settings.png) |

## Features

- **System tray operation** — runs silently in the notification area; right-click for menu
- **Station Browser** — search [radio-browser.info](https://radio-browser.info) with codec filtering, parallel stream checking, quick preview
- **Playlist management** — multiple named playlists, drag-to-reorder, duplicate prevention by UUID
- **Now Playing** — balloon notifications and tooltip showing current stream/song
- **AAC/AAC+ support** — via PyAV decoding (no external codecs required)
- **Output device selection** — choose your audio hardware (speakers, headphones, etc.)
- **Auto-start** — launch at Windows login via registry
- **Auto-play** — resume last stream on startup
- **Proxy support** — auto-detects system proxy via WinHTTP API; uses PAC if configured
- **Single-file build** — self-contained `.exe`, no runtime dependencies

## Install

### MSI Installer (recommended)

Download `Tray Radio.msi` from the [Releases](https://github.com/HermanF/tray_radio/releases) page. The installer:

- Installs to `Program Files\Tray Radio`
- Creates Start Menu and Desktop shortcuts
- Creates `%APPDATA%\tray_radio` for configuration
- Adds Add/Remove Programs entry
- Supports upgrades (old version auto-removed)

### Portable EXE

Download `Tray Radio.exe` from the [Releases](https://github.com/HermanF/tray_radio/releases) page. Run it directly — no installation needed. Configuration is stored in `%APPDATA%\tray_radio\`.

## How to Use

### First Launch

Run `Tray Radio.exe`. An icon appears in the system tray (near the clock). Right-click the icon to open the menu.

### Tray Menu

| Menu Item | Action |
|---|---|
| Browse Stations | Open the station browser to search and add stations |
| Playlists | Submenu listing your playlists; click one to play it |
| Playing: _station name_ | Currently playing stream (truncated to 64 chars) |
| Settings | Open settings dialog |
| Search Stations | Quick search (reuses browser dialog) |
| Quit | Exit the application |

### Station Browser

1. Click **Browse Stations** in the tray menu
2. Type a search term (e.g., "jazz", "bbc", "classical")
3. Select a codec filter (All, MP3, AAC, FLAC, etc.) to narrow results
4. Click **Search** — results are scanned in parallel for responsiveness
5. Green-highlighted rows are reachable; grey rows are unreachable
6. Double-click a row or select it and click **Preview** to test the stream
7. Select a target playlist from the dropdown and click **Add** to save

The browser dialog persists between opens — your search results and terms are preserved.

### Playlists

- **Add playlist**: In Settings or from the Playlist editor
- **Manage playlists**: Click playlists from the tray menu, then use the editor to rename, reorder, or remove streams
- **Duplicate protection**: The same station UUID cannot appear twice in a playlist
- **Move between playlists**: Drag streams between playlist tabs

### Settings

| Setting | Description |
|---|---|
| Auto-play last stream | Resume playback on startup |
| Auto-start with Windows | Launch at login via `HKCU\...\Run` |
| Audio Output | Select audio device from detected hardware; falls back to default if device is disconnected |
| Scan Workers | Number of parallel threads for stream checking (higher = faster but more bandwidth) |

### Now Playing

When a stream plays, a balloon notification displays the station name and current song (if provided by the stream). Hovering over the tray icon shows the info in a tooltip. The notification is silent (no sound).

### Audio Output

In Settings, choose your audio device from the dropdown. The device name is saved in `config.json`. If the device is disconnected (e.g., USB headphones unplugged), playback falls back to the system default — the saved name stays ready for when the device reappears.

## Build from Source

### Requirements

- Python 3.14+
- Windows 11 (may work on 10, untested)
- WiX Toolset v7 (for MSI, optional)

### Setup

```powershell
git clone https://github.com/HermanF/tray_radio.git
cd tray_radio
pip install -r requirements.txt
```

### Build EXE

```powershell
python build.py
```

Output: `dist\Tray Radio.exe` (~97 MB)

### Build MSI

WiX Toolset v7 is required. Install it:

```powershell
dotnet tool install -g wix
```

Then run `python build.py` — it builds both the EXE and MSI.

Output: `dist\Tray Radio.msi` (~96 MB)

### Run from Source

```powershell
python main.py
```

### Dependencies

- [PyQt5](https://pypi.org/project/PyQt5/) — UI dialogs
- [pystray](https://pypi.org/project/pystray/) — system tray icon and menu
- [miniaudio](https://pypi.org/project/miniaudio/) — audio playback (MP3, FLAC, OGG, WAV)
- [av](https://pypi.org/project/av/) — AAC/AAC+ decoding (PyAV 17.1.0+)
- [pywin32](https://pypi.org/project/pywin32/) — Windows shell integration, AUMID, notifications
- [Pillow](https://pypi.org/project/Pillow/) — icon generation and image processing
- [pypac](https://pypi.org/project/pypac/) — PAC proxy resolution
- [radio-browser](https://pypi.org/project/radio-browser/) — station catalog API client
- [numpy](https://pypi.org/project/numpy/) — audio buffer conversion (via PyAV)
- [PyInstaller](https://pypi.org/project/PyInstaller/) — single-file EXE build

## Project Structure

| File | Purpose |
|---|---|
| `main.py` | Application entry point, Qt app setup, tray <-> dialog wiring |
| `tray.py` | System tray icon, menu, notifications, AUMID shortcut |
| `player.py` | Audio playback: miniaudio + PyAV AAC fallback, device selection |
| `proxy.py` | Proxy detection, auto-start registry, configuration |
| `catalog.py` | radio-browser.info API client |
| `scanner.py` | Parallel stream responsiveness checking with codec pre-filter |
| `playlist_manager.py` | JSON playlist storage, duplicate prevention |
| `icon_generator.py` | Station favicon fetch/cache, playing icon generation |
| `ui/station_browser.py` | Station search/scan/preview/add dialog |
| `ui/settings_dialog.py` | Settings dialog with audio device selection |
| `ui/playlist_editor.py` | Playlist management dialog |
| `build.py` | PyInstaller + WiX MSI build script |
| `installer.wxs` | WiX source for MSI installer |
