from pathlib import Path
import runpy


if __name__ == "__main__":
    tool_path = Path(__file__).resolve().parents[1] / "tools" / "xiaozhi_registration_tool.py"
    runpy.run_path(str(tool_path), run_name="__main__")
