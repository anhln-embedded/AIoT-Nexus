import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class McpToolContext:
    hw: Any
    vision: Any
    camera_controller: Any = None
    ui_controller: Any = None


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, McpTool] = {}

    def register(self, tool: McpTool):
        if tool.name in self._tools:
            raise ValueError(f"MCP tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def register_many(self, tools: list[McpTool]):
        for tool in tools:
            self.register(tool)

    def tools_schema(self) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any] | None:
        tool = self._tools.get(name)
        if tool is None:
            return None
        result = tool.handler(params)
        if inspect.isawaitable(result):
            return await result
        return result


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value
