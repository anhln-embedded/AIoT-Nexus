import asyncio
import json
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterable, Awaitable, Callable, Optional

from src.xiaozhi_gateway.audio_player import XiaozhiAudioPlayer
from src.xiaozhi_gateway.mcp_adapter import XiaozhiMcpToolAdapter


LogCallback = Optional[Callable[[str], Awaitable[None]]]


@dataclass
class XiaozhiGatewayConfig:
    url: str = ""
    token: str = ""
    transport: str = "websocket"
    protocol_version: int = 1
    device_id: str = ""
    client_id: str = ""
    mqtt_client_id: str = ""
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_publish_topic: str = ""
    mqtt_subscribe_topic: str = ""
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_frame_duration: int = 20

    def resolved_client_id(self) -> str:
        return self.client_id or self.mqtt_client_id or str(uuid.uuid4())


class XiaozhiGatewayBase:
    def __init__(
        self,
        config: XiaozhiGatewayConfig,
        mcp_adapter: XiaozhiMcpToolAdapter,
        log_callback: LogCallback = None,
    ):
        self.config = config
        self.mcp_adapter = mcp_adapter
        self.log_callback = log_callback
        self.session_id: str | None = None
        self.client_id = config.resolved_client_id()
        self._ready = asyncio.Event()
        self._mcp_initialized = asyncio.Event()
        self._speech_finished = asyncio.Event()
        self._speech_finished.set()
        self.listening_finished_event = asyncio.Event()
        self.last_stt_text = ""
        self._outgoing: asyncio.Queue[dict[str, Any] | bytes | None] = asyncio.Queue()
        self._text_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.speech_state_callback: LogCallback = None
        self.assistant_text_callback: LogCallback = None
        self._logged_binary_audio = False
        self.audio_player = XiaozhiAudioPlayer(
            sample_rate=config.audio_sample_rate,
            channels=config.audio_channels,
            log_callback=log_callback,
        )
        self.plays_remote_audio = self.audio_player.is_available

    async def wait_for_speech_finished(self, timeout: float = 30.0) -> bool:
        try:
            await asyncio.wait_for(self._speech_finished.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            await self._log("Timed out waiting for XiaoZhi TTS stop")
            self._speech_finished.set()
            return False

    def build_hello(self) -> dict[str, Any]:
        return {
            "type": "hello",
            "version": self.config.protocol_version,
            "features": {
                "mcp": True,
                "aec": False,
            },
            "transport": self.config.transport,
            "audio_params": {
                "format": "opus",
                "sample_rate": self.config.audio_sample_rate,
                "channels": self.config.audio_channels,
                "frame_duration": self.config.audio_frame_duration,
            },
        }

    async def handle_json_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        session_id = message.get("session_id")
        if isinstance(session_id, str):
            self.session_id = session_id

        message_type = message.get("type")
        if message_type == "hello":
            audio_params = message.get("audio_params") or {}
            self.audio_player.update_audio_params(
                sample_rate=audio_params.get("sample_rate"),
                channels=audio_params.get("channels"),
            )
            await self._log(f"XiaoZhi audio params: {audio_params}")
            await self._log(f"XiaoZhi hello accepted; session={self.session_id or '-'}")
            self._ready.set()
            return None

        if message_type in {"stt", "llm", "tts", "alert"}:
            await self._handle_text_event(message)
            return None

        if message_type != "mcp":
            await self._log(f"XiaoZhi message ignored: {message_type}")
            return None

        payload = message.get("payload")
        if not isinstance(payload, dict):
            return self._wrap_mcp_payload(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32600,
                        "message": "Missing MCP payload",
                    },
                }
            )

        response_payload = await self.mcp_adapter.handle_payload(payload)
        if payload.get("method") == "initialize":
            self._mcp_initialized.set()
        if response_payload is None:
            return None
        return self._wrap_mcp_payload(response_payload)

    def _wrap_mcp_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = {
            "type": "mcp",
            "payload": payload,
        }
        if self.session_id:
            response["session_id"] = self.session_id
        return response

    async def _log(self, message: str):
        print(message)
        if self.log_callback:
            await self.log_callback(message)

    async def send_text_query(
        self,
        text: str,
        timeout: float = 30.0,
        sentence_idle_timeout: float = 2.0,
        ready_timeout: float = 15.0,
    ) -> str:
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=ready_timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("XiaoZhi gateway is not connected yet") from exc
        try:
            await asyncio.wait_for(self._mcp_initialized.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            await self._log("XiaoZhi MCP initialize was not observed before query; continuing")
        self._drain_text_events()
        self._speech_finished.set()

        await self._outgoing.put(
            {
                "session_id": self.session_id,
                "type": "listen",
                "state": "detect",
                "text": text,
            }
        )

        return await self._collect_text_response(timeout, sentence_idle_timeout)

    async def send_audio_query(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        sample_width: int = 2,
        timeout: float = 30.0,
        sentence_idle_timeout: float = 2.0,
        listen_mode: str = "auto",
    ) -> str:
        async def _single_chunk():
            yield pcm_bytes

        return await self.send_audio_stream_query(
            _single_chunk(),
            sample_rate=sample_rate,
            sample_width=sample_width,
            timeout=timeout,
            sentence_idle_timeout=sentence_idle_timeout,
            listen_mode=listen_mode,
        )

    async def send_audio_stream_query(
        self,
        pcm_frames: AsyncIterable[bytes],
        sample_rate: int = 16000,
        sample_width: int = 2,
        timeout: float = 30.0,
        sentence_idle_timeout: float = 2.0,
        listen_mode: str = "auto",
    ) -> str:
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        try:
            await asyncio.wait_for(self._mcp_initialized.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            await self._log("XiaoZhi MCP initialize was not observed before audio query; continuing")
        self._drain_text_events()
        self._speech_finished.set()
        self.listening_finished_event.clear()
        self.last_stt_text = ""

        encoder = self._create_opus_encoder(sample_rate, sample_width)
        audio_packets_sent = 0
        audio_bytes_sent = 0
        await self._outgoing.put(
            {
                "session_id": self.session_id,
                "type": "listen",
                "state": "start",
                "mode": listen_mode,
            }
        )
        try:
            async for pcm_frame in pcm_frames:
                if not pcm_frame:
                    continue
                packets = self._encode_pcm_chunk_to_opus(
                    encoder, pcm_frame, sample_rate, sample_width
                )
                for packet in packets:
                    wrapped_packet = self._wrap_binary_audio_packet(packet)
                    audio_packets_sent += 1
                    audio_bytes_sent += len(wrapped_packet)
                    await self._outgoing.put(wrapped_packet)
        finally:
            try:
                for packet in self._flush_opus_encoder(encoder):
                    wrapped_packet = self._wrap_binary_audio_packet(packet)
                    audio_packets_sent += 1
                    audio_bytes_sent += len(wrapped_packet)
                    await self._outgoing.put(wrapped_packet)
            finally:
                await self._outgoing.put(
                    {
                        "session_id": self.session_id,
                        "type": "listen",
                        "state": "stop",
                    }
                )
                await self._log_audio_send_summary(audio_packets_sent, audio_bytes_sent)

        return await self._collect_text_response(timeout, sentence_idle_timeout)

    def _wrap_binary_audio_packet(self, packet: bytes) -> bytes:
        version = int(self.config.protocol_version or 1)
        if version == 2:
            timestamp = int(time.monotonic() * 1000) & 0xFFFFFFFF
            return struct.pack("!HHIII", version, 0, 0, timestamp, len(packet)) + packet
        if version == 3:
            return struct.pack("!BBH", 0, 0, len(packet)) + packet
        return packet

    def _unwrap_binary_audio_packet(self, packet: bytes) -> bytes:
        version = int(self.config.protocol_version or 1)
        if version == 2 and len(packet) >= 16:
            _, message_type, _, _, payload_size = struct.unpack("!HHIII", packet[:16])
            if message_type == 0 and len(packet) >= 16 + payload_size:
                return packet[16 : 16 + payload_size]
        if version == 3 and len(packet) >= 4:
            message_type, _, payload_size = struct.unpack("!BBH", packet[:4])
            if message_type == 0 and len(packet) >= 4 + payload_size:
                return packet[4 : 4 + payload_size]
        return packet

    async def _log_audio_send_summary(self, packet_count: int, byte_count: int):
        await self._log(
            "[MIC UPLOAD] Audio sent to XiaoZhi: "
            f"packets={packet_count}, bytes={byte_count}, protocol_version={self.config.protocol_version}"
        )
        if packet_count == 0:
            await self._log("[MIC UPLOAD] No Opus packets were sent")

    def _create_opus_encoder(self, sample_rate: int, sample_width: int):
        import av

        if sample_width != 2:
            raise ValueError("Only 16-bit PCM audio is supported")

        codec = av.CodecContext.create("libopus", "w")
        codec.sample_rate = sample_rate
        codec.layout = "mono"
        codec.format = "s16"
        codec.open()
        return codec

    def _encode_pcm_chunk_to_opus(
        self,
        codec,
        pcm_bytes: bytes,
        sample_rate: int,
        sample_width: int,
    ) -> list[bytes]:
        import av
        import numpy as np

        if sample_width != 2:
            raise ValueError("Only 16-bit PCM audio is supported")

        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        frame_size = int(sample_rate * self.config.audio_frame_duration / 1000)
        if len(samples) < frame_size:
            samples = np.pad(samples, (0, frame_size - len(samples)))
        packets: list[bytes] = []
        for offset in range(0, len(samples), frame_size):
            chunk = samples[offset : offset + frame_size]
            if len(chunk) < frame_size:
                chunk = np.pad(chunk, (0, frame_size - len(chunk)))
            frame = av.AudioFrame.from_ndarray(chunk.reshape(1, -1), format="s16", layout="mono")
            frame.sample_rate = sample_rate
            for packet in codec.encode(frame):
                packets.append(bytes(packet))
        return packets

    def _flush_opus_encoder(self, codec) -> list[bytes]:
        return [bytes(packet) for packet in codec.encode(None)]

    async def _collect_text_response(self, timeout: float, sentence_idle_timeout: float) -> str:
        deadline = time.monotonic() + timeout
        sentence_deadline = None
        stt_text = ""
        tts_started = False
        tts_stopped = False
        response_parts: list[str] = []
        while time.monotonic() < deadline:
            wait_until = min(
                deadline,
                sentence_deadline if sentence_deadline is not None else deadline,
            )
            remaining = wait_until - time.monotonic()
            if remaining <= 0:
                break
            try:
                event = await asyncio.wait_for(self._text_events.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break

            if event["type"] == "stt":
                stt_text = event.get("text", "")
            elif event["type"] == "tts_start":
                tts_started = True
                sentence_deadline = None
            elif event["type"] == "sentence":
                sentence = event.get("text", "")
                if sentence:
                    response_parts.append(sentence)
                    if event.get("source") == "tts":
                        tts_started = True
                        sentence_deadline = None
                    else:
                        sentence_deadline = time.monotonic() + sentence_idle_timeout
            elif event["type"] == "tts_stop" and response_parts:
                tts_stopped = True
                break
            elif event["type"] == "tts_stop":
                tts_stopped = True
                break
            elif event["type"] == "alert":
                alert_text = event.get("text", "")
                if response_parts:
                    break
                if alert_text:
                    return alert_text
            if tts_started:
                sentence_deadline = None

        if response_parts:
            return "".join(response_parts).strip()
        if tts_started or tts_stopped:
            return "XiaoZhi audio response"
        if stt_text:
            return f"XiaoZhi received: {stt_text}"
        raise TimeoutError("XiaoZhi did not return a text response")

    def _encode_pcm_to_opus(
        self,
        pcm_bytes: bytes,
        sample_rate: int,
        sample_width: int,
    ) -> list[bytes]:
        packets: list[bytes] = []
        codec = self._create_opus_encoder(sample_rate, sample_width)
        packets.extend(self._encode_pcm_chunk_to_opus(codec, pcm_bytes, sample_rate, sample_width))
        packets.extend(self._flush_opus_encoder(codec))
        return packets

    async def close(self):
        self.audio_player.close()
        await self._outgoing.put(None)

    async def wait_ready(self, timeout: float = 8.0) -> bool:
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def _handle_text_event(self, message: dict[str, Any]):
        message_type = message.get("type")
        if message_type == "stt":
            text = message.get("text", "")
            self.last_stt_text = text
            self.listening_finished_event.set()
            await self._text_events.put({"type": "stt", "text": text})
            await self._log(f"[USER]: {text}")
        elif message_type == "llm":
            text = message.get("text", "")
            if text:
                await self._text_events.put({"type": "sentence", "text": text})
        elif message_type == "tts":
            state = message.get("state")
            if state == "start":
                self.listening_finished_event.set()
                self._speech_finished.clear()
                await self._notify_speech_state("SPEAKING")
                await self._text_events.put({"type": "tts_start"})
            elif state == "sentence_start":
                text = message.get("text", "")
                self._speech_finished.clear()
                await self._notify_speech_state("SPEAKING")
                await self._text_events.put({"type": "sentence", "text": text, "source": "tts"})
                if text and self.assistant_text_callback:
                    await self.assistant_text_callback(text)
                await self._log(f"[XIAOZHI TRA LOI]: {text}")
            elif state == "stop":
                self._speech_finished.set()
                await self._notify_speech_state("IDLE")
                await self._text_events.put({"type": "tts_stop"})
                await self._log("[XIAOZHI EVENT] TTS stopped")
        elif message_type == "alert":
            status = message.get("status", "Alert")
            text = message.get("message", "")
            alert_text = f"{status}: {text}" if text else str(status)
            await self._text_events.put({"type": "alert", "text": alert_text})
            await self._log(f"XiaoZhi alert: {alert_text}")

    def _drain_text_events(self):
        while True:
            try:
                self._text_events.get_nowait()
            except asyncio.QueueEmpty:
                return

    async def _notify_speech_state(self, state: str):
        if self.speech_state_callback:
            await self.speech_state_callback(state)


class XiaozhiWebSocketGateway(XiaozhiGatewayBase):
    def __init__(
        self,
        config: XiaozhiGatewayConfig,
        mcp_adapter: XiaozhiMcpToolAdapter,
        log_callback: LogCallback = None,
    ):
        super().__init__(config, mcp_adapter, log_callback)
        self.config.transport = "websocket"

    async def run_forever(self):
        if not self.config.url:
            raise ValueError("XiaoZhi WebSocket URL is required")

        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("Install websockets to use XiaozhiWebSocketGateway") from exc

        headers = self._headers()
        async with websockets.connect(
            self.config.url,
            additional_headers=headers,
        ) as websocket:
            await websocket.send(json.dumps(self.build_hello(), ensure_ascii=False))
            await self._log(f"Connected to XiaoZhi WebSocket: {self.config.url}")

            sender_task = asyncio.create_task(self._send_loop(websocket))
            async for raw_message in websocket:
                if isinstance(raw_message, bytes):
                    if not self._logged_binary_audio:
                        await self._log("Playing XiaoZhi audio stream from server")
                        self._logged_binary_audio = True
                    await self.audio_player.play_opus_frame(
                        self._unwrap_binary_audio_packet(raw_message)
                    )
                    continue

                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    await self._log("Ignored malformed XiaoZhi JSON message")
                    continue

                response = await self.handle_json_message(message)
                if response:
                    await websocket.send(json.dumps(response, ensure_ascii=False))
            sender_task.cancel()

    async def _send_loop(self, websocket):
        while True:
            message = await self._outgoing.get()
            if message is None:
                await websocket.close()
                return
            if isinstance(message, bytes):
                await websocket.send(message)
            else:
                await websocket.send(json.dumps(message, ensure_ascii=False))

    def _headers(self) -> dict[str, str]:
        headers = {
            "Protocol-Version": str(self.config.protocol_version),
            "Client-Id": self.client_id,
        }
        if self.config.device_id:
            headers["Device-Id"] = self.config.device_id
        if self.config.token:
            token = self.config.token
            if " " not in token:
                token = f"Bearer {token}"
            headers["Authorization"] = token
        return headers


class XiaozhiMqttGateway(XiaozhiGatewayBase):
    def __init__(
        self,
        config: XiaozhiGatewayConfig,
        mcp_adapter: XiaozhiMcpToolAdapter,
        log_callback: LogCallback = None,
    ):
        super().__init__(config, mcp_adapter, log_callback)
        self.config.transport = "mqtt"
        self._incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def run_forever(self):
        if not self.config.url:
            raise ValueError("XiaoZhi MQTT broker URL is required")
        if not self.config.mqtt_publish_topic or not self.config.mqtt_subscribe_topic:
            raise ValueError("MQTT publish and subscribe topics are required")

        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("Install paho-mqtt to use XiaozhiMqttGateway") from exc

        loop = asyncio.get_running_loop()
        client = mqtt.Client(client_id=self.client_id)
        if self.config.mqtt_username or self.config.mqtt_password:
            client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)

        def on_connect(mqtt_client, userdata, flags, rc):
            del userdata, flags
            if rc == 0:
                mqtt_client.subscribe(self.config.mqtt_subscribe_topic)
                mqtt_client.publish(
                    self.config.mqtt_publish_topic,
                    json.dumps(self.build_hello(), ensure_ascii=False),
                )

        def on_message(mqtt_client, userdata, message):
            del mqtt_client, userdata
            try:
                payload = json.loads(message.payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return
            loop.call_soon_threadsafe(self._incoming.put_nowait, payload)

        client.on_connect = on_connect
        client.on_message = on_message

        host, port = self._parse_mqtt_url()
        client.connect(host, port)
        client.loop_start()
        await self._log(f"Connected to XiaoZhi MQTT broker: {host}:{port}")
        try:
            while True:
                message = await self._incoming.get()
                response = await self.handle_json_message(message)
                if response:
                    client.publish(
                        self.config.mqtt_publish_topic,
                        json.dumps(response, ensure_ascii=False),
                    )
        finally:
            client.loop_stop()
            client.disconnect()

    def _parse_mqtt_url(self) -> tuple[str, int]:
        url = self.config.url.removeprefix("mqtt://").removeprefix("mqtts://")
        host, separator, port = url.partition(":")
        return host, int(port) if separator else 1883
