import asyncio
import json
import random
import re
import inspect
import urllib.error
import urllib.request
import uuid

import flet as ft


OTA_URL = "https://api.tenclass.net/xiaozhi/ota/"
DEFAULT_USER_AGENT = "AIoT-Nexus/0.1.0"
DEFAULT_DEVICE_NAME = "AIoT-Nexus"


def random_locally_administered_mac() -> str:
    first_octet = 0x02
    octets = [first_octet, *[random.randint(0x00, 0xFF) for _ in range(5)]]
    return ":".join(f"{octet:02x}" for octet in octets)


def random_client_id() -> str:
    return str(uuid.uuid4())


def build_ota_payload(device_id: str, client_id: str, device_name: str) -> dict:
    name = device_name.strip() or DEFAULT_DEVICE_NAME
    return {
        "application": {
            "name": name,
            "version": "0.1.0",
        },
        "board": {
            "name": name,
            "type": "aiot-nexus",
        },
        "device": {
            "id": device_id,
            "name": name,
        },
        "client_id": client_id,
    }


def request_xiaozhi_ota(device_id: str, client_id: str, device_name: str) -> dict:
    headers = {
        "Activation-Version": "1",
        "Device-Id": device_id,
        "Client-Id": client_id,
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "vi-VN",
        "Content-Type": "application/json",
    }
    payload = build_ota_payload(device_id, client_id, device_name)
    request = urllib.request.Request(
        OTA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def build_env_block(device_id: str, client_id: str, payload: dict | None = None) -> str:
    websocket = (payload or {}).get("websocket") or {}
    url = websocket.get("url", "wss://api.tenclass.net/xiaozhi/v1/")
    token = websocket.get("token", "test-token")
    return "\n".join(
        [
            "AIOT_XIAOZHI_GATEWAY_ENABLED=true",
            "AIOT_XIAOZHI_TRANSPORT=websocket",
            f"AIOT_XIAOZHI_URL={url}",
            f"AIOT_XIAOZHI_TOKEN={token}",
            f"AIOT_XIAOZHI_DEVICE_ID={device_id}",
            f"AIOT_XIAOZHI_CLIENT_ID={client_id}",
            "AIOT_XIAOZHI_PROTOCOL_VERSION=1",
            "AIOT_XIAOZHI_AUDIO_SAMPLE_RATE=16000",
            "AIOT_XIAOZHI_AUDIO_FRAME_DURATION=20",
        ]
    )


def extract_activation_code(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return ""

    activation = payload.get("activation")
    if isinstance(activation, dict):
        for key in ("code", "otp", "activation_code"):
            value = activation.get(key)
            if value:
                return str(value).strip()

    for key in ("activation_code", "otp", "code"):
        value = payload.get(key)
        if value:
            return str(value).strip()

    return ""


def extract_activation_code_from_text(text: str) -> str:
    match = re.search(r"Mã xác thực:\s*([A-Za-z0-9_-]+)", text)
    if match:
        return match.group(1).strip()

    for line in text.splitlines():
        value = line.strip()
        if re.fullmatch(r"\d{4,8}", value):
            return value

    return ""


def activation_text(payload: dict | None) -> str:
    if not payload:
        return "Chưa lấy mã xác thực."
    activation = payload.get("activation") or {}
    code = extract_activation_code(payload)
    message = activation.get("message", "")
    challenge = activation.get("challenge", "")
    lines = []
    if code:
        lines.append(f"Mã xác thực: {code}")
    if message:
        lines.append(f"Thông báo: {message}")
    if challenge:
        lines.append(f"Challenge: {challenge}")
    return "\n".join(lines) if lines else "Server không trả activation code."


def main(page: ft.Page):
    page.title = "XiaoZhi Registration Tool"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0B0C10"
    page.window.width = 1040
    page.window.height = 720
    page.window.min_width = 1040
    page.window.min_height = 720
    page.padding = 0

    bg_card = "#1F2833"
    bg_panel = "#141B24"
    bg_input = "#0B0C10"
    border_glow = "#45A29E"
    border_soft = "#2E3B48"
    text_neon = "#66FCF1"
    text_main = "#EAFBFA"
    text_muted = "#8EA0A7"
    text_soft = "#C5C6C7"

    current_payload = {"value": None}
    request_state = {"fetching": False}

    def field_style(**kwargs):
        base = {
            "border_color": border_soft,
            "focused_border_color": border_glow,
            "border_radius": 8,
            "bgcolor": bg_input,
            "color": text_main,
            "label_style": ft.TextStyle(color=text_muted, size=11),
            "cursor_color": text_neon,
            "text_size": 12,
            "content_padding": ft.Padding.symmetric(horizontal=12, vertical=10),
        }
        base.update(kwargs)
        return base

    def section(title: str, icon, content, expand: bool = False):
        return ft.Container(
            expand=expand,
            bgcolor=bg_card,
            border=ft.Border.all(1, border_glow),
            border_radius=8,
            padding=16,
            content=ft.Column(
                expand=expand,
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(icon, color=text_neon, size=18),
                            ft.Text(title, size=12, color=text_soft, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    content,
                ],
            ),
        )

    device_input = ft.TextField(
        label="AIOT_XIAOZHI_DEVICE_ID",
        value=random_locally_administered_mac(),
        dense=True,
        **field_style(width=300),
    )
    device_name_input = ft.TextField(
        label="Tên thiết bị khi đăng ký",
        value=DEFAULT_DEVICE_NAME,
        dense=True,
        **field_style(),
    )
    client_input = ft.TextField(
        label="AIOT_XIAOZHI_CLIENT_ID",
        value=random_client_id(),
        expand=True,
        dense=True,
        **field_style(),
    )
    status_text = ft.Text("Sẵn sàng tạo thông số đăng ký.", color=text_muted, size=12)
    activation_box = ft.TextField(
        label="Mã xác thực từ xiaozhi",
        value=activation_text(None),
        multiline=True,
        read_only=True,
        **field_style(min_lines=5, max_lines=5),
    )
    env_box = ft.TextField(
        label=".env block",
        value=build_env_block(device_input.value, client_input.value),
        expand=True,
        multiline=True,
        read_only=True,
        **field_style(min_lines=10, max_lines=10, width=None),
    )
    raw_box = ft.TextField(
        label="Raw OTA response",
        value="",
        expand=True,
        multiline=True,
        read_only=True,
        **field_style(min_lines=13, max_lines=13, width=None),
    )

    def set_fetching(is_fetching: bool):
        request_state["fetching"] = is_fetching
        fetch_button.disabled = is_fetching
        fetch_button.text = "Đang lấy mã..." if is_fetching else "Lấy mã xác thực"
        fetch_button.icon = ft.Icons.HOURGLASS_TOP if is_fetching else ft.Icons.VERIFIED_USER
        loading_block.visible = is_fetching

    def refresh_env():
        env_box.value = build_env_block(
            device_input.value.strip(),
            client_input.value.strip(),
            current_payload["value"],
        )

    def randomize(_=None):
        current_payload["value"] = None
        device_input.value = random_locally_administered_mac()
        client_input.value = random_client_id()
        activation_box.value = activation_text(None)
        raw_box.value = ""
        refresh_env()
        status_text.value = "Đã tạo Device-Id và Client-Id ngẫu nhiên."
        page.update()

    async def fetch_activation(_=None):
        if request_state["fetching"]:
            return
        device_id = device_input.value.strip()
        client_id = client_input.value.strip()
        device_name = device_name_input.value.strip() or DEFAULT_DEVICE_NAME
        set_fetching(True)
        status_text.value = "Đang gọi OTA endpoint chính thức..."
        page.update()

        try:
            payload = await asyncio.to_thread(
                request_xiaozhi_ota,
                device_id,
                client_id,
                device_name,
            )
            current_payload["value"] = payload
            activation_box.value = activation_text(payload)
            raw_box.value = json.dumps(
                {
                    "request": build_ota_payload(device_id, client_id, device_name),
                    "response": payload,
                },
                ensure_ascii=False,
                indent=2,
            )
            refresh_env()
            status_text.value = "Đã lấy mã xác thực. Vào xiaozhi.me và nhập mã để active."
        except Exception as exc:
            status_text.value = f"Lỗi: {exc}"
        finally:
            set_fetching(False)
            page.update()

    async def copy_to_clipboard(text: str):
        clipboard = getattr(page, "clipboard", None)
        if clipboard and hasattr(clipboard, "set"):
            await clipboard.set(text)
            return
        if clipboard and hasattr(clipboard, "set_text"):
            result = clipboard.set_text(text)
            if inspect.isawaitable(result):
                await result
            return
        if hasattr(page, "set_clipboard"):
            result = page.set_clipboard(text)
            if inspect.isawaitable(result):
                await result
            return
        raise RuntimeError("Flet clipboard API is not available")

    async def copy_code(_=None):
        payload = current_payload["value"] or {}
        code = extract_activation_code(payload) or extract_activation_code_from_text(activation_box.value)
        if code:
            try:
                await copy_to_clipboard(code)
                status_text.value = f"Đã copy mã xác thực {code}."
            except Exception as exc:
                status_text.value = f"Lỗi copy clipboard: {exc}"
        else:
            status_text.value = "Chưa có mã xác thực để copy."
        page.update()

    random_button = ft.FilledButton(
        "Tạo ngẫu nhiên",
        icon=ft.Icons.SHUFFLE,
        on_click=randomize,
        style=ft.ButtonStyle(
            bgcolor=text_neon,
            color="#0B0C10",
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )
    fetch_button = ft.FilledButton(
        "Lấy mã xác thực",
        icon=ft.Icons.VERIFIED_USER,
        on_click=fetch_activation,
        style=ft.ButtonStyle(
            bgcolor=text_neon,
            color="#0B0C10",
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )
    loading_block = ft.Container(
        visible=False,
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        border_radius=8,
        bgcolor="#182533",
        border=ft.Border.all(1, border_glow),
        content=ft.Row(
            controls=[
                ft.ProgressRing(width=18, height=18, stroke_width=2, color=text_neon),
                ft.Text("Đang chờ server...", size=11, color=text_soft, weight=ft.FontWeight.BOLD),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    device_input.on_change = lambda _: (refresh_env(), page.update())
    client_input.on_change = lambda _: (refresh_env(), page.update())

    page.add(
        ft.Container(
            expand=True,
            bgcolor="#0B0C10",
            padding=18,
            content=ft.Column(
                expand=True,
                spacing=14,
                controls=[
                    ft.Container(
                        bgcolor=bg_card,
                        border=ft.Border.all(1, border_glow),
                        border_radius=8,
                        padding=ft.Padding.symmetric(horizontal=18, vertical=14),
                        content=ft.Row(
                            controls=[
                                ft.Container(
                                    width=54,
                                    height=54,
                                    shape=ft.BoxShape.CIRCLE,
                                    bgcolor="#182533",
                                    border=ft.Border.all(2, text_neon),
                                    content=ft.Icon(ft.Icons.HUB, color=text_neon, size=28),
                                    alignment=ft.Alignment.CENTER,
                                    shadow=ft.BoxShadow(
                                        spread_radius=2,
                                        blur_radius=18,
                                        color=ft.Colors.with_opacity(0.34, text_neon),
                                        blur_style=ft.BlurStyle.OUTER,
                                    ),
                                ),
                                ft.Column(
                                    expand=True,
                                    spacing=3,
                                    controls=[
                                        ft.Text("XiaoZhi Registration Tool", size=22, color=text_neon, weight=ft.FontWeight.BOLD),
                                        ft.Text(
                                            "Tạo Device-Id/Client-Id, lấy mã xác thực OTA và xuất cấu hình .env cho AIoT-Nexus.",
                                            color=text_soft,
                                            size=12,
                                        ),
                                    ],
                                ),
                                ft.Container(
                                    padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                                    border_radius=8,
                                    bgcolor=ft.Colors.with_opacity(0.42, "#0B0C10"),
                                    border=ft.Border.all(1, border_glow),
                                    content=ft.Row(
                                        controls=[
                                            ft.Icon(ft.Icons.LAN, color=text_neon, size=16),
                                            ft.Text("Ngoc Einstein", color=text_soft, size=11, weight=ft.FontWeight.BOLD),
                                        ],
                                        spacing=7,
                                    ),
                                ),
                            ],
                            spacing=14,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ),
                    ft.Row(
                        expand=True,
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Column(
                                width=410,
                                spacing=14,
                                controls=[
                                    section(
                                        "THÔNG SỐ THIẾT BỊ",
                                        ft.Icons.DEVELOPER_BOARD,
                                        ft.Column(
                                            spacing=12,
                                            controls=[
                                                device_name_input,
                                                device_input,
                                                client_input,
                                                ft.Row(
                                                    controls=[
                                                        random_button,
                                                        fetch_button,
                                                        loading_block,
                                                    ],
                                                    spacing=10,
                                                    wrap=True,
                                                ),
                                            ],
                                        ),
                                    ),
                                    section(
                                        "MÃ XÁC THỰC",
                                        ft.Icons.PASSWORD,
                                        ft.Column(
                                            spacing=12,
                                            controls=[
                                                activation_box,
                                                ft.Row(
                                                    controls=[
                                                        ft.OutlinedButton(
                                                            "Copy mã",
                                                            icon=ft.Icons.KEY,
                                                            on_click=copy_code,
                                                            style=ft.ButtonStyle(
                                                                color=text_neon,
                                                                side=ft.BorderSide(1, border_glow),
                                                                shape=ft.RoundedRectangleBorder(radius=8),
                                                            ),
                                                        ),
                                                    ],
                                                    spacing=10,
                                                ),
                                            ],
                                        ),
                                    ),
                                    ft.Container(
                                        bgcolor=bg_panel,
                                        border=ft.Border.all(1, border_soft),
                                        border_radius=8,
                                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                                        content=ft.Row(
                                            controls=[
                                                ft.Icon(ft.Icons.INFO_OUTLINE, color=text_muted, size=16),
                                                status_text,
                                            ],
                                            spacing=8,
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        ),
                                    ),
                                ],
                            ),
                            ft.Column(
                                expand=True,
                                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                                spacing=14,
                                controls=[
                                    ft.Container(
                                        expand=True,
                                        content=section("BLOCK .ENV", ft.Icons.SETTINGS, env_box),
                                    ),
                                    ft.Container(
                                        expand=True,
                                        content=section("PHẢN HỒI OTA", ft.Icons.DATA_OBJECT, raw_box, expand=True),
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )
    )


if __name__ == "__main__":
    ft.run(main)
