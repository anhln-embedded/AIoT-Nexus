# AIoT-Nexus

AIoT-Nexus is a Flet desktop HUD for a Raspberry Pi based AIoT device. It runs a voice-first async pipeline with simulated or real STM32 UART hardware, OpenCV camera tools, LiteLLM routing, and a fullscreen touchscreen UI.

The current target display profile is `1280x800`.

## Project Layout

```text
main.py                    Flet entry point
src/core/config.py         Runtime configuration and environment variables
src/core/engine.py         Async application broker
src/ui/gui/hud.py          Flet HUD
src/hardware/uart.py       UART or simulated hardware controller
src/vision/agent.py        OpenCV vision tools
src/voice/agent.py         STT/TTS voice agent
src/mcp/client.py          LiteLLM and tool routing
scripts/run-pc.ps1         Windows laptop preview launcher
scripts/AIoT-Nexus.sh      Raspberry Pi systemd manager
scripts/launch-pi.sh       Raspberry Pi GUI/service launcher
tests/                     Unit and compatibility tests
```

## Environment Variables

Create a `.env` file in the project root when needed:

```env
GEMINI_API_KEY=
OPENAI_API_KEY=

AIOT_IS_PI=false
AIOT_USE_UART=false
AIOT_DISPLAY_WIDTH=1280
AIOT_DISPLAY_HEIGHT=800
AIOT_CAMERA_INDEX=0
AIOT_TELEMETRY_INTERVAL=5.0

AIOT_CAMERA_PREVIEW_FPS=30
AIOT_CAMERA_PREVIEW_WIDTH=640
AIOT_CAMERA_PREVIEW_HEIGHT=360
AIOT_CAMERA_JPEG_QUALITY=75

AIOT_PORT_WIN=COM3
AIOT_PORT_PI=/dev/serial0
AIOT_BAUDRATE=115200
```

Important:

- `.env` is ignored by git and should not be committed.
- On Pi, the service sets `AIOT_IS_PI=true` automatically.
- `AIOT_USE_UART=false` uses simulated hardware even on Pi.
- If `AIOT_USE_UART` is unset on Pi, `launch-pi.sh` auto-detects `/dev/serial0`, `/dev/ttyUSB0`, then `/dev/ttyACM0`; if none exists, it falls back to simulation.

Camera preview tuning:

- `AIOT_CAMERA_PREVIEW_FPS` controls the UI preview render cadence. Use `30` on a capable Windows laptop; lower to `24` or `20` if the preview stutters.
- `AIOT_CAMERA_PREVIEW_WIDTH` and `AIOT_CAMERA_PREVIEW_HEIGHT` control the JPEG preview size sent to Flet. The default `640x360` matches the HUD panel.
- `AIOT_CAMERA_JPEG_QUALITY` controls preview JPEG quality from `1` to `100`. Use `75` for a good balance; lower it if CPU usage is high.
- The HUD has a `SOI GƯƠNG` switch. It only flips the live preview horizontally; camera tool processing still uses the original frame.

## Run on Windows Laptop

Use Python 3.11.

```powershell
cd F:\Vali
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run the PC preview profile:

```powershell
.\scripts\run-pc.ps1
```

Or run directly after activating `.venv`:

```powershell
python .\main.py
```

The PC preview launcher sets:

```text
AIOT_IS_PI=false
AIOT_USE_UART=false
AIOT_DISPLAY_WIDTH=1280
AIOT_DISPLAY_HEIGHT=800
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Install on Raspberry Pi

Recommended OS: Raspberry Pi OS 64-bit Desktop. Desktop autologin should be enabled for the fullscreen UI service.

Install system packages:

```bash
sudo apt update
sudo apt full-upgrade -y

sudo apt install -y \
  python3 python3-venv python3-dev \
  build-essential git \
  portaudio19-dev libasound2-dev \
  libgtk-3-0 libgl1 libglib2.0-0 \
  libmpv2 mpv \
  ffmpeg v4l-utils
```

Clone or copy the project:

```bash
cd ~
git clone <YOUR_REPO_URL> AIoT-Nexus
cd ~/AIoT-Nexus
```

Create the virtual environment on the Pi. Do not copy `.venv` from Windows.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Microphone input selection uses PyAudio, which is included in `requirements.txt`.
If you install dependencies manually and microphone listing is unavailable, install it with:

```bash
pip install PyAudio
```

Create `.env`:

```bash
nano .env
```

Example Pi `.env`:

```env
GEMINI_API_KEY=
OPENAI_API_KEY=

AIOT_DISPLAY_WIDTH=1280
AIOT_DISPLAY_HEIGHT=800
AIOT_CAMERA_INDEX=0
AIOT_BAUDRATE=115200
```

Enable device permissions and reboot:

```bash
sudo usermod -aG dialout,video,audio $USER
sudo reboot
```

## Enable Desktop Autologin on Pi

```bash
sudo raspi-config
```

Select:

```text
System Options -> Boot / Auto Login -> Desktop Autologin
```

Reboot after changing this.

## Run on Raspberry Pi Manually

```bash
cd ~/AIoT-Nexus
source .venv/bin/activate
AIOT_IS_PI=true python main.py
```

For hardware simulation on Pi:

```bash
AIOT_IS_PI=true AIOT_USE_UART=false python main.py
```

## Run as Raspberry Pi Service

Install and start the service:

```bash
cd ~/AIoT-Nexus
chmod +x scripts/*.sh
./scripts/AIoT-Nexus.sh install
```

Manage the service:

```bash
./scripts/AIoT-Nexus.sh start
./scripts/AIoT-Nexus.sh stop
./scripts/AIoT-Nexus.sh restart
./scripts/AIoT-Nexus.sh status
./scripts/AIoT-Nexus.sh logs
./scripts/AIoT-Nexus.sh enable
./scripts/AIoT-Nexus.sh disable
./scripts/AIoT-Nexus.sh uninstall
```

The systemd service name is:

```bash
aiot-nexus.service
```

Equivalent direct commands:

```bash
sudo systemctl restart aiot-nexus.service
sudo systemctl status aiot-nexus.service
sudo journalctl -u aiot-nexus.service -f
```

Do not run `aiot-nexus.service stop`; service files are not shell commands.

## Service Auto Update

`scripts/launch-pi.sh` auto-updates from git by default when the service starts. It only does a fast-forward update and skips updating if local tracked files have changes.

Variables:

```env
AIOT_AUTO_UPDATE=true
AIOT_UPDATE_REMOTE=origin
AIOT_UPDATE_BRANCH=
```

Disable auto-update:

```env
AIOT_AUTO_UPDATE=false
```

## Check Raspberry Pi Display

From SSH:

```bash
DISPLAY=:0 xrandr --current | grep '*'
fbset -s
cat /sys/class/graphics/fb0/virtual_size
```

Expected for the current target panel:

```text
1280x800
```

If `wlr-randr` says it cannot connect, the SSH session does not have the Wayland runtime environment. That is fine if `launch-pi.sh` logs either:

```text
[AIoT-Nexus] Using Wayland display ...
```

or:

```text
[AIoT-Nexus] Using X11 display :0
```

## Check UART and STM32

List serial devices:

```bash
ls -l /dev/serial* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

For GPIO UART, enable serial hardware:

```bash
sudo raspi-config
```

Select:

```text
Interface Options -> Serial Port
Login shell over serial: No
Serial hardware enabled: Yes
```

If no serial device exists, the launcher logs:

```text
[AIoT-Nexus] No UART device found; using hardware simulation.
```

To force simulation:

```env
AIOT_USE_UART=false
```

To force a real port:

```env
AIOT_USE_UART=true
AIOT_PORT_PI=/dev/ttyUSB0
```

## Check Camera and Audio

Camera:

```bash
v4l2-ctl --list-devices
```

Audio:

```bash
arecord -l
aplay -l
```

Quick microphone test:

```bash
arecord -d 5 test.wav
aplay test.wav
```

## Troubleshooting

### `libmpv.so.2: cannot open shared object file`

Install MPV runtime libraries:

```bash
sudo apt install -y libmpv2 mpv
sudo ldconfig
ldconfig -p | grep libmpv
```

### Service is active but UI is not visible

Check logs:

```bash
./scripts/AIoT-Nexus.sh logs
```

Look for:

```text
[AIoT-Nexus] Using X11 display :0
```

or:

```text
[AIoT-Nexus] Using Wayland display ...
```

If neither appears, enable Desktop Autologin and reboot.

### AT-SPI or accessibility warnings

These warnings are usually harmless:

```text
AT-SPI: Error retrieving accessibility bus address
atk_socket_embed: assertion 'plug_id != NULL' failed
```

The launcher sets `NO_AT_BRIDGE=1` to suppress most of them.

### `/dev/serial0` does not exist

Either enable serial hardware, connect a USB serial device, or run in simulation:

```env
AIOT_USE_UART=false
```

Then restart:

```bash
./scripts/AIoT-Nexus.sh restart
```

### Update service after changing scripts

When `scripts/AIoT-Nexus.sh` or `scripts/launch-pi.sh` changes, reinstall the service so systemd gets the new unit:

```bash
./scripts/AIoT-Nexus.sh install
./scripts/AIoT-Nexus.sh restart
```

