from typing import Any

from src.mcp.registry import McpTool, McpToolContext


def get_tools(context: McpToolContext) -> list[McpTool]:
    async def get_dht_data(params: dict[str, Any]) -> dict[str, Any]:
        return await context.hw.get_dht_data()

    return [
        McpTool(
            name="get_dht_data",
            description="Đọc thông tin nhiệt độ và độ ẩm phòng hiện tại từ cảm biến DHT22 kết nối với STM32.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=get_dht_data,
        )
    ]
