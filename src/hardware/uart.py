import asyncio
import json
import random

try:
    import serial_asyncio
except ImportError:
    serial_asyncio = None

class AsyncHardwareController:
    def __init__(self, is_pi: bool = False, port: str = "COM3", baudrate: int = 115200):
        self.is_pi = is_pi
        self.port = port
        self.baudrate = baudrate
        
        self.reader = None
        self.writer = None
        self.is_connected = False
        
        # Virtual Things Cache (Thing Abstraction)
        self.temperature = 25.0
        self.humidity = 60.0
        self.relays = {1: False, 2: False}
        self.led_color = "off"
        self._io_lock = asyncio.Lock()

    async def connect(self, log_callback=None):
        """Initializes the connection. Returns True if successful or mocked."""
        if not self.is_pi:
            self.is_connected = True
            msg = "[UART SIM] Mock serial connection initialized."
            print(msg)
            if log_callback:
                await log_callback(msg)
            return True

        if serial_asyncio is None:
            msg = "[UART ERROR] pyserial-asyncio is not installed!"
            print(msg)
            if log_callback:
                await log_callback(msg)
            return False

        try:
            msg = f"[UART] Connecting to serial {self.port} at {self.baudrate}..."
            print(msg)
            if log_callback:
                await log_callback(msg)

            self.reader, self.writer = await serial_asyncio.open_serial_connection(
                url=self.port, baudrate=self.baudrate
            )
            self.is_connected = True
            msg = f"[UART] Connected to {self.port} successfully."
            print(msg)
            if log_callback:
                await log_callback(msg)
            return True
        except Exception as e:
            self.is_connected = False
            msg = f"[UART CONNECTION ERROR] Could not connect: {e}"
            print(msg)
            if log_callback:
                await log_callback(msg)
            return False

    async def disconnect(self):
        """Disconnects serial port."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.is_connected = False
        self.reader = None
        self.writer = None

    async def _send_receive(self, packet: dict) -> dict:
        """
        Internal dispatcher. Sends a JSON command packet to the serial stream,
        reads the response packet, and updates internal abstraction states.
        """
        if not isinstance(packet, dict) or not packet.get("action"):
            return {"status": "error", "message": "Invalid UART packet"}

        async with self._io_lock:
            return await self._send_receive_locked(packet)

    async def _send_receive_locked(self, packet: dict) -> dict:
        payload = json.dumps(packet, ensure_ascii=False)
        log_traffic = packet.get("action") != "GET_DHT"
        if log_traffic:
            print(f"[UART TX] -> {payload}")

        if not self.is_connected:
            connected = await self.connect()
            if not connected:
                return {"status": "error", "message": "UART port disconnected"}

        if not self.is_pi:
            await asyncio.sleep(0.1)
            action = packet.get("action")

            if action == "GET_DHT":
                self.temperature = round(random.uniform(23.5, 27.8), 1)
                self.humidity = round(random.uniform(50.0, 70.0), 1)
                response = {
                    "status": "ok",
                    "temp": self.temperature,
                    "humidity": self.humidity
                }
            elif action == "SET_RELAY":
                r_id = int(packet.get("relay_id", 1))
                state = bool(packet.get("state", False))
                self.relays[r_id] = state
                response = {
                    "status": "ok",
                    "relay_id": r_id,
                    "state": state
                }
            elif action == "SET_LED":
                color = str(packet.get("color", "off"))
                self.led_color = color
                response = {
                    "status": "ok",
                    "color": color
                }
            else:
                response = {"status": "error", "message": "Unknown action"}

            if log_traffic:
                print(f"[UART RX SIM] <- {json.dumps(response)}")
            return response

        try:
            tx_data = (payload + "\n").encode('utf-8')
            self.writer.write(tx_data)
            await self.writer.drain()

            line_bytes = await asyncio.wait_for(self.reader.readline(), timeout=2.0)
            line_str = line_bytes.decode('utf-8').strip()
            if log_traffic:
                print(f"[UART RX] <- {line_str}")

            response = json.loads(line_str)
            self._update_local_cache(response)
            return response
        except asyncio.TimeoutError:
            print("[UART TIMEOUT] No response from STM32 within 2 seconds.")
            return {"status": "error", "message": "STM32 response timeout"}
        except Exception as e:
            print(f"[UART RX ERROR] {e}")
            self.is_connected = False
            return {"status": "error", "message": f"UART error: {e}"}

    def _update_local_cache(self, response: dict):
        """Parses the STM32 response packet and updates local virtual states."""
        if response.get("status") == "ok":
            if "temp" in response:
                self.temperature = float(response["temp"])
            if "humidity" in response:
                self.humidity = float(response["humidity"])
            if "relay_id" in response:
                r_id = int(response["relay_id"])
                self.relays[r_id] = bool(response.get("state", False))
            if "color" in response:
                self.led_color = str(response["color"])

    async def get_dht_data(self) -> dict:
        """Gets temperature and humidity telemetry."""
        return await self._send_receive({"action": "GET_DHT"})

    async def set_relay(self, relay_id: int, state: bool) -> dict:
        """Sets the state of a specific relay switch."""
        return await self._send_receive({"action": "SET_RELAY", "relay_id": relay_id, "state": state})

    async def set_led(self, color: str) -> dict:
        """Sets the RGB LED status indicator color."""
        return await self._send_receive({"action": "SET_LED", "color": color})
