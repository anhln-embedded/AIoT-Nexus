import asyncio
import base64
import flet as ft
from src.core.engine import AsyncCoreEngine
from src.core.config import DEFAULT_PROVIDER, IS_PI, LLM_PROVIDERS


def configure_window(page: ft.Page, is_pi: bool = IS_PI) -> None:
    """Configures a kiosk window on Raspberry Pi and a dev window elsewhere."""
    if is_pi:
        page.padding = 0
        page.window.full_screen = True
        page.window.frameless = True
        page.window.maximized = True
        page.window.resizable = False
        page.window.maximizable = False
        return

    page.padding = 10
    page.window.width = 1024
    page.window.height = 600
    page.window.min_width = 960
    page.window.min_height = 540
    page.window.resizable = True
    page.window.maximizable = True

async def main_hud(page: ft.Page):
    # Setup Page Metadata
    page.title = "AIoT-Nexus Core OS HUD"
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
            padding=15,
            width=130,
            content=ft.Column(
                controls=[
                    ft.Text("NHIỆT ĐỘ", size=10, color="#C5C6C7", weight=ft.FontWeight.BOLD),
                    ft.Row([ft.Icon(ft.Icons.THERMOSTAT, color="#FF5555"), temp_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                ]
            )
        )
    )
    
    hum_card = ft.Card(
        bgcolor=BG_CARD,
        content=ft.Container(
            padding=15,
            width=130,
            content=ft.Column(
                controls=[
                    ft.Text("ĐỘ ẨM PHÒNG", size=10, color="#C5C6C7", weight=ft.FontWeight.BOLD),
                    ft.Row([ft.Icon(ft.Icons.WATER_DROP, color="#55AAFF"), hum_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                ]
            )
        )
    )

    # Actuators Status UI
    relay1_switch = ft.Switch(value=False, active_color="#66FCF1", disabled=True)
    relay2_switch = ft.Switch(value=False, active_color="#66FCF1", disabled=True)
    rgb_led_indicator = ft.Container(
        width=25, height=25, border_radius=5, bgcolor="black", border=ft.Border.all(1, "#C5C6C7")
    )
    
    actuators_card = ft.Card(
        bgcolor=BG_CARD,
        content=ft.Container(
            padding=12,
            content=ft.Column(
                spacing=5,
                controls=[
                    ft.Text("TRẠNG THÁI PHẦN CỨNG", size=10, color="#C5C6C7", weight=ft.FontWeight.BOLD),
                    ft.Row([
                        ft.Text("Relay 1", size=11), relay1_switch,
                        ft.Text("Relay 2", size=11), relay2_switch,
                    ], spacing=10),
                    ft.Row([
                        ft.Text("Đèn LED RGB:", size=11),
                        rgb_led_indicator,
                        ft.Text("MÔ PHỎNG: Windows 11" if not core.hw.is_pi else "PI PRODUCTION", size=9, color="#45A29E")
                    ], spacing=10)
                ]
            )
        )
    )

    # OpenCV Camera Vision Overlay Panel
    camera_placeholder = ft.Container(
        width=260,
        height=160,
        bgcolor="#0B0C10",
        border=ft.Border.all(2, "#45A29E"),
        border_radius=8,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.VIDEOCAM_OFF, size=35, color="#C5C6C7"),
                ft.Text("CAMERA STANDBY", size=11, color="#C5C6C7", weight=ft.FontWeight.BOLD)
            ]
        )
    )
    
    camera_feed = ft.Image(
        src=b"",
        width=260,
        height=160,
        fit=ft.BoxFit.CONTAIN,
        visible=False
    )
    
    camera_panel = ft.Container(
        content=ft.Stack([camera_placeholder, camera_feed])
    )

    # LLM Settings configuration panel
    provider_dropdown = ft.Dropdown(
        options=[
            ft.dropdown.Option("gemini", "Google Gemini"),
            ft.dropdown.Option("openai", "OpenAI GPT"),
            ft.dropdown.Option("ollama", "Local Ollama"),
        ],
        value=DEFAULT_PROVIDER,
        width=130,
        height=40,
        text_size=12,
        color="#66FCF1",
        border_color="#45A29E",
    )
    
    api_key_input = ft.TextField(
        label="LLM API Key",
        password=True,
        can_reveal_password=True,
        width=220,
        height=40,
        text_size=11,
        color="#66FCF1",
        border_color="#45A29E",
        hint_text="Nhập API Key ở đây...",
        value=LLM_PROVIDERS[DEFAULT_PROVIDER]["api_key"]
    )
    
    def on_provider_change(e):
        prov = provider_dropdown.value
        config = LLM_PROVIDERS.get(prov, {})
        api_key_input.value = config.get("api_key", "")
        if prov == "ollama":
            api_key_input.label = "Ollama Endpoint"
            api_key_input.value = config.get("api_base", "http://localhost:11434")
            api_key_input.password = False
        else:
            api_key_input.label = "LLM API Key"
            api_key_input.password = True
        
        apply_settings(None)
        page.update()

    provider_dropdown.on_change = on_provider_change

    def apply_settings(e):
        prov = provider_dropdown.value
        val = api_key_input.value
        if prov == "ollama":
            core.update_llm_settings(prov, api_key="ollama", api_base=val)
        else:
            core.update_llm_settings(prov, api_key=val, api_base=None)

    api_key_input.on_change = apply_settings

    # Debug / Status log console panel
    log_list = ft.ListView(
        expand=True,
        spacing=4,
        auto_scroll=True
    )
    
    log_panel = ft.Container(
        height=85,
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
        ]
    )

    right_column = ft.Column(
        spacing=10,
        expand=True,
        controls=[
            ft.Row([temp_card, hum_card], spacing=10),
            actuators_card,
            ft.Row([
                provider_dropdown,
                api_key_input
            ], spacing=10),
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
                bgcolor="#1F2833",
                border_radius=8,
                padding=10,
                alignment=ft.Alignment.CENTER,
                content=camera_panel
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

    apply_settings(None)

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
                    
                    relays = event.get("relays", {})
                    relay1_switch.value = relays.get(1, False)
                    relay2_switch.value = relays.get(2, False)
                    
                    led_color = event.get("led_color", "off").lower()
                    color_mapping = {
                        "red": "red",
                        "green": "green",
                        "blue": "blue",
                        "yellow": "yellow",
                        "white": "white",
                        "off": "black"
                    }
                    rgb_led_indicator.bgcolor = color_mapping.get(led_color, "black")
                    
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
