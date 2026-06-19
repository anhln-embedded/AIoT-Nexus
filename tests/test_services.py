import asyncio
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import numpy as np

from src.core.engine import AsyncCoreEngine
from src.core import config
from src.hardware.uart import AsyncHardwareController
from src.mcp.client import AsyncMcpClient
from src.voice.agent import AsyncVoiceAgent
from src.vision.agent import AsyncVisionAgent
from src.xiaozhi_gateway import (
    XiaozhiGatewayConfig,
    XiaozhiMcpToolAdapter,
    XiaozhiWebSocketGateway,
)
from src.xiaozhi_gateway.audio_player import XiaozhiAudioPlayer


class FakeVision:
    def __init__(self):
        self.is_enabled = True
        self.enabled_history = []

    def set_enabled(self, enabled):
        self.is_enabled = enabled
        self.enabled_history.append(enabled)

    async def detect_faces(self):
        return {"face_count": 1, "faces": [], "is_mocked_camera": True}, "frame"

    async def detect_colors(self):
        return {
            "detected_color": "Blue",
            "hsv_values": {"h": 120, "s": 255, "v": 255},
            "is_mocked_camera": True,
        }, "frame"


class HardwareTests(unittest.IsolatedAsyncioTestCase):
    async def test_simulated_things(self):
        hw = AsyncHardwareController(is_pi=False)
        self.assertTrue(await hw.connect())

        dht = await hw.get_dht_data()
        relay = await hw.set_relay(1, True)
        led = await hw.set_led("blue")

        self.assertEqual(dht["status"], "ok")
        self.assertTrue(relay["state"])
        self.assertEqual(led["color"], "blue")
        await hw.disconnect()

    async def test_uart_requests_are_serialized(self):
        hw = AsyncHardwareController(is_pi=False)
        results = await asyncio.gather(*(hw.get_dht_data() for _ in range(3)))
        self.assertTrue(all(item["status"] == "ok" for item in results))


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hw = AsyncHardwareController(is_pi=False)
        await self.hw.connect()
        self.client = AsyncMcpClient(self.hw, FakeVision())

    async def test_json_rpc_tool_execution(self):
        response = await self.client._execute_tool_json_rpc("detect_faces", {})
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["result"]["face_count"], 1)
        self.assertEqual(response["result"]["_b64_frame"], "frame")

    async def test_json_rpc_can_toggle_camera(self):
        response = await self.client._execute_tool_json_rpc(
            "set_camera_enabled",
            {"enabled": False},
        )

        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertFalse(response["result"]["enabled"])
        self.assertEqual(self.client.vision.enabled_history, [False])

    async def test_json_rpc_rejects_invalid_camera_toggle_payload(self):
        response = await self.client._execute_tool_json_rpc(
            "set_camera_enabled",
            {"enabled": "off"},
        )

        self.assertEqual(response["error"]["code"], -32000)
        self.assertIn("enabled", response["error"]["message"])

    async def test_camera_tool_uses_core_camera_controller_when_available(self):
        class FakeCameraController:
            def __init__(self, vision):
                self.vision = vision
                self.enabled_history = []

            async def set_camera_enabled(self, enabled):
                self.enabled_history.append(enabled)
                self.vision.is_enabled = enabled

        vision = FakeVision()
        controller = FakeCameraController(vision)
        client = AsyncMcpClient(self.hw, vision, camera_controller=controller)

        response = await client._execute_tool_json_rpc(
            "set_camera_enabled",
            {"enabled": False},
        )

        self.assertFalse(response["result"]["enabled"])
        self.assertEqual(controller.enabled_history, [False])
        self.assertEqual(vision.enabled_history, [])

    async def test_offline_chat_routes_to_hardware(self):
        answer, frame = await self.client.chat(
            prompt="Nhiệt độ và độ ẩm phòng hiện tại là bao nhiêu?",
            model_name="gemini/gemini-2.5-flash",
            api_key="",
        )
        self.assertIn("DHT22", answer)
        self.assertIsNone(frame)


    async def test_xiaozhi_tools_list_and_call(self):
        adapter = XiaozhiMcpToolAdapter(self.client)

        tools_response = await adapter.handle_payload(
            {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 1,
            }
        )
        tool_names = [tool["name"] for tool in tools_response["result"]["tools"]]
        self.assertIn("self.aiot.get_dht_data", tool_names)
        self.assertIn("self.aiot.set_camera_enabled", tool_names)

        call_response = await adapter.handle_payload(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "self.aiot.detect_faces",
                    "arguments": {},
                },
                "id": 2,
            }
        )
        content = call_response["result"]["content"][0]["text"]
        self.assertIn("face_count", content)
        self.assertNotIn("_b64_frame", content)

        camera_response = await adapter.handle_payload(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "self.aiot.set_camera_enabled",
                    "arguments": {"enabled": False},
                },
                "id": 3,
            }
        )
        self.assertIn('"enabled": false', camera_response["result"]["content"][0]["text"])

    async def test_xiaozhi_gateway_wraps_mcp_response(self):
        adapter = XiaozhiMcpToolAdapter(self.client)
        gateway = XiaozhiWebSocketGateway(
            XiaozhiGatewayConfig(url="ws://localhost:8000/xiaozhi"),
            adapter,
        )

        response = await gateway.handle_json_message(
            {
                "session_id": "session-1",
                "type": "mcp",
                "payload": {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {},
                    "id": 1,
                },
            }
        )

        self.assertEqual(response["type"], "mcp")
        self.assertEqual(response["session_id"], "session-1")
        self.assertEqual(response["payload"]["result"]["serverInfo"]["name"], "AIoT-Nexus")

    def test_xiaozhi_gateway_builds_websocket_headers(self):
        gateway = XiaozhiWebSocketGateway(
            XiaozhiGatewayConfig(
                url="ws://localhost:8000/xiaozhi",
                token="secret",
                device_id="device-1",
                client_id="client-1",
            ),
            XiaozhiMcpToolAdapter(self.client),
        )

        headers = gateway._headers()
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(headers["Device-Id"], "device-1")
        self.assertEqual(headers["Client-Id"], "client-1")

    async def test_xiaozhi_gateway_streams_audio_frames_as_binary(self):
        adapter = XiaozhiMcpToolAdapter(self.client)
        gateway = XiaozhiWebSocketGateway(
            XiaozhiGatewayConfig(url="ws://localhost:8000/xiaozhi"),
            adapter,
        )
        gateway._ready.set()
        gateway._mcp_initialized.set()
        gateway.session_id = "session-1"
        gateway._encode_pcm_chunk_to_opus = lambda *args: [b"opus-frame"]
        gateway._flush_opus_encoder = lambda encoder: [b"opus-tail"]
        gateway._create_opus_encoder = lambda *args: object()

        async def frames():
            yield b"pcm-frame"
            await gateway._text_events.put({"type": "sentence", "text": "Xin chao"})
            await gateway._text_events.put({"type": "tts_stop"})

        response = await gateway.send_audio_stream_query(frames(), timeout=1.0)
        queued = [
            await gateway._outgoing.get(),
            await gateway._outgoing.get(),
            await gateway._outgoing.get(),
            await gateway._outgoing.get(),
        ]

        self.assertEqual(response, "Xin chao")
        self.assertEqual(queued[0]["type"], "listen")
        self.assertEqual(queued[0]["state"], "start")
        self.assertEqual(queued[0]["mode"], "auto")
        self.assertEqual(queued[1], b"opus-frame")
        self.assertEqual(queued[2], b"opus-tail")
        self.assertEqual(queued[3]["state"], "stop")

    async def test_xiaozhi_gateway_stops_microphone_when_stt_arrives(self):
        logs = []

        async def capture_log(message):
            logs.append(message)

        gateway = XiaozhiWebSocketGateway(
            XiaozhiGatewayConfig(url="ws://localhost:8000/xiaozhi"),
            XiaozhiMcpToolAdapter(self.client),
            log_callback=capture_log,
        )

        self.assertFalse(gateway.listening_finished_event.is_set())
        await gateway.handle_json_message({"type": "stt", "text": "Xin chao"})

        self.assertTrue(gateway.listening_finished_event.is_set())
        self.assertEqual(gateway.last_stt_text, "Xin chao")
        self.assertEqual(logs[-1], "[USER]: Xin chao")

    async def test_xiaozhi_tts_stop_reports_idle_and_logs_server_event(self):
        logs = []
        states = []

        async def capture_log(message):
            logs.append(message)

        async def capture_state(state):
            states.append(state)

        gateway = XiaozhiWebSocketGateway(
            XiaozhiGatewayConfig(url="ws://localhost:8000/xiaozhi"),
            XiaozhiMcpToolAdapter(self.client),
            log_callback=capture_log,
        )
        gateway.speech_state_callback = capture_state
        gateway._speech_finished.clear()

        await gateway.handle_json_message({"type": "tts", "state": "stop"})

        self.assertTrue(gateway._speech_finished.is_set())
        self.assertEqual(states, ["IDLE"])
        self.assertEqual(logs[-1], "[XIAOZHI EVENT] TTS stopped")

    async def test_xiaozhi_sentence_callback_runs_before_audio_messages_continue(self):
        events = []

        async def capture_text(text):
            events.append(("text", text))

        gateway = XiaozhiWebSocketGateway(
            XiaozhiGatewayConfig(url="ws://localhost:8000/xiaozhi"),
            XiaozhiMcpToolAdapter(self.client),
        )
        gateway.assistant_text_callback = capture_text

        await gateway.handle_json_message(
            {"type": "tts", "state": "sentence_start", "text": "Xin chao"}
        )

        self.assertEqual(events, [("text", "Xin chao")])

    async def test_xiaozhi_gateway_always_stops_listening_after_audio_error(self):
        gateway = XiaozhiWebSocketGateway(
            XiaozhiGatewayConfig(url="ws://localhost:8000/xiaozhi"),
            XiaozhiMcpToolAdapter(self.client),
        )
        gateway._ready.set()
        gateway._mcp_initialized.set()
        gateway.session_id = "session-1"
        gateway._create_opus_encoder = lambda *args: object()
        gateway._encode_pcm_chunk_to_opus = lambda *args: [b"opus-frame"]
        gateway._flush_opus_encoder = lambda encoder: []

        async def broken_frames():
            yield b"pcm-frame"
            raise RuntimeError("microphone disconnected")

        with self.assertRaisesRegex(RuntimeError, "microphone disconnected"):
            await gateway.send_audio_stream_query(broken_frames(), timeout=1.0)

        queued = [
            await gateway._outgoing.get(),
            await gateway._outgoing.get(),
            await gateway._outgoing.get(),
        ]
        self.assertEqual(queued[0]["state"], "start")
        self.assertEqual(queued[1], b"opus-frame")
        self.assertEqual(queued[2]["state"], "stop")

    def test_xiaozhi_gateway_wraps_binary_audio_for_protocol_versions(self):
        adapter = XiaozhiMcpToolAdapter(self.client)
        gateway_v2 = XiaozhiWebSocketGateway(
            XiaozhiGatewayConfig(url="ws://localhost:8000/xiaozhi", protocol_version=2),
            adapter,
        )
        gateway_v3 = XiaozhiWebSocketGateway(
            XiaozhiGatewayConfig(url="ws://localhost:8000/xiaozhi", protocol_version=3),
            adapter,
        )

        wrapped_v2 = gateway_v2._wrap_binary_audio_packet(b"opus")
        wrapped_v3 = gateway_v3._wrap_binary_audio_packet(b"opus")

        self.assertEqual(gateway_v2._unwrap_binary_audio_packet(wrapped_v2), b"opus")
        self.assertEqual(gateway_v3._unwrap_binary_audio_packet(wrapped_v3), b"opus")
        self.assertNotEqual(wrapped_v2, b"opus")
        self.assertNotEqual(wrapped_v3, b"opus")

    async def test_xiaozhi_gateway_accepts_audio_only_tts_response(self):
        adapter = XiaozhiMcpToolAdapter(self.client)
        gateway = XiaozhiWebSocketGateway(
            XiaozhiGatewayConfig(url="ws://localhost:8000/xiaozhi"),
            adapter,
        )
        gateway._ready.set()
        gateway._mcp_initialized.set()
        gateway.session_id = "session-1"
        gateway._encode_pcm_chunk_to_opus = lambda *args: [b"opus-frame"]
        gateway._flush_opus_encoder = lambda encoder: []
        gateway._create_opus_encoder = lambda *args: object()

        async def frames():
            yield b"pcm-frame"
            await gateway._text_events.put({"type": "tts_start"})
            await gateway._text_events.put({"type": "tts_stop"})

        response = await gateway.send_audio_stream_query(frames(), timeout=1.0)

        self.assertEqual(response, "XiaoZhi audio response")


class VisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_color_detection_on_synthetic_frame(self):
        vision = AsyncVisionAgent()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[190:290, 270:370] = (255, 0, 0)
        vision._grab_frame = lambda: (frame.copy(), False)

        result, encoded_frame = await vision.detect_colors()

        self.assertEqual(result["detected_color"], "Blue")
        self.assertTrue(encoded_frame)

    async def test_camera_enable_waits_for_pending_stop(self):
        vision = AsyncVisionAgent()
        events = []
        started = []

        class SlowThread:
            def join(self):
                time.sleep(0.05)

        async def state_callback(enabled):
            events.append(enabled)

        def fake_start_streaming():
            started.append(True)
            vision.is_streaming = True
            vision.thread_running = True

        vision.cap_thread = SlowThread()
        vision.is_enabled = True
        vision.is_streaming = True
        vision.state_callback = state_callback
        vision.start_streaming = fake_start_streaming

        stop_task = asyncio.create_task(vision.set_enabled(False))
        await asyncio.sleep(0)
        start_task = asyncio.create_task(vision.set_enabled(True))

        await asyncio.gather(stop_task, start_task)

        self.assertTrue(vision.is_enabled)
        self.assertTrue(vision.is_streaming)
        self.assertTrue(vision.thread_running)
        self.assertEqual(events, [False, True])
        self.assertEqual(started, [True])


class VoiceTests(unittest.TestCase):
    def test_windows_microphone_listing_filters_aliases(self):
        class FakeAudio:
            host_apis = {
                0: {"name": "MME"},
                1: {"name": "Windows WASAPI"},
                2: {"name": "Windows WDM-KS"},
            }
            devices = [
                {
                    "index": 0,
                    "name": "Microsoft Sound Mapper - Input",
                    "hostApi": 0,
                    "maxInputChannels": 2,
                },
                {
                    "index": 1,
                    "name": "Microphone Array (Intel)",
                    "hostApi": 0,
                    "maxInputChannels": 4,
                },
                {
                    "index": 2,
                    "name": "Speakers (Realtek)",
                    "hostApi": 1,
                    "maxInputChannels": 0,
                },
                {
                    "index": 3,
                    "name": "Microphone Array (Intel)",
                    "hostApi": 1,
                    "maxInputChannels": 2,
                },
                {
                    "index": 4,
                    "name": "Microphone Array 1 (Intel)",
                    "hostApi": 2,
                    "maxInputChannels": 2,
                },
            ]

            def get_device_count(self):
                return len(self.devices)

            def get_device_info_by_index(self, index):
                return self.devices[index]

            def get_host_api_info_by_index(self, index):
                return self.host_apis[index]

        devices = AsyncVoiceAgent._input_devices_from_audio(FakeAudio())
        devices = AsyncVoiceAgent._prefer_host_api(devices)
        devices = AsyncVoiceAgent._dedupe_devices(devices)

        self.assertEqual(
            [(device["index"], device["name"]) for device in devices],
            [(3, "Microphone Array (Intel)")],
        )

    def test_speaker_listing_keeps_only_preferred_output_devices(self):
        class FakeAudio:
            host_apis = {
                0: {"name": "MME"},
                1: {"name": "Windows WASAPI"},
            }
            devices = [
                {"index": 0, "name": "Microphone", "hostApi": 1, "maxOutputChannels": 0},
                {"index": 1, "name": "Speakers (Realtek)", "hostApi": 0, "maxOutputChannels": 2},
                {"index": 2, "name": "Speakers (Realtek)", "hostApi": 1, "maxOutputChannels": 2},
                {"index": 3, "name": "Headphones", "hostApi": 1, "maxOutputChannels": 2},
            ]

            def get_device_count(self):
                return len(self.devices)

            def get_device_info_by_index(self, index):
                return self.devices[index]

            def get_host_api_info_by_index(self, index):
                return self.host_apis[index]

        devices = AsyncVoiceAgent._output_devices_from_audio(FakeAudio())
        devices = AsyncVoiceAgent._prefer_host_api(devices)
        devices = AsyncVoiceAgent._dedupe_devices(devices)

        self.assertEqual(
            [(device["index"], device["name"]) for device in devices],
            [(2, "Speakers (Realtek)"), (3, "Headphones")],
        )

    def test_xiaozhi_player_opens_selected_output_device(self):
        player = object.__new__(XiaozhiAudioPlayer)
        player._stream = None
        player._audio = Mock()
        player.pyaudio = Mock(paInt16=8)
        player.output_channels = 1
        player.output_sample_rate = 48000
        player.output_device_index = 6
        player._audio.open.return_value = Mock()

        player._ensure_stream()

        player._audio.open.assert_called_once_with(
            format=8,
            channels=1,
            rate=48000,
            output=True,
            output_device_index=6,
            frames_per_buffer=960,
        )

    def test_default_microphone_resolves_to_available_index(self):
        agent = AsyncVoiceAgent()

        with patch.object(agent, "get_default_microphone_index", return_value=7):
            with patch("src.voice.agent.sr.Microphone") as microphone:
                _ = agent.microphone

        microphone.assert_called_once_with(device_index=7)

    def test_microphone_audio_is_downmixed_and_resampled_for_xiaozhi(self):
        frame_count = 960  # 20 ms at 48 kHz
        stereo = np.column_stack(
            (
                np.full(frame_count, 1200, dtype=np.int16),
                np.full(frame_count, -200, dtype=np.int16),
            )
        )

        converted, _ = AsyncVoiceAgent._convert_microphone_chunk(
            stereo.tobytes(),
            sample_width=2,
            input_rate=48000,
            input_channels=2,
            output_rate=16000,
        )

        self.assertIn(len(converted), {638, 640})
        samples = np.frombuffer(converted, dtype=np.int16)
        self.assertTrue(np.all(np.abs(samples - 500) <= 1))


class CoreTests(unittest.IsolatedAsyncioTestCase):
    def test_pi_ui_mode_is_separate_from_uart_mode(self):
        self.assertIsInstance(config.IS_PI, bool)
        self.assertIsInstance(config.USE_REAL_UART, bool)

    async def test_xiaozhi_text_waits_for_ui_render_acknowledgement(self):
        core = AsyncCoreEngine()

        callback_task = asyncio.create_task(
            core._handle_xiaozhi_assistant_text("Hello from XiaoZhi")
        )
        event = await asyncio.wait_for(core.ui_queue.get(), timeout=1.0)

        self.assertEqual(event["type"], "xiaozhi_assistant_part")
        self.assertEqual(event["value"], "Hello from XiaoZhi")
        self.assertFalse(callback_task.done())
        event["rendered"].set_result(True)
        await callback_task

    async def test_start_stop_are_idempotent(self):
        core = AsyncCoreEngine()
        core.hw.connect = AsyncMock(return_value=True)
        core.hw.disconnect = AsyncMock()
        core.vision.close = AsyncMock()

        await core.start()
        await core.start()
        await core.stop()
        await core.stop()

        core.hw.connect.assert_awaited_once()
        core.hw.disconnect.assert_awaited_once()
        core.vision.close.assert_awaited_once()

    async def test_camera_toggle_broadcasts_requested_state_for_ui(self):
        core = AsyncCoreEngine()
        core.vision.set_enabled = AsyncMock()

        await core.set_camera_enabled(False)

        event = await core.ui_queue.get()
        self.assertEqual(event, {"type": "camera_requested_state", "value": False})
        core.vision.set_enabled.assert_awaited_once_with(False)

    async def test_rejects_unknown_provider(self):
        core = AsyncCoreEngine()
        with self.assertRaises(ValueError):
            core.update_llm_settings("unknown", "")

    async def test_xiaozhi_voice_pipeline_streams_microphone_audio(self):
        class FakeGateway:
            def __init__(self):
                self.config = XiaozhiGatewayConfig()
                self.plays_remote_audio = True
                self.last_stt_text = "Xin chao"
                self.streamed_frames = []

            async def send_audio_stream_query(self, frames, sample_rate, sample_width, **kwargs):
                self.sample_rate = sample_rate
                self.sample_width = sample_width
                self.listen_mode = kwargs.get("listen_mode")
                async for frame in frames:
                    self.streamed_frames.append(frame)
                return "XiaoZhi response"

        async def fake_frames(**kwargs):
            yield b"pcm-frame"

        core = AsyncCoreEngine()
        core.xiaozhi_gateway = FakeGateway()
        core.voice.stream_microphone_pcm_frames = fake_frames
        core.voice.listen = AsyncMock()
        core.voice.speak = AsyncMock()
        core.broadcast_telemetry = AsyncMock()

        with patch("src.core.engine.XIAOZHI_GATEWAY_ENABLED", True):
            await core._run_voice_pipeline()

        core.voice.listen.assert_not_awaited()
        core.voice.speak.assert_not_awaited()
        self.assertEqual(core.xiaozhi_gateway.streamed_frames, [b"pcm-frame"])
        self.assertEqual(core.xiaozhi_gateway.sample_rate, core.xiaozhi_gateway.config.audio_sample_rate)
        self.assertEqual(core.xiaozhi_gateway.sample_width, 2)
        self.assertEqual(core.xiaozhi_gateway.listen_mode, "auto")
        queued_events = []
        while not core.ui_queue.empty():
            queued_events.append(core.ui_queue.get_nowait())
        user_chat_events = [
            event
            for event in queued_events
            if event.get("type") == "chat_message" and event.get("role") == "user"
        ]
        self.assertEqual(user_chat_events, [])

    async def test_xiaozhi_voice_pipeline_auto_continues_after_tts_stop(self):
        class FakeGateway:
            def __init__(self):
                self.config = XiaozhiGatewayConfig()
                self.plays_remote_audio = True
                self.tts_stop = asyncio.Event()
                self.wait_started = asyncio.Event()
                self.calls = 0

            async def send_audio_stream_query(self, frames, sample_rate, sample_width, **kwargs):
                async for _frame in frames:
                    pass
                self.calls += 1
                if self.calls == 1:
                    return "XiaoZhi response"
                raise TimeoutError("No follow-up speech")

            async def wait_for_speech_finished(self):
                self.wait_started.set()
                await self.tts_stop.wait()

        async def fake_frames(**kwargs):
            yield b"pcm-frame"

        core = AsyncCoreEngine()
        core.is_running = True
        core.xiaozhi_gateway = FakeGateway()
        core.voice.stream_microphone_pcm_frames = fake_frames
        core.voice.listen = AsyncMock()
        core.voice.speak = AsyncMock()
        core.broadcast_telemetry = AsyncMock()

        with patch("src.core.engine.XIAOZHI_GATEWAY_ENABLED", True):
            task = asyncio.create_task(core._run_voice_pipeline())
            await asyncio.wait_for(core.xiaozhi_gateway.wait_started.wait(), timeout=1.0)
            self.assertEqual(core.state, "SPEAKING")
            self.assertFalse(task.done())
            core.xiaozhi_gateway.tts_stop.set()
            await task

        self.assertEqual(core.state, "IDLE")
        self.assertEqual(core.xiaozhi_gateway.calls, 2)

    async def test_xiaozhi_voice_pipeline_closes_after_farewell(self):
        class FakeGateway:
            def __init__(self):
                self.config = XiaozhiGatewayConfig()
                self.plays_remote_audio = True
                self.last_stt_text = "Tạm biệt"
                self.calls = 0

            async def send_audio_stream_query(self, frames, **kwargs):
                async for _frame in frames:
                    pass
                self.calls += 1
                return "Hẹn gặp lại!"

            async def wait_for_speech_finished(self):
                return True

        async def fake_frames(**kwargs):
            yield b"pcm-frame"

        core = AsyncCoreEngine()
        core.is_running = True
        core.xiaozhi_gateway = FakeGateway()
        core.voice.stream_microphone_pcm_frames = fake_frames
        core.voice.speak = AsyncMock()
        core.broadcast_telemetry = AsyncMock()

        with patch("src.core.engine.XIAOZHI_GATEWAY_ENABLED", True):
            await core._run_voice_pipeline()

        self.assertEqual(core.state, "IDLE")
        self.assertEqual(core.xiaozhi_gateway.calls, 1)


if __name__ == "__main__":
    unittest.main()
