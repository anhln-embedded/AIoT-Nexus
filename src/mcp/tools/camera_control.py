from typing import Any

from src.mcp.registry import McpTool, McpToolContext, maybe_await


def get_tools(context: McpToolContext) -> list[McpTool]:
    async def set_camera_enabled(params: dict[str, Any]) -> dict[str, Any]:
        enabled = params.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("Field 'enabled' must be a boolean")

        camera_target = context.camera_controller or context.vision
        if hasattr(camera_target, "set_camera_enabled"):
            await maybe_await(camera_target.set_camera_enabled(enabled))
        else:
            await maybe_await(camera_target.set_enabled(enabled))

        current_state = bool(context.vision.is_enabled)
        return {
            "enabled": current_state,
            "status": "on" if current_state else "off",
            "message": f"Camera đã được {'bật' if current_state else 'tắt'}.",
        }

    return [
        McpTool(
            name="set_camera_enabled",
            description="Bật hoặc tắt camera. Dùng khi người dùng yêu cầu mở camera, bật camera, tắt camera hoặc dừng camera.",
            parameters={
                "type": "object",
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "description": "true để bật camera, false để tắt camera.",
                    }
                },
                "required": ["enabled"],
            },
            handler=set_camera_enabled,
        )
    ]
