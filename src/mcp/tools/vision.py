import asyncio
from typing import Any

from src.mcp.registry import McpTool, McpToolContext, maybe_await


async def _ensure_camera_enabled(vision):
    if not vision.is_enabled:
        await maybe_await(vision.set_enabled(True))
        await asyncio.sleep(0.5)


def get_tools(context: McpToolContext) -> list[McpTool]:
    async def detect_faces(params: dict[str, Any]) -> dict[str, Any]:
        await _ensure_camera_enabled(context.vision)
        result, b64_frame = await context.vision.detect_faces()
        return {
            "face_count": result["face_count"],
            "faces": result["faces"],
            "is_mocked_camera": result["is_mocked_camera"],
            "_b64_frame": b64_frame,
        }

    async def detect_colors(params: dict[str, Any]) -> dict[str, Any]:
        await _ensure_camera_enabled(context.vision)
        result, b64_frame = await context.vision.detect_colors()
        return {
            "detected_color": result["detected_color"],
            "hsv_values": result["hsv_values"],
            "is_mocked_camera": result["is_mocked_camera"],
            "_b64_frame": b64_frame,
        }

    return [
        McpTool(
            name="detect_faces",
            description="Chụp một bức ảnh từ camera HD và đếm số lượng khuôn mặt/người có mặt.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=detect_faces,
        ),
        McpTool(
            name="detect_colors",
            description="Chụp một bức ảnh từ camera HD và nhận diện màu sắc của vật thể ở trung tâm khung hình.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=detect_colors,
        ),
    ]
