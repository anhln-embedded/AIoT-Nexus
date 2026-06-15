import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from the root directory
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Environment flag: False for Windows simulation, True for Raspberry Pi deployment
IS_PI = _env_bool("AIOT_IS_PI", False)
USE_REAL_UART = _env_bool("AIOT_USE_UART", IS_PI)

# Serial settings
PORT_WIN = os.getenv("AIOT_PORT_WIN", "COM3")
PORT_PI = os.getenv("AIOT_PORT_PI", "/dev/serial0")
BAUDRATE = int(os.getenv("AIOT_BAUDRATE", "115200"))
CAMERA_INDEX = int(os.getenv("AIOT_CAMERA_INDEX", "0"))
TELEMETRY_INTERVAL = float(os.getenv("AIOT_TELEMETRY_INTERVAL", "5.0"))
DISPLAY_WIDTH = int(os.getenv("AIOT_DISPLAY_WIDTH", "1280"))
DISPLAY_HEIGHT = int(os.getenv("AIOT_DISPLAY_HEIGHT", "800"))

# LLM Providers Configuration
LLM_PROVIDERS = {
    "gemini": {
        "model": "gemini/gemini-2.5-flash",
        "api_key": os.getenv("GEMINI_API_KEY", ""),
        "api_base": None
    },
    "openai": {
        "model": "openai/gpt-4o-mini",
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "api_base": None
    },
    "ollama": {
        "model": "ollama/llama3",
        "api_key": "ollama",
        "api_base": "http://localhost:11434"
    }
}

DEFAULT_PROVIDER = "gemini"
