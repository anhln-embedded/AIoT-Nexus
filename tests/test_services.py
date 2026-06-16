import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import numpy as np

from src.core.engine import AsyncCoreEngine
from src.core import config
from src.hardware.uart import AsyncHardwareController
from src.mcp.client import AsyncMcpClient
from src.voice.agent import AsyncVoiceAgent
from src.vision.agent import AsyncVisionAgent


class FakeVision:
    def __init__(self):
        self.is_enabled = True

    def set_enabled(self, enabled):
        self.is_enabled = enabled

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

    async def test_offline_chat_routes_to_hardware(self):
        answer, frame = await self.client.chat(
            prompt="Nhiệt độ và độ ẩm phòng hiện tại là bao nhiêu?",
            model_name="gemini/gemini-2.5-flash",
            api_key="",
        )
        self.assertIn("DHT22", answer)
        self.assertIsNone(frame)


class VisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_color_detection_on_synthetic_frame(self):
        vision = AsyncVisionAgent()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[190:290, 270:370] = (255, 0, 0)
        vision._grab_frame = lambda: (frame.copy(), False)

        result, encoded_frame = await vision.detect_colors()

        self.assertEqual(result["detected_color"], "Blue")
        self.assertTrue(encoded_frame)


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

    def test_default_microphone_resolves_to_available_index(self):
        agent = AsyncVoiceAgent()

        with patch.object(agent, "get_default_microphone_index", return_value=7):
            with patch("src.voice.agent.sr.Microphone") as microphone:
                _ = agent.microphone

        microphone.assert_called_once_with(device_index=7)


class CoreTests(unittest.IsolatedAsyncioTestCase):
    def test_pi_ui_mode_is_separate_from_uart_mode(self):
        self.assertIsInstance(config.IS_PI, bool)
        self.assertIsInstance(config.USE_REAL_UART, bool)

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

    async def test_rejects_unknown_provider(self):
        core = AsyncCoreEngine()
        with self.assertRaises(ValueError):
            core.update_llm_settings("unknown", "")


if __name__ == "__main__":
    unittest.main()
