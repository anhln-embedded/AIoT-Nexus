import asyncio
import builtins
from typing import Dict, Any, Optional

def safe_print(*args, **kwargs):
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        new_args = []
        for arg in args:
            if isinstance(arg, str):
                new_args.append(arg.encode('ascii', errors='backslashreplace').decode('ascii'))
            else:
                new_args.append(arg)
        try:
            builtins.print(*new_args, **kwargs)
        except Exception:
            pass

print = safe_print


from src.core.config import (
    BAUDRATE,
    CAMERA_INDEX,
    DEFAULT_PROVIDER,
    IS_PI,
    LLM_PROVIDERS,
    PORT_PI,
    PORT_WIN,
    TELEMETRY_INTERVAL,
    USE_REAL_UART,
)
from src.voice.agent import AsyncVoiceAgent
from src.vision.agent import AsyncVisionAgent
from src.hardware.uart import AsyncHardwareController
from src.mcp.client import AsyncMcpClient

class AsyncCoreEngine:
    def __init__(self):
        port = PORT_PI if USE_REAL_UART else PORT_WIN
        self.hw = AsyncHardwareController(
            is_pi=USE_REAL_UART,
            port=port,
            baudrate=BAUDRATE,
        )
        self.vision = AsyncVisionAgent(camera_index=CAMERA_INDEX)
        self.voice = AsyncVoiceAgent()
        self.mcp = AsyncMcpClient(hw_controller=self.hw, vision_agent=self.vision)

        self.state = "IDLE"
        self.is_running = False
        self.ui_queue = asyncio.Queue()
        
        provider = LLM_PROVIDERS[DEFAULT_PROVIDER]
        self.current_provider = DEFAULT_PROVIDER
        self.api_key = provider["api_key"]
        self.api_base = provider["api_base"]

        self._poller_task = None
        self._interaction_lock = asyncio.Lock()

    async def start(self):
        """Starts the central core engine, connects hardware, and spawns background tasks."""
        if self.is_running:
            return
        self.is_running = True
        await self.hw.connect(log_callback=self.log_to_ui)
        self._poller_task = asyncio.create_task(self._telemetry_poller_loop())
        await self.log_to_ui("Hệ thống AIoT-Nexus đã khởi động thành công.")
        await self.set_state("IDLE")

    async def stop(self):
        """Gracefully shuts down background loops and hardware interfaces."""
        if not self.is_running:
            return
        self.is_running = False
        if self._poller_task:
            self._poller_task.cancel()
            try:
                await self._poller_task
            except asyncio.CancelledError:
                pass
        await self.hw.disconnect()
        await self.vision.close()
        await self.log_to_ui("Hệ thống đã dừng hoạt động.")

    async def set_state(self, new_state: str):
        """Sets internal execution state and broadcasts to UI."""
        self.state = new_state
        await self.ui_queue.put({
            "type": "state",
            "value": new_state
        })

    async def log_to_ui(self, message: str):
        """Broadcasts a text log message to the UI log console."""
        await self.ui_queue.put({
            "type": "log",
            "value": message
        })

    async def broadcast_telemetry(self):
        """Broadcasts current hardware states to the UI dashboard."""
        await self.ui_queue.put({
            "type": "telemetry",
            "temp": self.hw.temperature,
            "humidity": self.hw.humidity,
            "relays": self.hw.relays,
            "led_color": self.hw.led_color
        })

    async def _telemetry_poller_loop(self):
        """Periodically polls sensors and updates UI dashboard when engine is IDLE."""
        while self.is_running:
            try:
                if self.state == "IDLE":
                    await self.hw.get_dht_data()
                    await self.broadcast_telemetry()
            except Exception as e:
                print(f"Telemetry poller loop error: {e}")
            await asyncio.sleep(TELEMETRY_INTERVAL)

    async def handle_tool_execution_hook(self, name: str, b64_frame: str, result: dict):
        """
        Callback triggered by MCP when computer vision tools execute.
        Streams the processed camera frame and updates telemetry to the UI.
        """
        await self.ui_queue.put({
            "type": "camera_frame",
            "value": b64_frame
        })
        await self.log_to_ui(f"[Công Cụ] Thực thi '{name}' thành công.")
        await self.broadcast_telemetry()

    async def trigger_voice_interaction(self):
        """
        Runs the linear pipeline of voice interaction:
        Listen -> Recognize STT -> Ask LLM (MCP Tool routing) -> Speak response TTS -> Idle.
        """
        if self.state != "IDLE" or self._interaction_lock.locked():
            return

        async with self._interaction_lock:
            await self._run_voice_pipeline()

    async def _run_voice_pipeline(self):
        try:
            await self.set_state("LISTENING")
            user_text = await self.voice.listen(log_callback=self.log_to_ui)
            
            if not user_text.strip():
                await self.log_to_ui("Không phát hiện câu nói hoặc không nghe rõ.")
                await self.set_state("SPEAKING")
                await self.voice.speak("Tôi không nghe thấy gì, xin vui lòng thử lại.", log_callback=self.log_to_ui)
                await self.set_state("IDLE")
                return

            await self.set_state("PROCESSING")
            await self.log_to_ui(f"Bạn nói: \"{user_text}\"")

            model_name = self._get_selected_model_string()
            
            ai_response, b64_frame = await self.mcp.chat(
                prompt=user_text,
                model_name=model_name,
                api_key=self.api_key,
                api_base=self.api_base,
                tool_hook=self.handle_tool_execution_hook,
                log_callback=self.log_to_ui
            )

            await self.set_state("SPEAKING")
            await self.voice.speak(ai_response, log_callback=self.log_to_ui)

        except Exception as e:
            print(f"Error in core pipeline: {e}")
            await self.log_to_ui(f"Lỗi hệ thống: {e}")
            await self.set_state("SPEAKING")
            await self.voice.speak("Hệ thống gặp sự cố, vui lòng thử lại.", log_callback=self.log_to_ui)
        finally:
            await self.set_state("IDLE")
            await self.broadcast_telemetry()

    def _get_selected_model_string(self) -> str:
        """Retrieves model string based on UI selection."""
        provider_config = LLM_PROVIDERS.get(self.current_provider, {})
        return provider_config.get("model", "gemini/gemini-2.5-flash")

    def update_llm_settings(self, provider: str, api_key: str, api_base: Optional[str] = None):
        """Updates LLM credentials dynamically from UI."""
        if provider not in LLM_PROVIDERS:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        self.current_provider = provider
        self.api_key = api_key
        self.api_base = api_base
        print(f"Updated dynamic LLM config: Provider={provider}, Model={self._get_selected_model_string()}")

    async def set_camera_enabled(self, enabled: bool):
        """Toggles the camera enabled state dynamically."""
        await self.vision.set_enabled(enabled)
        await self.log_to_ui(f"Hệ thống: Đã {'bật' if enabled else 'tắt'} camera.")

    async def update_camera_index(self, index: int):
        """Updates the camera index dynamically."""
        await self.vision.update_camera_index(index)
        await self.log_to_ui(f"Hệ thống: Thiết lập sử dụng Camera {index}.")

    async def get_available_cameras(self) -> list[int]:
        """Queries the hardware for available camera indexes."""
        return await self.vision.get_available_cameras()
