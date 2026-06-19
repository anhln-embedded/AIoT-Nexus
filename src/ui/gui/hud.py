import asyncio
import os
import time
import flet as ft
from src.core.engine import AsyncCoreEngine
from src.core.config import (
    DEFAULT_PROVIDER,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    IS_PI,
    LLM_PROVIDERS,
)

CAMERA_PREVIEW_FPS = float(os.getenv("AIOT_CAMERA_PREVIEW_FPS", "24"))


class FletImageWidgetWrapper:
    def __init__(self, real_image_widget):
        self._real_widget = real_image_widget
        self._src_base64 = ""

    @property
    def src_base64(self):
        return self._src_base64

    @src_base64.setter
    def src_base64(self, val):
        self._src_base64 = val
        try:
            self._real_widget.src = val
        except Exception as e:
            print(f"Error updating image base64 in wrapper: {e}")


class CameraViewWrapper:
    def __init__(self, widget, fps_text=None):
        self.widget = FletImageWidgetWrapper(widget)
        self.fps_text = fps_text
        self._frame_count = 0
        self._last_time = time.time()

    def update(self):
        # Update the image widget directly
        self.widget._real_widget.update()
        
        # Also update the FPS text if it's there
        self._frame_count += 1
        current_time = time.time()
        elapsed = current_time - self._last_time
        if elapsed >= 1.0:
            fps = self._frame_count / elapsed
            if self.fps_text:
                try:
                    self.fps_text.value = f"FPS: {fps:.1f}"
                    self.fps_text.update()
                except Exception:
                    pass
            self._frame_count = 0
            self._last_time = current_time




def configure_window(
    page: ft.Page,
    is_pi: bool = IS_PI,
    width: int = DISPLAY_WIDTH,
    height: int = DISPLAY_HEIGHT,
) -> None:
    """Configures a kiosk window on Raspberry Pi and a dev window elsewhere."""
    if is_pi:
        page.padding = 0
        page.window.full_screen = True
        page.window.frameless = True
        page.window.maximized = True
        page.window.resizable = False
        page.window.maximizable = False
        return

    page.padding = 0
    page.window.width = width
    page.window.height = height
    page.window.min_width = width
    page.window.min_height = height
    page.window.max_width = width
    page.window.max_height = height
    page.window.resizable = False
    page.window.maximizable = False

async def main_hud(page: ft.Page):
    # Setup Page Metadata
    page.title = "AIoT-Nexus"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0B0C10"
    configure_window(page)
    
    # Initialize Core Application Engine
    core = AsyncCoreEngine()
    
    # Detect available cameras dynamically from hardware
    available_cameras = await core.get_available_cameras()
    available_microphones = await core.get_available_microphones()
    
    # --- Custom Styling Tokens ---
    BG_CARD = "#1F2833"
    BORDER_GLOW = "#45A29E"
    TEXT_NEON = "#66FCF1"
    
    # --- Left Panel UI Components (Glowing Status Eye) ---
    brand_logo = ft.Image(
        src="assets/logo/PTIT_logo_transparent.png",
        width=42,
        height=52,
        fit=getattr(ft, "ImageFit", ft.BoxFit).CONTAIN,
        gapless_playback=True,
    )

    brand_header = ft.Container(
        width=292,
        height=58,
        alignment=ft.Alignment.CENTER,
        content=ft.Row(
            controls=[
                brand_logo,
                ft.Column(
                    controls=[
                        ft.Text(
                            "HỌC VIỆN CÔNG NGHỆ BƯU CHÍNH VIỄN THÔNG",
                            size=8.2,
                            color="#E5252A",
                            weight=ft.FontWeight.BOLD,
                            no_wrap=True,
                        ),
                        ft.Text(
                            "Posts and Telecommunications Institute of Technology",
                            size=6.7,
                            color="#E8EEF2",
                            weight=ft.FontWeight.BOLD,
                            no_wrap=True,
                        ),
                    ],
                    spacing=1,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                    width=218,
                ),
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    state_icon = ft.Icon(ft.Icons.MIC, size=64, color="#66FCF1")
    
    # Glowing Indicator Container
    glow_indicator = ft.Container(
        width=164,
        height=164,
        shape=ft.BoxShape.CIRCLE,
        bgcolor="#182533",
        border=ft.Border.all(4, "#66FCF1"),
        shadow=ft.BoxShadow(
            spread_radius=12,
            blur_radius=26,
            color=ft.Colors.with_opacity(0.48, "#66FCF1"),
            blur_style=ft.BlurStyle.OUTER,
        ),
        content=state_icon,
        alignment=ft.Alignment.CENTER,
        animate=ft.Animation(300, ft.AnimationCurve.DECELERATE),
    )
    
    status_label = ft.Text(
        "Khởi động hệ thống...",
        size=19,
        color="#66FCF1",
        weight=ft.FontWeight.BOLD
    )
    status_badge = ft.Container(
        padding=ft.Padding.symmetric(horizontal=16, vertical=6),
        border_radius=8,
        bgcolor=ft.Colors.with_opacity(0.42, "#0B0C10"),
        border=ft.Border.all(1, "#45A29E"),
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=10,
            color=ft.Colors.with_opacity(0.22, "#66FCF1"),
            blur_style=ft.BlurStyle.OUTER,
        ),
        content=status_label,
    )
    status_gap = ft.Container(height=10)
    
    # Pulsing task for animation loop
    async def pulse_indicator():
        while core.is_running:
            if core.state == "LISTENING":
                glow_indicator.scale = 1.1
                glow_indicator.shadow.spread_radius = 16
                glow_indicator.shadow.blur_radius = 30
                glow_indicator.shadow.color = ft.Colors.with_opacity(0.78, "#00FF00")
            elif core.state == "SPEAKING":
                glow_indicator.scale = 1.05 if glow_indicator.scale == 1.0 else 1.0
                glow_indicator.shadow.spread_radius = 14
                glow_indicator.shadow.blur_radius = 28
                glow_indicator.shadow.color = ft.Colors.with_opacity(0.68, "#9900FF")
            elif core.state == "PROCESSING":
                glow_indicator.scale = 1.0
                glow_indicator.shadow.spread_radius = 9 if glow_indicator.shadow.spread_radius == 16 else 16
                glow_indicator.shadow.blur_radius = 28
                glow_indicator.shadow.color = ft.Colors.with_opacity(0.68, "#FFBF00")
            else:
                glow_indicator.scale = 1.0
                glow_indicator.shadow.spread_radius = 10
                glow_indicator.shadow.blur_radius = 24
                glow_indicator.shadow.color = ft.Colors.with_opacity(0.5, "#66FCF1")
                
            try:
                glow_indicator.update()
            except Exception:
                pass
            await asyncio.sleep(0.5)

    # --- Right Panel UI Components (Dashboard & Telemetry) ---
    temp_text = ft.Text("25.0 °C", size=24, color="#66FCF1", weight=ft.FontWeight.BOLD)
    hum_text = ft.Text("60.0 %", size=24, color="#66FCF1", weight=ft.FontWeight.BOLD)
    
    temp_card = ft.Card(
        bgcolor=BG_CARD,
        content=ft.Container(
            padding=10,
            width=130,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("NHIỆT ĐỘ", size=10, color="#C5C6C7", weight=ft.FontWeight.BOLD),
                    ft.Row([ft.Icon(ft.Icons.THERMOSTAT, color="#FF5555"), temp_text], alignment=ft.MainAxisAlignment.CENTER, spacing=5)
                ]
            )
        )
    )
    
    hum_card = ft.Card(
        bgcolor=BG_CARD,
        content=ft.Container(
            padding=10,
            width=130,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("ĐỘ ẨM PHÒNG", size=10, color="#C5C6C7", weight=ft.FontWeight.BOLD),
                    ft.Row([ft.Icon(ft.Icons.WATER_DROP, color="#55AAFF"), hum_text], alignment=ft.MainAxisAlignment.CENTER, spacing=5)
                ]
            )
        )
    )

    # OpenCV Camera Vision Overlay Panel
    camera_placeholder_icon = ft.Icon(ft.Icons.VIDEOCAM_OFF, size=45, color="#C5C6C7")
    camera_placeholder_text = ft.Text("CAMERA STANDBY", size=14, color="#C5C6C7", weight=ft.FontWeight.BOLD)

    camera_placeholder = ft.Container(
        width=640,
        height=360,
        bgcolor="#0B0C10",
        border=ft.Border.all(2, "#45A29E"),
        border_radius=8,
        alignment=ft.Alignment.CENTER,
        visible=not core.vision.is_enabled,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                camera_placeholder_icon,
                camera_placeholder_text
            ]
        )
    )
    
    camera_feed = ft.Image(
        src="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
        width=640,
        height=360,
        fit=getattr(ft, "ImageFit", ft.BoxFit).CONTAIN,
        gapless_playback=True,
        visible=core.vision.is_enabled
    )
    
    fps_text = ft.Text("FPS: 0.0", size=10, color="#66FCF1", weight=ft.FontWeight.BOLD)
    fps_container = ft.Container(
        content=fps_text,
        bgcolor=ft.Colors.with_opacity(0.6, "#0B0C10"),
        padding=4,
        border_radius=4,
        left=10,
        top=10,
        visible=core.vision.is_enabled
    )
    
    camera_panel = ft.Container(
        width=640,
        height=360,
        alignment=ft.Alignment.CENTER,
        content=ft.Stack(
            [camera_placeholder, camera_feed, fps_container],
            alignment=ft.Alignment.CENTER,
        ),
    )
    camera_panel_shell = ft.Container(
        content=camera_panel,
        width=640,
        height=360 if core.vision.is_enabled else 0,
        alignment=ft.Alignment.TOP_CENTER,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        opacity=1.0 if core.vision.is_enabled else 0.0,
        offset=(0, 0) if core.vision.is_enabled else (0, -0.06),
        ignore_interactions=not core.vision.is_enabled,
        animate_size=ft.Animation(420, ft.AnimationCurve.EASE_IN_OUT_CUBIC),
        animate_opacity=ft.Animation(260, ft.AnimationCurve.EASE_IN_OUT),
        animate_offset=ft.Animation(420, ft.AnimationCurve.EASE_IN_OUT_CUBIC),
    )

    camera_view = CameraViewWrapper(camera_feed, fps_text)
    core.vision.camera_view = camera_view
    camera_requested_state = {"enabled": core.vision.is_enabled}


    camera_title_text = ft.Text("THIẾT LẬP CAMERA:", size=11, color="#C5C6C7", weight=ft.FontWeight.BOLD)
    camera_source_text = ft.Text("Nguồn:", size=11, color="#C5C6C7")

    # Camera selection and toggle controls
    async def on_camera_change(e):
        try:
            val = camera_dropdown.value
            idx = val.split()[-1] if val else "0"
            await core.update_camera_index(int(idx))
            if not camera_switch.value:
                camera_placeholder_text.value = f"CAMERA DISABLED (Camera {idx})"
            else:
                camera_placeholder_text.value = f"CAMERA STANDBY (Camera {idx})"
            page.update()
        except Exception as ex:
            print(f"Error updating camera index: {ex}")

    async def on_camera_switch_change(e):
        try:
            enabled = camera_switch.value
            camera_requested_state["enabled"] = enabled
            apply_camera_layout(enabled)
            camera_switch.update()
            camera_panel_shell.update()
            camera_feed.update()
            fps_container.update()
            page.update()
            await core.set_camera_enabled(enabled)
        except Exception as ex:
            print(f"Error toggling camera enabled state: {ex}")

    def on_camera_mirror_change(e):
        try:
            core.vision.is_mirrored = bool(camera_mirror_switch.value)
            page.update()
        except Exception as ex:
            print(f"Error updating camera mirror mode: {ex}")

    camera_dropdown = ft.Dropdown(
        options=[
            ft.dropdown.Option(f"Camera {idx}")
            for idx in available_cameras
        ],
        value=f"Camera {core.vision.camera_index}" if core.vision.camera_index in available_cameras else f"Camera {available_cameras[0]}",
        width=110,
        height=48,
        text_size=12,
        color="#66FCF1",
        border_color="#45A29E",
        focused_border_color="#66FCF1",
    )
    camera_dropdown.on_change = on_camera_change

    camera_mirror_switch = ft.Switch(
        label="SOI GƯƠNG",
        value=core.vision.is_mirrored,
        active_color="#66FCF1",
    )
    camera_mirror_switch.on_change = on_camera_mirror_change


    camera_switch = ft.Switch(
        label="TẮT CAMERA" if core.vision.is_enabled else "BẬT CAMERA",
        value=core.vision.is_enabled,
        active_color="#66FCF1",
    )
    camera_switch.on_change = on_camera_switch_change

    camera_controls = ft.Container(
        content=ft.Row(
            controls=[
                ft.Row([
                    ft.Icon(ft.Icons.VIDEOCAM, color="#66FCF1", size=18),
                    camera_title_text,
                ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    camera_source_text,
                    camera_dropdown,
                ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                camera_mirror_switch,
                camera_switch,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        width=640,
        bgcolor="#1F2833",
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=15, vertical=8),
        border=ft.Border.all(1, "#45A29E"),
    )

    # Initialize dynamic titles based on initial selection
    val = camera_dropdown.value
    initial_idx = val.split()[-1] if val else "0"
    camera_placeholder_text.value = f"CAMERA STANDBY (Camera {initial_idx})"

    def apply_camera_layout(enabled: bool):
        val = camera_dropdown.value
        idx = val.split()[-1] if val else "0"
        camera_panel_shell.height = 360 if enabled else 0
        camera_panel_shell.opacity = 1.0 if enabled else 0.0
        camera_panel_shell.offset = (0, 0) if enabled else (0, -0.06)
        camera_panel_shell.ignore_interactions = not enabled
        camera_feed.visible = enabled
        fps_container.visible = enabled
        camera_placeholder.visible = False
        camera_switch.value = enabled
        camera_switch.label = "TẮT CAMERA" if enabled else "BẬT CAMERA"
        if enabled:
            camera_placeholder_text.value = f"CAMERA STANDBY (Camera {idx})"
            camera_placeholder_text.color = "#C5C6C7"
            camera_placeholder_icon.color = "#C5C6C7"
        else:
            camera_placeholder_text.value = f"CAMERA DISABLED (Camera {idx})"
            camera_placeholder_text.color = "#FF5555"
            camera_placeholder_icon.color = "#FF5555"

    apply_camera_layout(core.vision.is_enabled)

    # Conversation and system event panel
    chat_list = ft.ListView(
        expand=True,
        spacing=8,
        auto_scroll=True
    )
    
    chat_panel = ft.Container(
        expand=True,
        bgcolor="#0B0C10",
        border=ft.Border.all(1, "#1F2833"),
        border_radius=5,
        padding=10,
        content=chat_list
    )

    xiaozhi_chat_state = {
        "last_stt": "",
        "assistant_parts": [],
        "active_assistant_text": None,
        "active_assistant_message": "",
    }

    def append_log(message: str):
        # Surface only XiaoZhi conversation events in the chat panel.
        # Technical logs still go to the terminal via print statements.
        if message.startswith("[USER]: "):
            stt_text = message.removeprefix("[USER]: ").strip()
            if stt_text:
                xiaozhi_chat_state["last_stt"] = stt_text
                xiaozhi_chat_state["assistant_parts"].clear()
                xiaozhi_chat_state["active_assistant_text"] = None
                xiaozhi_chat_state["active_assistant_message"] = ""
                append_chat_message("user", stt_text, from_xiaozhi_stream=True)
            return

        # Assistant text uses a dedicated acknowledged UI event so the
        # corresponding audio cannot start before the bubble is rendered.

    def append_xiaozhi_assistant_part(message: str):
        xiaozhi_chat_state["assistant_parts"].append(message)
        current_message = xiaozhi_chat_state["active_assistant_message"]
        next_message = f"{current_message} {message}".strip() if current_message else message

        active_text = xiaozhi_chat_state["active_assistant_text"]
        if active_text is None:
            active_text = append_chat_message("assistant", next_message, from_xiaozhi_stream=True)
            xiaozhi_chat_state["active_assistant_text"] = active_text
        else:
            active_text.value = next_message
            page.update()

        xiaozhi_chat_state["active_assistant_message"] = next_message

    def append_chat_message(role: str, message: str, from_xiaozhi_stream: bool = False):
        if role == "user" and message == "Âm thanh từ micro" and xiaozhi_chat_state["last_stt"]:
            return
        if role == "assistant" and xiaozhi_chat_state["assistant_parts"] and not from_xiaozhi_stream:
            xiaozhi_chat_state["assistant_parts"].clear()
            xiaozhi_chat_state["active_assistant_text"] = None
            xiaozhi_chat_state["active_assistant_message"] = ""
            return

        is_user = role == "user"
        bubble_color = "#14313A" if is_user else "#18212B"
        border_color = "#45A29E" if is_user else "#2E3B48"
        text_color = "#EAFBFA" if is_user else "#D7E1E5"
        label = "Bạn" if is_user else ("XiaoZhi" if from_xiaozhi_stream else "AIoT-Nexus")
        alignment = ft.Alignment.CENTER_RIGHT if is_user else ft.Alignment.CENTER_LEFT
        message_text = ft.Text(message, size=12, color=text_color, selectable=True)

        chat_list.controls.append(
            ft.Container(
                alignment=alignment,
                content=ft.Container(
                    width=430,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                    border_radius=8,
                    bgcolor=bubble_color,
                    border=ft.Border.all(1, border_color),
                    content=ft.Column(
                        spacing=4,
                        controls=[
                            ft.Text(label, size=9, color="#66FCF1" if is_user else "#8EA0A7", weight=ft.FontWeight.BOLD),
                            message_text,
                        ],
                    ),
                ),
            )
        )
        page.update()
        return message_text

    async def on_trigger_click(e):
        asyncio.create_task(core.trigger_voice_interaction())

    async def submit_chat_text(e=None):
        text = chat_input.value.strip()
        if not text:
            return

        chat_state["waiting"] = True
        chat_input.value = ""
        chat_input.update()
        update_chat_send_button()
        asyncio.create_task(core.trigger_text_interaction(text))

    glow_indicator.on_click = on_trigger_click
    glow_indicator.tooltip = "Nhấn để thực thi lệnh thoại"

    microphone_options = [ft.dropdown.Option("Mặc định hệ thống")]
    microphone_options.extend(
        ft.dropdown.Option(f"Mic {index}: {name[:34]}")
        for index, name in available_microphones
    )

    async def on_microphone_change(e):
        try:
            value = microphone_dropdown.value or "Mặc định hệ thống"
            if value == "Mặc định hệ thống":
                await core.update_microphone_index(None)
                return

            index = int(value.split(":", 1)[0].split()[-1])
            await core.update_microphone_index(index)
        except Exception as ex:
            print(f"Error updating microphone index: {ex}")

    microphone_dropdown = ft.Dropdown(
        options=microphone_options,
        value="Mặc định hệ thống",
        width=172,
        height=44,
        text_size=9,
        color="#C5C6C7",
        border_color="#2E3B48",
        border_radius=5,
        content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        dense=True,
        focused_border_color="#45A29E",
    )
    microphone_dropdown.on_change = on_microphone_change

    microphone_controls = ft.Container(
        width=204,
        padding=ft.Padding.symmetric(horizontal=8, vertical=7),
        border_radius=8,
        bgcolor="#141B24",
        border=ft.Border.all(1, "#24303C"),
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            spacing=3,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.MIC_EXTERNAL_ON, color="#6F858C", size=12),
                        ft.Text("MIC INPUT", size=7, color="#6F858C", weight=ft.FontWeight.BOLD),
                    ],
                    spacing=5,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                microphone_dropdown,
            ],
        ),
    )

    microphone_gap = ft.Container(height=12)
    chat_state = {"waiting": False}

    chat_input = ft.TextField(
        hint_text="Hỏi bất kỳ điều gì",
        width=360,
        height=28,
        text_size=13,
        text_vertical_align=0.0,
        color="#EAFBFA",
        bgcolor="transparent",
        border=ft.InputBorder.NONE,
        focused_border_color="transparent",
        focused_bgcolor="transparent",
        hover_color="transparent",
        focus_color="transparent",
        cursor_color="#66FCF1",
        content_padding=0,
        dense=True,
        collapsed=True,
    )

    chat_input_shell = ft.Container(
        expand=True,
        height=34,
        padding=ft.Padding.symmetric(horizontal=8, vertical=0),
        bgcolor="transparent",
        alignment=ft.Alignment.CENTER_LEFT,
        content=chat_input,
    )

    chat_add_button = ft.IconButton(
        icon=ft.Icons.ADD_ROUNDED,
        icon_color="#8EA0A7",
        icon_size=24,
        tooltip="Tùy chọn thêm",
        width=34,
        height=34,
        padding=0,
    )

    chat_mode_label = ft.Row(
        controls=[
            ft.Text("Tức thì", size=12, color="#8EA0A7"),
            ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED, size=16, color="#8EA0A7"),
        ],
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    chat_voice_button = ft.IconButton(
        icon=ft.Icons.MIC_ROUNDED,
        icon_color="#A9C6C8",
        icon_size=20,
        tooltip="Nhấn để nói",
        width=34,
        height=34,
        padding=0,
        on_click=on_trigger_click,
    )

    chat_send_button = ft.IconButton(
        icon=ft.Icons.GRAPHIC_EQ_ROUNDED,
        icon_color="#071012",
        icon_size=22,
        bgcolor="#66FCF1",
        tooltip="Gửi lệnh text",
        on_click=submit_chat_text,
        width=42,
        height=42,
        padding=0,
    )

    def update_chat_send_button():
        has_text = bool(chat_input.value.strip())
        if chat_state["waiting"]:
            chat_send_button.icon = ft.Icons.STOP_ROUNDED
            chat_send_button.tooltip = "Đang chờ phản hồi"
            chat_send_button.bgcolor = "#EAFBFA"
            chat_send_button.icon_color = "#071012"
        elif has_text:
            chat_send_button.icon = ft.Icons.ARROW_UPWARD_ROUNDED
            chat_send_button.tooltip = "Gửi lệnh text"
            chat_send_button.bgcolor = "#66FCF1"
            chat_send_button.icon_color = "#071012"
        else:
            chat_send_button.icon = ft.Icons.GRAPHIC_EQ_ROUNDED
            chat_send_button.tooltip = "Nhập text hoặc dùng mic"
            chat_send_button.bgcolor = "#2E8E8A"
            chat_send_button.icon_color = "#DDFCF9"
        try:
            chat_send_button.update()
        except Exception:
            pass

    def on_chat_input_change(e):
        update_chat_send_button()

    chat_input.on_change = on_chat_input_change
    chat_input.on_submit = submit_chat_text

    chat_input_bar = ft.Container(
        width=640,
        height=52,
        padding=ft.Padding.symmetric(horizontal=12, vertical=5),
        bgcolor="#101923",
        border=ft.Border.all(1, "#2B5960"),
        border_radius=26,
        content=ft.Row(
            controls=[
                chat_add_button,
                chat_input_shell,
                chat_mode_label,
                chat_voice_button,
                chat_send_button,
            ],
            spacing=9,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
    update_chat_send_button()

    # --- Page Layout Assembly ---
    microphone_cluster = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=10,
        controls=[
            glow_indicator,
            status_gap,
            status_badge,
            microphone_gap,
            microphone_controls,
        ],
    )

    left_column = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.START,
        spacing=10,
        expand=True,
        width=300,
        controls=[
            brand_header,
            ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                content=microphone_cluster,
            ),
            ft.Row([temp_card, hum_card], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
        ]
    )

    right_column = ft.Column(
        spacing=10,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            camera_panel_shell,
            ft.Container(
                content=camera_controls,
                alignment=ft.Alignment.CENTER,
            ),
            ft.Text("TRUNG TÂM HỘI THOẠI", size=9, color="#45A29E", weight=ft.FontWeight.BOLD),
            chat_panel,
            ft.Container(
                content=chat_input_bar,
                alignment=ft.Alignment.CENTER,
            ),
        ]
    )

    main_hud_layout = ft.Row(
        spacing=15,
        expand=True,
        controls=[
            ft.Container(
                bgcolor="#1F2833",
                border_radius=8,
                padding=20,
                width=320,
                alignment=ft.Alignment.CENTER,
                content=left_column
            ),
            ft.Container(
                expand=True,
                bgcolor="#12161F",
                border_radius=8,
                padding=12,
                content=right_column
            )
        ]
    )

    page.add(main_hud_layout)
    page.update()

    # Apply default LLM settings at startup
    prov = DEFAULT_PROVIDER
    config = LLM_PROVIDERS.get(prov, {})
    if prov == "ollama":
        core.update_llm_settings(prov, api_key="ollama", api_base=config.get("api_base", "http://localhost:11434"))
    else:
        core.update_llm_settings(prov, api_key=config.get("api_key", ""), api_base=None)

    async def ui_queue_listener():
        """Reads core events asynchronously and updates Flet controls."""
        while core.is_running:
            try:
                event = await core.ui_queue.get()
                ev_type = event.get("type")
                ev_val = event.get("value")

                if ev_type == "state":
                    if ev_val == "IDLE":
                        chat_state["waiting"] = False
                        update_chat_send_button()
                        status_label.value = "Chờ lệnh..."
                        status_label.color = "#66FCF1"
                        state_icon.name = ft.Icons.MIC
                        state_icon.color = "#66FCF1"
                        glow_indicator.border.color = "#66FCF1"
                        apply_camera_layout(bool(camera_switch.value))
                    elif ev_val == "LISTENING":
                        status_label.value = "Đang lắng nghe..."
                        status_label.color = "#00FF00"
                        state_icon.name = ft.Icons.RECORD_VOICE_OVER
                        state_icon.color = "#00FF00"
                        glow_indicator.border.color = "#00FF00"
                    elif ev_val == "PROCESSING":
                        chat_state["waiting"] = True
                        update_chat_send_button()
                        status_label.value = "Đang suy nghĩ..."
                        status_label.color = "#FFBF00"
                        state_icon.name = ft.Icons.PSYCHOLOGY
                        state_icon.color = "#FFBF00"
                        glow_indicator.border.color = "#FFBF00"
                    elif ev_val == "SPEAKING":
                        status_label.value = "AIoT-Nexus đang nói..."
                        status_label.color = "#9900FF"
                        state_icon.name = ft.Icons.VOLUME_UP
                        state_icon.color = "#9900FF"
                        glow_indicator.border.color = "#9900FF"
                    
                elif ev_type == "log":
                    append_log(str(ev_val))

                elif ev_type == "chat_message":
                    append_chat_message(str(event.get("role", "assistant")), str(ev_val))

                elif ev_type == "xiaozhi_assistant_part":
                    append_xiaozhi_assistant_part(str(ev_val))
                    rendered = event.get("rendered")
                    if rendered is not None and not rendered.done():
                        rendered.set_result(True)

                elif ev_type == "telemetry":
                    temp_text.value = f"{event.get('temp')} °C"
                    hum_text.value = f"{event.get('humidity')} %"
                    
                elif ev_type == "camera_frame":
                    if camera_switch.value and core.vision.is_enabled:
                        camera_view.widget.src_base64 = str(ev_val)
                        camera_panel_shell.height = 360
                        camera_panel_shell.opacity = 1.0
                        camera_panel_shell.offset = (0, 0)
                        camera_panel_shell.ignore_interactions = False
                        camera_placeholder.visible = False
                        camera_feed.visible = True
                        fps_container.visible = True
                        camera_panel_shell.update()
                        camera_view.update()
                        camera_placeholder.update()

                elif ev_type == "camera_requested_state":
                    enabled = bool(ev_val)
                    camera_requested_state["enabled"] = enabled
                    camera_switch.value = enabled
                    apply_camera_layout(enabled)
                    camera_switch.update()
                    camera_panel_shell.update()
                    camera_placeholder.update()
                    camera_feed.update()
                    fps_container.update()

                elif ev_type == "camera_state":
                    enabled = bool(ev_val)
                    if enabled != camera_requested_state["enabled"]:
                        core.ui_queue.task_done()
                        continue
                    apply_camera_layout(enabled)
                    camera_switch.update()
                    camera_panel_shell.update()
                    camera_placeholder.update()
                    camera_feed.update()
                    fps_container.update()

                if ev_type != "camera_frame":
                    page.update()
                core.ui_queue.task_done()

            except Exception as e:
                print(f"UI listener error: {e}")
            await asyncio.sleep(0.05)

    async def camera_preview_loop():
        """Renders the latest captured frame at a steady UI-friendly cadence."""
        frame_interval = 1.0 / max(CAMERA_PREVIEW_FPS, 1.0)
        while core.is_running:
            started_at = time.perf_counter()
            try:
                if camera_switch.value:
                    b64_frame = await core.vision.get_preview_frame_base64()
                    if b64_frame and camera_switch.value and core.vision.is_enabled:
                        camera_view.widget.src_base64 = b64_frame
                        if not camera_feed.visible:
                            camera_panel_shell.height = 360
                            camera_panel_shell.opacity = 1.0
                            camera_panel_shell.offset = (0, 0)
                            camera_panel_shell.ignore_interactions = False
                            camera_placeholder.visible = False
                            camera_feed.visible = True
                            fps_container.visible = True
                            camera_panel_shell.update()
                            camera_placeholder.update()
                            fps_container.update()
                        camera_view.update()
                else:
                    await asyncio.sleep(0.1)
                    continue
            except Exception as e:
                print(f"Camera preview loop error: {e}")

            elapsed = time.perf_counter() - started_at
            await asyncio.sleep(max(0.0, frame_interval - elapsed))

    # Start core engine and spawn tasks
    await core.start()
    
    pulse_task = asyncio.create_task(pulse_indicator())
    listener_task = asyncio.create_task(ui_queue_listener())
    camera_task = asyncio.create_task(camera_preview_loop())

    async def cleanup(e):
        await core.stop()
        pulse_task.cancel()
        listener_task.cancel()
        camera_task.cancel()
        
    page.on_close = cleanup
