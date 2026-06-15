import asyncio
import random

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
