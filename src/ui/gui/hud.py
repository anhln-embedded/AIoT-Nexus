import asyncio
import base64
import flet as ft
from src.core.engine import AsyncCoreEngine
from src.core.config import (
    DEFAULT_PROVIDER,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    IS_PI,
    LLM_PROVIDERS,
)


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
    
    # --- Custom Styling Tokens ---
    BG_CARD = "#1F2833"
    BORDER_GLOW = "#45A29E"
    TEXT_NEON = "#66FCF1"
    
    # --- Left Panel UI Components (Glowing Status Eye) ---
    state_icon = ft.Icon(ft.Icons.MIC, size=55, color="#66FCF1")
    
    # Glowing Indicator Container
    glow_indicator = ft.Container(
        width=150,
        height=150,
        shape=ft.BoxShape.CIRCLE,
        bgcolor="#1F2833",
        border=ft.Border.all(3, "#66FCF1"),
        shadow=ft.BoxShadow(
            spread_radius=8,
            blur_radius=18,
            color=ft.Colors.with_opacity(0.3, "#66FCF1"),
            blur_style=ft.BlurStyle.OUTER,
        ),
        content=state_icon,
        alignment=ft.Alignment.CENTER,
        animate=ft.Animation(300, ft.AnimationCurve.DECELERATE),
    )
    
    status_label = ft.Text(
        "Khởi động hệ thống...",
        size=18,
        color="#66FCF1",
        weight=ft.FontWeight.BOLD
    )
    
    # Pulsing task for animation loop
    async def pulse_indicator():
        while core.is_running:
            if core.state == "LISTENING":
                glow_indicator.scale = 1.1
                glow_indicator.shadow.spread_radius = 12
                glow_indicator.shadow.blur_radius = 24
                glow_indicator.shadow.color = ft.Colors.with_opacity(0.7, "#00FF00")
            elif core.state == "SPEAKING":
                glow_indicator.scale = 1.05 if glow_indicator.scale == 1.0 else 1.0
                glow_indicator.shadow.spread_radius = 10
                glow_indicator.shadow.color = ft.Colors.with_opacity(0.6, "#9900FF")
            elif core.state == "PROCESSING":
                glow_indicator.scale = 1.0
                glow_indicator.shadow.spread_radius = 6 if glow_indicator.shadow.spread_radius == 12 else 12
                glow_indicator.shadow.color = ft.Colors.with_opacity(0.6, "#FFBF00")
            else:
                glow_indicator.scale = 1.0
                glow_indicator.shadow.spread_radius = 6
                glow_indicator.shadow.blur_radius = 14
                glow_indicator.shadow.color = ft.Colors.with_opacity(0.4, "#66FCF1")
                
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
    camera_placeholder = ft.Container(
        width=640,
        height=360,
        bgcolor="#0B0C10",
        border=ft.Border.all(2, "#45A29E"),
        border_radius=8,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.VIDEOCAM_OFF, size=45, color="#C5C6C7"),
                ft.Text("CAMERA STANDBY", size=14, color="#C5C6C7", weight=ft.FontWeight.BOLD)
            ]
        )
    )
    
    camera_feed = ft.Image(
        src=b"",
        width=640,
        height=360,
        fit=ft.BoxFit.CONTAIN,
        visible=False
    )
    
    camera_panel = ft.Container(
        content=ft.Stack([camera_placeholder, camera_feed])
    )

    # Debug / Status log console panel
    log_list = ft.ListView(
        expand=True,
        spacing=4,
        auto_scroll=True
    )
    
    log_panel = ft.Container(
        expand=True,
        bgcolor="#0B0C10",
        border=ft.Border.all(1, "#1F2833"),
        border_radius=5,
        padding=5,
        content=log_list
    )

    def append_log(message: str):
        log_list.controls.append(
            ft.Text(
                f">> {message}", 
                size=11, 
                color="#C5C6C7", 
                font_family="monospace"
            )
        )
        page.update()

    async def on_trigger_click(e):
        asyncio.create_task(core.trigger_voice_interaction())

    trigger_button = ft.ElevatedButton(
        content="THỰC THI LỆNH (MIC)",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        bgcolor="#45A29E",
        color="#0B0C10",
        on_click=on_trigger_click,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=6),
            text_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
        )
    )

    # --- Page Layout Assembly ---
    left_column = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=15,
        width=300,
        controls=[
            glow_indicator,
            status_label,
            trigger_button,
            ft.Divider(height=10, color="transparent"),
            ft.Row([temp_card, hum_card], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
        ]
    )

    right_column = ft.Column(
        spacing=10,
        expand=True,
        controls=[
            ft.Container(
                content=camera_panel,
                alignment=ft.Alignment.CENTER,
            ),
            ft.Text("BẢNG ĐIỀU KHIỂN HỆ THỐNG / LOGS", size=9, color="#45A29E", weight=ft.FontWeight.BOLD),
            log_panel
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
                        status_label.value = "Chờ lệnh..."
                        status_label.color = "#66FCF1"
                        state_icon.name = ft.Icons.MIC
                        state_icon.color = "#66FCF1"
                        glow_indicator.border.color = "#66FCF1"
                        camera_feed.visible = False
                        camera_placeholder.visible = True
                    elif ev_val == "LISTENING":
                        status_label.value = "Đang lắng nghe..."
                        status_label.color = "#00FF00"
                        state_icon.name = ft.Icons.RECORD_VOICE_OVER
                        state_icon.color = "#00FF00"
                        glow_indicator.border.color = "#00FF00"
                    elif ev_val == "PROCESSING":
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

                elif ev_type == "telemetry":
                    temp_text.value = f"{event.get('temp')} °C"
                    hum_text.value = f"{event.get('humidity')} %"
                    
                elif ev_type == "camera_frame":
                    camera_feed.src = base64.b64decode(str(ev_val))
                    camera_placeholder.visible = False
                    camera_feed.visible = True

                page.update()
                core.ui_queue.task_done()

            except Exception as e:
                print(f"UI listener error: {e}")
            await asyncio.sleep(0.05)

    # Start core engine and spawn tasks
    await core.start()
    
    pulse_task = asyncio.create_task(pulse_indicator())
    listener_task = asyncio.create_task(ui_queue_listener())

    async def cleanup(e):
        await core.stop()
        pulse_task.cancel()
        listener_task.cancel()
        
    page.on_close = cleanup
