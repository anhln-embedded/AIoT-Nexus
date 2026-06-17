import json
from copy import deepcopy
from typing import Any


JSON_RPC_VERSION = "2.0"


class XiaozhiMcpToolAdapter:
    """Maps AIoT-Nexus tool calls to XiaoZhi MCP JSON-RPC messages."""

    def __init__(self, mcp_client, tool_prefix: str = "self.aiot."):
        self.mcp_client = mcp_client
        self.tool_prefix = tool_prefix

    def list_tools(self) -> list[dict[str, Any]]:
        tools = []
        for tool in self.mcp_client.tools_schema:
            function = tool.get("function", {})
            name = function.get("name", "")
            if not name:
                continue
            tools.append(
                {
                    "name": self._public_tool_name(name),
                    "description": function.get("description", ""),
                    "inputSchema": deepcopy(
                        function.get(
                            "parameters",
                            {"type": "object", "properties": {}, "required": []},
                        )
                    ),
                }
            )
        return tools

    async def handle_payload(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params") or {}

        if method and method.startswith("notifications/"):
            return None

        if payload.get("jsonrpc") != JSON_RPC_VERSION:
            return self._error(request_id, -32600, "Invalid JSON-RPC version")

        if method == "initialize":
            return self._result(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "AIoT-Nexus",
                        "version": "0.1.0",
                    },
                },
            )

        if method == "tools/list":
            return self._result(
                request_id,
                {
                    "tools": self.list_tools(),
                },
            )

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str) or not name:
                return self._error(request_id, -32602, "Missing tool name")
            if not isinstance(arguments, dict):
                return self._error(request_id, -32602, "Tool arguments must be an object")
            return await self._call_tool(request_id, name, arguments)

        return self._error(request_id, -32601, f"Method '{method}' not found")

    async def _call_tool(
        self,
        request_id: Any,
        public_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        local_name = self._local_tool_name(public_name)
        rpc_response = await self.mcp_client._execute_tool_json_rpc(local_name, arguments)
        if "error" in rpc_response:
            error = rpc_response["error"]
            return self._error(
                request_id,
                error.get("code", -32000),
                error.get("message", "Tool execution failed"),
            )

        result = deepcopy(rpc_response.get("result"))
        if isinstance(result, dict):
            result.pop("_b64_frame", None)

        return self._result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False),
                    }
                ],
                "isError": False,
            },
        )

    def _public_tool_name(self, local_name: str) -> str:
        if local_name.startswith("self."):
            return local_name
        return f"{self.tool_prefix}{local_name}"

    def _local_tool_name(self, public_name: str) -> str:
        if public_name.startswith(self.tool_prefix):
            return public_name.removeprefix(self.tool_prefix)
        return public_name

    @staticmethod
    def _result(request_id: Any, result: Any) -> dict[str, Any]:
        return {
            "jsonrpc": JSON_RPC_VERSION,
            "id": request_id,
            "result": result,
        }

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": JSON_RPC_VERSION,
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
