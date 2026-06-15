import asyncio
import unittest
from unittest.mock import AsyncMock

import numpy as np

from src.core.engine import AsyncCoreEngine
from src.hardware.uart import AsyncHardwareController
from src.mcp.client import AsyncMcpClient
from src.vision.agent import AsyncVisionAgent


class FakeVision:
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


class CoreTests(unittest.IsolatedAsyncioTestCase):
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
