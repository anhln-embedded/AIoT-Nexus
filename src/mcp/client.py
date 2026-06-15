import asyncio
import json
import litellm
from typing import Callable, Optional
from src.mcp.tools.weather import fetch_weather_api

class AsyncMcpClient:
    def __init__(self, hw_controller, vision_agent):
        self.hw = hw_controller
        self.vision = vision_agent
        self.request_id_counter = 0

        # Define tools schema for LiteLLM (OpenAI Tool format)
        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "get_dht_data",
                    "description": "Đọc thông tin nhiệt độ và độ ẩm phòng hiện tại từ cảm biến DHT22 kết nối với STM32.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "detect_faces",
                    "description": "Chụp một bức ảnh từ camera HD và đếm số lượng khuôn mặt/người có mặt.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "detect_colors",
                    "description": "Chụp một bức ảnh từ camera HD và nhận diện màu sắc của vật thể ở trung tâm khung hình.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Truy vấn thời tiết hiện tại của một thành phố cụ thể.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "Tên thành phố cần hỏi thời tiết (ví dụ: 'Hà Nội', 'Đà Nẵng')."
                            }
                        },
                        "required": ["location"]
                    }
                }
            }
        ]

    def _next_id(self) -> int:
        self.request_id_counter += 1
        return self.request_id_counter

    async def _execute_tool_json_rpc(self, method: str, params: dict) -> dict:
        """
        Simulates executing a tool via JSON-RPC 2.0 protocol.
        Wraps the service call in a standard JSON-RPC request and returns response.
        """
        req_id = self._next_id()
        rpc_request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": req_id
        }
        print(f"[MCP RPC TX] Request: {json.dumps(rpc_request)}")

        result = None
        error = None
        try:
            if method == "get_dht_data":
                result = await self.hw.get_dht_data()
            elif method == "detect_faces":
                result, b64_frame = await self.vision.detect_faces()
                result = {
                    "face_count": result["face_count"],
                    "faces": result["faces"],
                    "is_mocked_camera": result["is_mocked_camera"],
                    "_b64_frame": b64_frame
                }
            elif method == "detect_colors":
                result, b64_frame = await self.vision.detect_colors()
                result = {
                    "detected_color": result["detected_color"],
                    "hsv_values": result["hsv_values"],
                    "is_mocked_camera": result["is_mocked_camera"],
                    "_b64_frame": b64_frame
                }
            elif method == "get_weather":
                location = params.get("location", "Hà Nội")
                result = await fetch_weather_api(location)
            else:
                error = {"code": -32601, "message": f"Method '{method}' not found"}
        except Exception as e:
            error = {"code": -32000, "message": f"Execution error: {str(e)}"}

        rpc_response = {
            "jsonrpc": "2.0",
            "id": req_id
        }
        if error:
            rpc_response["error"] = error
        else:
            rpc_response["result"] = result

        print(f"[MCP RPC RX] Response: {json.dumps(rpc_response)}")
        return rpc_response

    async def chat(self, 
                   prompt: str, 
                   model_name: str, 
                   api_key: str, 
                   api_base: Optional[str] = None, 
                   tool_hook: Optional[Callable] = None,
                   log_callback: Optional[Callable] = None) -> tuple[str, Optional[str]]:
        """
        Sends conversational prompt to LiteLLM.
        Detects, simulates execution of tool requests via JSON-RPC 2.0,
        returns synthesized response and optionally the latest base64 image frame.
        """
        messages = [
            {"role": "system", "content": (
                "Bạn là trợ lý AIoT-Nexus thông minh điều khiển thiết bị phần cứng STM32 và camera OpenCV. "
                "Hãy giao tiếp bằng tiếng Việt thân thiện, tự nhiên. "
                "Bạn có quyền truy cập trực tiếp vào phần cứng thông qua các công cụ. "
                "Khi người dùng yêu cầu đo nhiệt độ/độ ẩm, phát hiện mặt, nhận diện màu sắc hoặc hỏi thời tiết, "
                "bạn PHẢI gọi công cụ tương ứng để lấy dữ liệu thực tế thay vì tự đoán."
            )},
            {"role": "user", "content": prompt}
        ]

        last_b64_frame = None
        is_ollama = "ollama" in model_name
        if not api_key and not is_ollama:
            if log_callback:
                await log_callback("Không phát hiện API key. Đang kích hoạt Trình Mô Phỏng Cục Bộ...")
            return await self._mock_llm_chain(prompt, tool_hook, log_callback)

        try:
            if log_callback:
                await log_callback(f"Đang gửi yêu cầu đến LLM ({model_name})...")

            kwargs = {
                "model": model_name,
                "messages": messages,
                "tools": self.tools_schema,
                "tool_choice": "auto",
                "api_key": api_key
            }
            if api_base:
                kwargs["api_base"] = api_base

            response = await litellm.acompletion(**kwargs)

            choice = response.choices[0]
            message = choice.message

            if message.get("tool_calls"):
                tool_calls = message["tool_calls"]
                messages.append(message)
                
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    
                    if log_callback:
                        await log_callback(f"LLM yêu cầu gọi công cụ: {func_name} với đối số: {func_args}")

                    rpc_response = await self._execute_tool_json_rpc(func_name, func_args)
                    
                    result_content = ""
                    if "error" in rpc_response:
                        result_content = json.dumps(rpc_response["error"])
                    else:
                        res = rpc_response["result"]
                        if isinstance(res, dict) and "_b64_frame" in res:
                            last_b64_frame = res.pop("_b64_frame")
                        
                        if last_b64_frame and tool_hook:
                            await tool_hook(func_name, last_b64_frame, res)

                        result_content = json.dumps(res)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": result_content
                    })

                if log_callback:
                    await log_callback("Đang tổng hợp câu trả lời từ dữ liệu công cụ...")
                
                kwargs["messages"] = messages
                kwargs.pop("tools", None)
                kwargs.pop("tool_choice", None)

                response2 = await litellm.acompletion(**kwargs)
                final_text = response2.choices[0].message.content
                return final_text, last_b64_frame

            else:
                return message.content, None

        except Exception as e:
            print(f"LLM Error: {e}")
            if log_callback:
                await log_callback(f"Lỗi LLM: {e}. Đang chuyển sang Trình Mô Phỏng Cục Bộ...")
            return await self._mock_llm_chain(prompt, tool_hook, log_callback)

    async def _mock_llm_chain(self, prompt: str, tool_hook=None, log_callback=None) -> tuple[str, Optional[str]]:
        """Simulates full LLM chain and function calling locally when offline/no-keys."""
        await asyncio.sleep(0.5)
        p_lower = prompt.lower()
        
        last_b64_frame = None
        tool_executed = None
        result_payload = {}
        
        if "nhiệt độ" in p_lower or "độ ẩm" in p_lower or "dht" in p_lower or "cảm biến" in p_lower:
            tool_executed = "get_dht_data"
            rpc_res = await self._execute_tool_json_rpc(tool_executed, {})
            result_payload = rpc_res.get("result", {})
            ans = f"Tôi đã đọc được thông tin phòng từ cảm biến DHT22: Nhiệt độ hiện tại là {result_payload.get('temp')}°C và độ ẩm là {result_payload.get('humidity')}%. Mọi thông số phòng đang trong tầm kiểm soát."
            
        elif "khuôn mặt" in p_lower or "người" in p_lower or "đếm mặt" in p_lower:
            tool_executed = "detect_faces"
            rpc_res = await self._execute_tool_json_rpc(tool_executed, {})
            result_payload = rpc_res.get("result", {})
            last_b64_frame = result_payload.pop("_b64_frame", None)
            
            count = result_payload.get("face_count", 0)
            if count > 0:
                ans = f"Hệ thống thị giác máy tính đã quét qua camera và phát hiện thấy có {count} khuôn mặt xuất hiện trong tầm nhìn."
            else:
                ans = "Tôi đã mở camera quét khu vực phía trước nhưng hiện tại chưa phát hiện thấy khuôn mặt nào cả."
                
        elif "màu sắc" in p_lower or "màu gì" in p_lower or "nhận diện màu" in p_lower:
            tool_executed = "detect_colors"
            rpc_res = await self._execute_tool_json_rpc(tool_executed, {})
            result_payload = rpc_res.get("result", {})
            last_b64_frame = result_payload.pop("_b64_frame", None)
            
            color = result_payload.get("detected_color", "Chưa xác định")
            hsv = result_payload.get("hsv_values", {})
            ans = f"Tôi đã phân tích vùng trung tâm hình ảnh và nhận diện được màu sắc: {color} (Chi tiết HSV: H={hsv.get('h')}, S={hsv.get('s')}, V={hsv.get('v')})."
            
        elif "thời tiết" in p_lower:
            city = "Hà Nội"
            if "hồ chí minh" in p_lower or "sài gòn" in p_lower:
                city = "Hồ Chí Minh"
            elif "đà nẵng" in p_lower:
                city = "Đà Nẵng"
            
            tool_executed = "get_weather"
            rpc_res = await self._execute_tool_json_rpc(tool_executed, {"location": city})
            result_payload = rpc_res.get("result", {})
            ans = f"Thời tiết hôm nay tại {result_payload.get('location')} đang là {result_payload.get('temperature')} với trạng thái {result_payload.get('condition')}, độ ẩm khoảng {result_payload.get('humidity')}."
            
        else:
            ans = "Chào bạn! Tôi là bộ não trung tâm AIoT-Nexus. Tôi có thể giúp bạn đọc cảm biến nhiệt độ phòng, kích hoạt camera nhận diện khuôn mặt, màu sắc hoặc tra cứu thông tin thời tiết. Hãy thử đặt các câu hỏi liên quan nhé!"

        if tool_executed and last_b64_frame and tool_hook:
            await tool_hook(tool_executed, last_b64_frame, result_payload)

        if log_callback:
            await log_callback(f"[Mô Phỏng] Đã xử lý yêu cầu qua công cụ: {tool_executed or 'Trò chuyện chung'}")
            
        return ans, last_b64_frame
