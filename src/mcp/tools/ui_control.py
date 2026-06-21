from typing import Any

from src.mcp.registry import McpTool, McpToolContext, maybe_await


def _controller(context: McpToolContext):
    controller = context.ui_controller or context.camera_controller
    if controller is None:
        raise RuntimeError("UI controller is unavailable")
    return controller


def get_tools(context: McpToolContext) -> list[McpTool]:
    async def set_interface_theme(params: dict[str, Any]) -> dict[str, Any]:
        theme = str(params.get("theme", "")).strip().lower()
        if theme not in {"light", "dark"}:
            raise ValueError("Field 'theme' must be 'light' or 'dark'")
        await maybe_await(_controller(context).set_interface_theme(theme))
        return {"theme": theme, "message": f"Interface theme set to {theme}."}

    async def set_camera_mirror(params: dict[str, Any]) -> dict[str, Any]:
        enabled = params.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("Field 'enabled' must be a boolean")
        await maybe_await(_controller(context).set_camera_mirror(enabled))
        return {
            "enabled": bool(context.vision.is_mirrored),
            "status": "on" if context.vision.is_mirrored else "off",
        }

    async def set_output_volume(params: dict[str, Any]) -> dict[str, Any]:
        volume = params.get("volume")
        if isinstance(volume, bool) or not isinstance(volume, (int, float)):
            raise ValueError("Field 'volume' must be a number from 0 to 100")
        if not 0 <= float(volume) <= 100:
            raise ValueError("Field 'volume' must be between 0 and 100")
        normalized = int(round(float(volume)))
        await maybe_await(_controller(context).set_output_volume(normalized))
        return {"volume": normalized, "message": f"Output volume set to {normalized}%."}

    return [
        McpTool(
            name="set_interface_theme",
            description="Set the application interface theme to light or dark.",
            parameters={
                "type": "object",
                "properties": {
                    "theme": {
                        "type": "string",
                        "enum": ["light", "dark"],
                    }
                },
                "required": ["theme"],
            },
            handler=set_interface_theme,
        ),
        McpTool(
            name="set_camera_mirror",
            description="Enable or disable mirrored camera preview mode.",
            parameters={
                "type": "object",
                "properties": {"enabled": {"type": "boolean"}},
                "required": ["enabled"],
            },
            handler=set_camera_mirror,
        ),
        McpTool(
            name="set_output_volume",
            description="Set assistant output volume as a percentage from 0 to 100.",
            parameters={
                "type": "object",
                "properties": {
                    "volume": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 100,
                    }
                },
                "required": ["volume"],
            },
            handler=set_output_volume,
        ),
    ]
