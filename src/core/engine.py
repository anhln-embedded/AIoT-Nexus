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
    XIAOZHI_CLIENT_ID,
    XIAOZHI_DEVICE_ID,
    XIAOZHI_GATEWAY_ENABLED,
    XIAOZHI_MQTT_PASSWORD,
    XIAOZHI_MQTT_PUBLISH_TOPIC,
    XIAOZHI_MQTT_SUBSCRIBE_TOPIC,
    XIAOZHI_MQTT_USERNAME,
    XIAOZHI_PROTOCOL_VERSION,
    XIAOZHI_TOKEN,
    XIAOZHI_TRANSPORT,
    XIAOZHI_URL,
)
from src.voice.agent import AsyncVoiceAgent
from src.vision.agent import AsyncVisionAgent
from src.hardware.uart import AsyncHardwareController
from src.mcp.client import AsyncMcpClient
from src.xiaozhi_gateway import (
    XiaozhiGatewayConfig,
    XiaozhiMcpToolAdapter,
    XiaozhiMqttGateway,
    XiaozhiWebSocketGateway,
)

class AsyncCoreEngine:
    def __init__(self):
        port = PORT_PI if USE_REAL_UART else PORT_WIN
        self.hw = AsyncHardwareController(
            is_pi=USE_REAL_UART,
            port=port,
            baudrate=BAUDRATE,
        )
        self.vision = AsyncVisionAgent(camera_index=CAMERA_INDEX)
        self.vision.state_callback = self.handle_camera_state_change
        self.voice = AsyncVoiceAgent()
        self.mcp = AsyncMcpClient(
            hw_controller=self.hw,
            vision_agent=self.vision,
            camera_controller=self,
        )

        self.state = "IDLE"
        self.is_running = False
        self.ui_queue = asyncio.Queue()
        
        provider = LLM_PROVIDERS[DEFAULT_PROVIDER]
        self.current_provider = DEFAULT_PROVIDER
        self.api_key = provider["api_key"]
        self.api_base = provider["api_base"]

        self._poller_task = None
        self._xiaozhi_gateway_task = None
        self.xiaozhi_gateway = None
        self._last_response_from_xiaozhi = False
        self._interaction_lock = asyncio.Lock()

    async def start(self):
        """Starts the central core engine, connects hardware, and spawns background tasks."""
        if self.is_running:
            return
        self.is_running = True
        await self.hw.connect(log_callback=self.log_to_ui)
        if self.vision.is_enabled:
            self.vision.start_streaming()
        self._poller_task = asyncio.create_task(self._telemetry_poller_loop())
        if XIAOZHI_GATEWAY_ENABLED:
            self.xiaozhi_gateway = self._create_xiaozhi_gateway()
            self._xiaozhi_gateway_task = asyncio.create_task(self._run_xiaozhi_gateway())
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
        if self._xiaozhi_gateway_task:
            self._xiaozhi_gateway_task.cancel()
            try:
                await self._xiaozhi_gateway_task
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

    async def chat_to_ui(self, role: str, message: str):
        """Broadcasts a chat message to the UI conversation pane."""
        await self.ui_queue.put({
            "type": "chat_message",
            "role": role,
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

    async def _run_xiaozhi_gateway(self):
        try:
            if self.xiaozhi_gateway is None:
                self.xiaozhi_gateway = self._create_xiaozhi_gateway()
            message = f"XiaoZhi gateway connecting via {XIAOZHI_TRANSPORT}..."
            print(message)
            await self.log_to_ui(message)
            await self.xiaozhi_gateway.run_forever()
        except asyncio.CancelledError:
            await self.log_to_ui("XiaoZhi gateway stopped.")
            raise
        except Exception as e:
            await self.log_to_ui(f"XiaoZhi gateway error: {e}")

    def _create_xiaozhi_gateway(self):
        config = XiaozhiGatewayConfig(
            url=XIAOZHI_URL,
            token=XIAOZHI_TOKEN,
            transport=XIAOZHI_TRANSPORT,
            protocol_version=XIAOZHI_PROTOCOL_VERSION,
            device_id=XIAOZHI_DEVICE_ID,
            client_id=XIAOZHI_CLIENT_ID,
            mqtt_username=XIAOZHI_MQTT_USERNAME,
            mqtt_password=XIAOZHI_MQTT_PASSWORD,
            mqtt_publish_topic=XIAOZHI_MQTT_PUBLISH_TOPIC,
            mqtt_subscribe_topic=XIAOZHI_MQTT_SUBSCRIBE_TOPIC,
        )
        adapter = XiaozhiMcpToolAdapter(self.mcp)
        if XIAOZHI_TRANSPORT.lower() == "mqtt":
            gateway = XiaozhiMqttGateway(config, adapter, log_callback=self.log_to_ui)
        else:
            gateway = XiaozhiWebSocketGateway(config, adapter, log_callback=self.log_to_ui)
        gateway.speech_state_callback = self._handle_xiaozhi_speech_state
        return gateway

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

    async def trigger_text_interaction(self, user_text: str):
        """Runs the AIoT interaction pipeline from typed user text."""
        user_text = user_text.strip()
        if not user_text or self.state != "IDLE" or self._interaction_lock.locked():
            return

        async with self._interaction_lock:
            await self._run_text_pipeline(user_text)

    async def _run_voice_pipeline(self):
        try:
            await self.set_state("LISTENING")
            if XIAOZHI_GATEWAY_ENABLED and self.xiaozhi_gateway:
                await self._run_xiaozhi_conversation_loop()
                return
            else:
                user_text = await self.voice.listen(log_callback=self.log_to_ui)
            
            if not user_text.strip():
                await self.log_to_ui("Không phát hiện câu nói hoặc không nghe rõ.")
                await self.set_state("SPEAKING")
                await self.voice.speak("Tôi không nghe thấy gì, xin vui lòng thử lại.", log_callback=self.log_to_ui)
                await self.set_state("IDLE")
                return

            await self.chat_to_ui("user", user_text)
            await self.log_to_ui(f"Bạn nói: \"{user_text}\"")

            if not (XIAOZHI_GATEWAY_ENABLED and self.xiaozhi_gateway and self._last_response_from_xiaozhi):
                await self.set_state("PROCESSING")
                ai_response, b64_frame = await self._ask_assistant(user_text)

            await self.set_state("SPEAKING")
            await self.chat_to_ui("assistant", ai_response)
            if not self._last_response_from_xiaozhi:
                await self.voice.speak(ai_response, log_callback=self.log_to_ui)
            else:
                await self._wait_for_xiaozhi_speech_finished()

        except Exception as e:
            print(f"Error in core pipeline: {e}")
            await self.log_to_ui(f"Lỗi hệ thống: {e}")
            await self.set_state("SPEAKING")
            await self.voice.speak("Hệ thống gặp sự cố, vui lòng thử lại.", log_callback=self.log_to_ui)
        finally:
            await self.set_state("IDLE")
            await self.broadcast_telemetry()

    async def _run_xiaozhi_conversation_loop(self):
        turn = 0
        while True:
            await self.set_state("LISTENING")
            try:
                user_text, ai_response = await self._run_xiaozhi_voice_pipeline(
                    response_timeout=30.0 if turn == 0 else 8.0,
                )
            except TimeoutError:
                if turn == 0:
                    raise
                await self.log_to_ui("XiaoZhi không nghe thấy câu tiếp theo, kết thúc hội thoại.")
                break

            if not user_text.strip():
                break

            await self.chat_to_ui("user", user_text)
            await self.log_to_ui(f"Báº¡n nÃ³i: \"{user_text}\"")
            await self.set_state("SPEAKING")
            await self.chat_to_ui("assistant", ai_response)
            await self._wait_for_xiaozhi_speech_finished()

            turn += 1
            if not self.is_running:
                break

    async def _run_xiaozhi_voice_pipeline(self, response_timeout: float = 30.0) -> tuple[str, str]:
        await self.log_to_ui("Streaming microphone audio to XiaoZhi...")
        print("Streaming microphone audio to XiaoZhi...")

        async def audio_frames():
            async for frame in self.voice.stream_microphone_pcm_frames(
                sample_rate=self.xiaozhi_gateway.config.audio_sample_rate,
                frame_duration_ms=self.xiaozhi_gateway.config.audio_frame_duration,
                channels=self.xiaozhi_gateway.config.audio_channels,
                log_callback=self.log_to_ui,
            ):
                yield frame
            await self.set_state("PROCESSING")

        ai_response = await self.xiaozhi_gateway.send_audio_stream_query(
            audio_frames(),
            sample_rate=self.xiaozhi_gateway.config.audio_sample_rate,
            sample_width=2,
            timeout=response_timeout,
            listen_mode="auto",
        )
        self._last_response_from_xiaozhi = True
        if not ai_response:
            return "", ""
        return "Âm thanh từ micro", ai_response

    async def _handle_xiaozhi_speech_state(self, state: str):
        if state == "SPEAKING":
            await self.set_state("SPEAKING")

    async def _wait_for_xiaozhi_speech_finished(self):
        if self.xiaozhi_gateway and hasattr(self.xiaozhi_gateway, "wait_for_speech_finished"):
            await self.xiaozhi_gateway.wait_for_speech_finished()

    async def _run_text_pipeline(self, user_text: str):
        try:
            await self.chat_to_ui("user", user_text)
            await self.set_state("PROCESSING")

            ai_response, b64_frame = await self._ask_assistant(user_text)

            await self.chat_to_ui("assistant", ai_response)
            await self.set_state("SPEAKING")
            if not self._last_response_from_xiaozhi:
                await self.voice.speak(ai_response, log_callback=self.log_to_ui)
            else:
                await self._wait_for_xiaozhi_speech_finished()

        except Exception as e:
            error_message = str(e) or e.__class__.__name__
            print(f"Error in text pipeline: {error_message}")
            await self.log_to_ui(f"Lỗi hệ thống: {error_message}")
            await self.chat_to_ui("assistant", f"XiaoZhi chưa phản hồi: {error_message}")
            await self.set_state("SPEAKING")
            if not self._last_response_from_xiaozhi:
                await self.voice.speak("Hệ thống gặp sự cố, vui lòng thử lại.", log_callback=self.log_to_ui)
        finally:
            await self.set_state("IDLE")
            await self.broadcast_telemetry()

    async def _ask_assistant(self, user_text: str) -> tuple[str, Optional[str]]:
        self._last_response_from_xiaozhi = False
        if XIAOZHI_GATEWAY_ENABLED and self.xiaozhi_gateway:
            audio_status = "on" if self._xiaozhi_remote_audio_enabled() else "off"
            message = f"Sending question to XiaoZhi... remote_audio={audio_status}"
            print(message)
            await self.log_to_ui(message)
            response = await self.xiaozhi_gateway.send_text_query(
                user_text,
                timeout=15.0,
                ready_timeout=20.0,
            )
            self._last_response_from_xiaozhi = True
            return response, None

        model_name = self._get_selected_model_string()
        return await self.mcp.chat(
            prompt=user_text,
            model_name=model_name,
            api_key=self.api_key,
            api_base=self.api_base,
            tool_hook=self.handle_tool_execution_hook,
            log_callback=self.log_to_ui
        )

    def _xiaozhi_remote_audio_enabled(self) -> bool:
        return bool(
            XIAOZHI_GATEWAY_ENABLED
            and self.xiaozhi_gateway
            and getattr(self.xiaozhi_gateway, "plays_remote_audio", False)
        )

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

    async def handle_camera_state_change(self, enabled: bool):
        """Callback triggered when camera state changes."""
        await self.ui_queue.put({
            "type": "camera_state",
            "value": enabled
        })
        await self.log_to_ui(f"Hệ thống: Đã {'bật' if enabled else 'tắt'} camera.")

    async def set_camera_enabled(self, enabled: bool):
        """Toggles the camera enabled state dynamically."""
        await self.ui_queue.put({
            "type": "camera_requested_state",
            "value": enabled
        })
        await self.vision.set_enabled(enabled)

    async def update_camera_index(self, index: int):
        """Updates the camera index dynamically."""
        await self.vision.update_camera_index(index)
        await self.log_to_ui(f"Hệ thống: Thiết lập sử dụng Camera {index}.")

    async def get_available_cameras(self) -> list[int]:
        """Queries the hardware for available camera indexes."""
        return await self.vision.get_available_cameras()

    async def get_available_microphones(self) -> list[tuple[int, str]]:
        """Queries available microphone input devices."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.voice.list_microphones)

    async def update_microphone_index(self, index: int | None):
        """Updates the microphone input device used for STT."""
        self.voice.set_microphone_index(index)
        label = self.voice.get_microphone_label(index)
        await self.log_to_ui(f"Hệ thống: Thiết lập sử dụng {label}.")
