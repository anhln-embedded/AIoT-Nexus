#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
MAIN_FILE="${PROJECT_DIR}/main.py"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
WAIT_SECONDS="${AIOT_DISPLAY_WAIT_SECONDS:-60}"

export HOME="${HOME:-$(getent passwd "$(id -un)" | cut -d: -f6)}"
export XDG_RUNTIME_DIR="${RUNTIME_DIR}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${RUNTIME_DIR}/bus}"
export AIOT_IS_PI="true"
export FLET_DESKTOP_FLAVOR="full"
export NO_AT_BRIDGE="1"

configure_uart() {
    if [[ -n "${AIOT_USE_UART:-}" ]]; then
        return
    fi

    if [[ -n "${AIOT_PORT_PI:-}" && -e "${AIOT_PORT_PI}" ]]; then
        export AIOT_USE_UART="true"
        echo "[AIoT-Nexus] Using configured UART ${AIOT_PORT_PI}"
        return
    fi

    local port
    for port in /dev/serial0 /dev/ttyUSB0 /dev/ttyACM0; do
        if [[ -e "${port}" ]]; then
            export AIOT_PORT_PI="${port}"
            export AIOT_USE_UART="true"
            echo "[AIoT-Nexus] Auto-detected UART ${AIOT_PORT_PI}"
            return
        fi
    done

    export AIOT_USE_UART="false"
    echo "[AIoT-Nexus] No UART device found; using hardware simulation."
}

wait_for_display() {
    local elapsed=0

    while (( elapsed < WAIT_SECONDS )); do
        if [[ -S "${RUNTIME_DIR}/wayland-0" ]]; then
            export WAYLAND_DISPLAY="wayland-0"
            export GDK_BACKEND="wayland,x11"
            echo "[AIoT-Nexus] Using Wayland display ${RUNTIME_DIR}/${WAYLAND_DISPLAY}"
            return 0
        fi

        if [[ -S "/tmp/.X11-unix/X0" ]]; then
            export DISPLAY=":0"
            export GDK_BACKEND="x11"
            if [[ -f "${HOME}/.Xauthority" ]]; then
                export XAUTHORITY="${HOME}/.Xauthority"
            fi
            echo "[AIoT-Nexus] Using X11 display ${DISPLAY}"
            return 0
        fi

        sleep 1
        ((elapsed += 1))
    done

    echo "[AIoT-Nexus] No graphical session found after ${WAIT_SECONDS}s." >&2
    echo "[AIoT-Nexus] Log in to the Raspberry Pi desktop or enable desktop autologin." >&2
    exit 1
}

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "[AIoT-Nexus] Missing Python environment: ${PYTHON_BIN}" >&2
    exit 1
fi

wait_for_display
configure_uart
exec "${PYTHON_BIN}" "${MAIN_FILE}"
