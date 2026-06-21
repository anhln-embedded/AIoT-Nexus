# AIoT-Nexus

AIoT-Nexus is a Flet desktop HUD for an AIoT device that can run on a Windows
development laptop or as a fullscreen Raspberry Pi touchscreen service. The app
combines an async core engine, simulated or real STM32 UART hardware, OpenCV
camera tools, Vietnamese voice I/O, LiteLLM function calling, and an optional
XiaoZhi protocol bridge.

The current target display profile is `1280x800`.

## Main Features

- Fullscreen Flet HUD with system state, chat, telemetry, camera preview, camera
  source selection, camera mirror mode, microphone selection, and LLM provider
  settings.
- Async core pipeline for voice and text interactions:
  `LISTENING -> PROCESSING -> SPEAKING -> IDLE`.
- STM32 UART integration with simulator fallback for DHT telemetry, relay state,
  and LED color state.
- OpenCV camera subsystem with background frame capture, live HUD preview,
  face detection, color detection, dynamic camera index selection, and safe
  camera enable/disable transitions.
- Voice subsystem with microphone discovery, Vietnamese STT, local TTS, and
  direct PCM microphone streaming for XiaoZhi.
- Modular MCP-style tool registry for adding new local tools without rewriting
  the chat client.
- LiteLLM tool calling with offline/mock fallback when no external API key is
  available.
- Optional XiaoZhi WebSocket/MQTT gateway that maps AIoT-Nexus tools to
  JSON-RPC MCP `initialize`, `tools/list`, and `tools/call`.
- Pi launcher and systemd helper with display waiting, UART auto-detection, and
  optional fast-forward git auto-update.

## Project Layout

```text
main.py                              Flet entry point
assets/logo/                         PTIT logo assets used by the HUD
scripts/run-pc.ps1                   Windows development launcher
scripts/AIoT-Nexus.sh                Raspberry Pi systemd install/manage helper
scripts/launch-pi.sh                 Raspberry Pi service launcher
src/core/config.py                   .env-backed runtime configuration
src/core/engine.py                   Async app broker and pipeline coordinator
src/hardware/uart.py                 STM32 UART or simulated hardware controller
src/mcp/client.py                    LiteLLM chat and JSON-RPC tool execution
src/mcp/registry.py                  Tool definition, context, and registry
src/mcp/tools/                       Individual MCP tool modules
src/ui/gui/hud.py                    Flet HUD and UI event consumer
src/vision/agent.py                  OpenCV camera streaming and vision tools
src/voice/agent.py                   Microphone, STT, TTS, and PCM streaming
src/xiaozhi_gateway/                 XiaoZhi WebSocket/MQTT bridge
tests/                               Unit and compatibility tests
tools/xiaozhi_registration_tool.py   XiaoZhi activation/.env helper
```

## Runtime Architecture

```text
Flet HUD
  -> AsyncCoreEngine
      -> AsyncHardwareController   (UART or simulator)
      -> AsyncVisionAgent          (camera streaming and vision tools)
      -> AsyncVoiceAgent           (STT, TTS, microphone streaming)
      -> AsyncMcpClient
          -> ToolRegistry
              -> hardware tools
              -> vision tools
              -> camera control tools
              -> weather tools
      -> optional XiaoZhi gateway
          -> XiaoZhi MCP adapter
```

The HUD communicates with the core through `core.ui_queue`. Core events update
state labels, chat messages, telemetry, camera frames, and camera state. Camera
state can be changed from either the UI switch or the MCP camera tool; both paths
flow through `AsyncCoreEngine.set_camera_enabled()` so the switch, layout, and
vision engine remain synchronized.

## MCP Tools

The default registry is built in `src/mcp/tools/catalog.py`. Current local tool
names are:

| Tool | Module | Purpose |
| --- | --- | --- |
| `get_dht_data` | `src/mcp/tools/hardware.py` | Read DHT temperature/humidity through hardware controller |
| `detect_faces` | `src/mcp/tools/vision.py` | Capture/analyze a camera frame and return face count |
| `detect_colors` | `src/mcp/tools/vision.py` | Capture/analyze the center of a camera frame for color |
| `set_camera_enabled` | `src/mcp/tools/camera_control.py` | Turn camera on/off through the same state path as the HUD switch |
| `get_weather` | `src/mcp/tools/weather.py` | Return simulated current weather data |

To add a new MCP tool:

1. Create a module under `src/mcp/tools/`.
2. Return one or more `McpTool` objects from a `get_tools(context)` function.
3. Register the module in `src/mcp/tools/catalog.py`.
4. Add focused tests in `tests/test_services.py`.

`XiaozhiMcpToolAdapter` exposes these tools with the public `self.aiot.*` prefix,
for example `self.aiot.get_dht_data`. Direct local names are also accepted by
the adapter.

## Hardware Model

### STM32 UART

`src/hardware/uart.py` manages the STM32-facing device state:

- `temperature`
- `humidity`
- `relays`
- `led_color`

Supported UART actions:

```text
GET_DHT
SET_RELAY
SET_LED
```

If real UART is disabled, the same controller runs in simulator mode and returns
mocked telemetry/control responses. This keeps the UI, MCP tools, and tests
usable on a Windows laptop without attached hardware.

### Hardware Detection

Python runtime configuration comes from `.env` via `src/core/config.py`:

- `AIOT_IS_PI` controls the Pi/fullscreen UI profile.
- `AIOT_USE_UART` controls real UART versus simulation.
- `AIOT_PORT_WIN` and `AIOT_PORT_PI` provide serial port names.
- `AIOT_BAUDRATE` controls UART speed.

On Raspberry Pi, `scripts/launch-pi.sh` performs the serial-device detection
before Python starts:

1. If `AIOT_USE_UART` is already set, it respects that value.
2. If `AIOT_PORT_PI` is set and exists, it enables UART on that port.
3. Otherwise it checks `/dev/serial0`, `/dev/ttyUSB0`, then `/dev/ttyACM0`.
4. If no device exists, it sets `AIOT_USE_UART=false` and uses simulation.

### Camera And Microphone

Camera and microphone are not handled by `src/hardware/uart.py`.

- Camera discovery lives in `src/vision/agent.py` and scans OpenCV indexes
  `0..4`. Windows uses `cv2.CAP_DSHOW`; other platforms use `cv2.CAP_ANY`.
- Microphone discovery lives in `src/voice/agent.py`, prefers PyAudio, filters
  non-input/alias devices, and falls back to SpeechRecognition microphone names.

## Environment Variables

Create a `.env` file in the project root when needed. `.env` is ignored by git
and should not be committed.

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

AIOT_XIAOZHI_GATEWAY_ENABLED=false
AIOT_XIAOZHI_TRANSPORT=websocket
AIOT_XIAOZHI_URL=
AIOT_XIAOZHI_TOKEN=
AIOT_XIAOZHI_DEVICE_ID=
AIOT_XIAOZHI_CLIENT_ID=
AIOT_XIAOZHI_PROTOCOL_VERSION=1
AIOT_XIAOZHI_AUDIO_SAMPLE_RATE=16000
AIOT_XIAOZHI_AUDIO_FRAME_DURATION=20
AIOT_XIAOZHI_AUTO_CONTINUE=true
AIOT_XIAOZHI_MQTT_USERNAME=
AIOT_XIAOZHI_MQTT_PASSWORD=
AIOT_XIAOZHI_MQTT_PUBLISH_TOPIC=
AIOT_XIAOZHI_MQTT_SUBSCRIBE_TOPIC=

AIOT_AUTO_UPDATE=true
AIOT_UPDATE_REMOTE=origin
AIOT_UPDATE_BRANCH=
```

Notes:

- On Pi, the systemd service sets `AIOT_IS_PI=true`.
- `AIOT_USE_UART=false` forces simulated hardware, even on Pi.
- If `AIOT_USE_UART` is unset on Pi, `launch-pi.sh` tries to auto-detect a UART
  device and falls back to simulation when none is found.
- `AIOT_CAMERA_PREVIEW_FPS` controls HUD preview cadence.
- `AIOT_CAMERA_PREVIEW_WIDTH` and `AIOT_CAMERA_PREVIEW_HEIGHT` control the JPEG
  preview size sent to Flet.
- `AIOT_CAMERA_JPEG_QUALITY` controls preview JPEG quality from `1` to `100`.

## XiaoZhi Gateway

`src/xiaozhi_gateway` provides an opt-in bridge for XiaoZhi-compatible backends.
When `AIOT_XIAOZHI_GATEWAY_ENABLED=true`, `AsyncCoreEngine.start()` creates the
gateway and starts it in a background task.

Supported transports:

- `websocket`: uses XiaoZhi-style headers such as `Authorization`,
  `Protocol-Version`, `Device-Id`, and `Client-Id`.
- `mqtt`: requires explicit publish/subscribe topics because self-hosted
  XiaoZhi-compatible servers can choose different topic layouts.

Gateway behavior:

- App text questions route through `send_text_query()` when the gateway is
  enabled.
- Voice mode can stream microphone PCM frames directly to XiaoZhi.
- Microphone VAD prevents silence from opening a XiaoZhi listening turn. Follow-up
  listening continues automatically by default; set
  `AIOT_XIAOZHI_AUTO_CONTINUE=false` to require a new mic trigger for each turn.
- While a conversation is active, the square stop button closes the current
  XiaoZhi session and returns to idle. The next mic trigger opens a fresh session.
- Incoming XiaoZhi audio frames are decoded with PyAV and played through PyAudio
  when that playback path is available.
- MCP payloads are mapped through `XiaozhiMcpToolAdapter`.

Generate a XiaoZhi activation code and `.env` block:

```powershell
.\.venv\Scripts\python.exe .\tools\xiaozhi_registration_tool.py
```

Use the activation code on `xiaozhi.me`, then copy the generated `.env` block
into the project `.env`.

## Run On Windows Laptop

Use Python 3.11 or 3.12.

```powershell
cd D:\AIoT-Nexus
py -3.12 -m venv .venv
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

## Install On Raspberry Pi

Recommended OS: Raspberry Pi OS 64-bit Desktop. Desktop autologin should be
enabled for the fullscreen UI service.

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

Create `.env`:

```bash
nano .env
```

Minimal Pi `.env`:

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

## Enable Desktop Autologin On Pi

```bash
sudo raspi-config
```

Select:

```text
System Options -> Boot / Auto Login -> Desktop Autologin
```

Reboot after changing this.

## Run On Raspberry Pi Manually

```bash
cd ~/AIoT-Nexus
source .venv/bin/activate
AIOT_IS_PI=true python main.py
```

For hardware simulation on Pi:

```bash
AIOT_IS_PI=true AIOT_USE_UART=false python main.py
```

To force a real UART port:

```bash
AIOT_IS_PI=true AIOT_USE_UART=true AIOT_PORT_PI=/dev/ttyUSB0 python main.py
```

## Run As Raspberry Pi Service

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

`scripts/launch-pi.sh` auto-updates from git by default when the service starts.
It only does a fast-forward update and skips updating if local tracked files have
changes.

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

When `scripts/AIoT-Nexus.sh` or `scripts/launch-pi.sh` changes, reinstall the
service so systemd gets the new unit:

```bash
./scripts/AIoT-Nexus.sh install
./scripts/AIoT-Nexus.sh restart
```

## Development And Tests

Run the full test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test*.py
```

Useful checks:

```powershell
.\.venv\Scripts\python.exe -m py_compile .\tools\xiaozhi_registration_tool.py
```

Core test coverage currently includes:

- simulated hardware operations and serialized UART requests
- MCP JSON-RPC tool execution
- XiaoZhi MCP adapter and gateway behavior
- camera enable/disable race regression coverage
- microphone listing/default resolution
- core start/stop idempotency
- Flet compatibility behavior

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

If `wlr-randr` says it cannot connect, the SSH session does not have the Wayland
runtime environment. That is fine if `launch-pi.sh` logs either:

```text
[AIoT-Nexus] Using Wayland display ...
```

or:

```text
[AIoT-Nexus] Using X11 display :0
```

## Check UART And STM32

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

## Check Camera And Audio

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

### Service Is Active But UI Is Not Visible

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

### AT-SPI Or Accessibility Warnings

These warnings are usually harmless:

```text
AT-SPI: Error retrieving accessibility bus address
atk_socket_embed: assertion 'plug_id != NULL' failed
```

The launcher sets `NO_AT_BRIDGE=1` to suppress most of them.

### `/dev/serial0` Does Not Exist

Either enable serial hardware, connect a USB serial device, or run in
simulation:

```env
AIOT_USE_UART=false
```

Then restart:

```bash
./scripts/AIoT-Nexus.sh restart
```

### XiaoZhi Gateway Connects But Questions Do Not Route

Check:

- `AIOT_XIAOZHI_GATEWAY_ENABLED=true`
- `AIOT_XIAOZHI_URL` is set.
- `AIOT_XIAOZHI_TOKEN`, `AIOT_XIAOZHI_DEVICE_ID`, and
  `AIOT_XIAOZHI_CLIENT_ID` match the activated device.
- Logs show `XiaoZhi gateway connecting via websocket...` or the selected
  transport.

### Camera Toggle Looks Out Of Sync

Camera toggles should flow through `AsyncCoreEngine.set_camera_enabled()`. The
HUD listens for `camera_requested_state` and `camera_state` events so MCP
camera toggles and switch toggles stay aligned. If this regresses, inspect:

- `src/ui/gui/hud.py`
- `src/core/engine.py`
- `src/vision/agent.py`
- `src/mcp/tools/camera_control.py`
