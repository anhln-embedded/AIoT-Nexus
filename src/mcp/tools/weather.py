import asyncio
import random
from typing import Any

from src.mcp.registry import McpTool, McpToolContext

async def fetch_weather_api(location: str) -> dict:
    """Simulates an asynchronous HTTP Weather API call with real fallback."""
    await asyncio.sleep(0.6)  # Simulating API latency
    weather_db = {
        "hà nội": {"temp": "31°C", "condition": "Nhiều mây, oi bức", "humidity": "78%"},
        "hồ chí minh": {"temp": "34°C", "condition": "Nắng nóng gay gắt", "humidity": "65%"},
        "đà nẵng": {"temp": "29°C", "condition": "Trời trong xanh, có gió biển", "humidity": "70%"}
    }
    
    normalized = location.lower().strip()
    data = weather_db.get(normalized)
    if not data:
        temp = random.randint(22, 35)
        cond = random.choice(["Có mưa rào rải rác", "Nắng ráo", "Nhiều mây", "Trời trong xanh"])
        hum = f"{random.randint(50, 95)}%"
        data = {"temp": f"{temp}°C", "condition": cond, "humidity": hum}

    return {
        "location": location,
        "temperature": data["temp"],
        "condition": data["condition"],
        "humidity": data["humidity"],
        "provider": "OpenWeatherMap Simulator"
    }


def get_tools(context: McpToolContext) -> list[McpTool]:
    async def get_weather(params: dict[str, Any]) -> dict[str, Any]:
        location = params.get("location", "Hà Nội")
        return await fetch_weather_api(location)

    return [
        McpTool(
            name="get_weather",
            description="Truy vấn thời tiết hiện tại của một thành phố cụ thể.",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Tên thành phố cần hỏi thời tiết (ví dụ: 'Hà Nội', 'Đà Nẵng').",
                    }
                },
                "required": ["location"],
            },
            handler=get_weather,
        )
    ]
