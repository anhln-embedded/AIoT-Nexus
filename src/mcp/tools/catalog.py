from src.mcp.registry import McpToolContext, ToolRegistry
from src.mcp.tools import camera_control, hardware, ui_control, vision, weather


def build_default_registry(hw_controller, vision_agent, camera_controller=None) -> ToolRegistry:
    context = McpToolContext(
        hw=hw_controller,
        vision=vision_agent,
        camera_controller=camera_controller,
        ui_controller=camera_controller,
    )
    registry = ToolRegistry()
    registry.register_many(hardware.get_tools(context))
    registry.register_many(vision.get_tools(context))
    registry.register_many(camera_control.get_tools(context))
    registry.register_many(ui_control.get_tools(context))
    registry.register_many(weather.get_tools(context))
    return registry
