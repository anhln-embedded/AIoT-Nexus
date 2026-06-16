#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
MAIN_FILE="${PROJECT_DIR}/main.py"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
WAIT_SECONDS="${AIOT_DISPLAY_WAIT_SECONDS:-60}"
AUTO_UPDATE="${AIOT_AUTO_UPDATE:-true}"
UPDATE_REMOTE="${AIOT_UPDATE_REMOTE:-origin}"
UPDATE_BRANCH="${AIOT_UPDATE_BRANCH:-}"

export HOME="${HOME:-$(getent passwd "$(id -un)" | cut -d: -f6)}"
export XDG_RUNTIME_DIR="${RUNTIME_DIR}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${RUNTIME_DIR}/bus}"
export AIOT_IS_PI="true"
export FLET_DESKTOP_FLAVOR="full"
export NO_AT_BRIDGE="1"

update_from_git() {
    if [[ "${AUTO_UPDATE}" != "true" ]]; then
        echo "[AIoT-Nexus] Auto update disabled."
        return
    fi

    if ! command -v git >/dev/null 2>&1; then
        echo "[AIoT-Nexus] git was not found; skipping auto update." >&2
        return
    fi

    if [[ ! -d "${PROJECT_DIR}/.git" ]]; then
        echo "[AIoT-Nexus] ${PROJECT_DIR} is not a git repository; skipping auto update." >&2
        return
    fi

    if [[ -z "${UPDATE_BRANCH}" ]]; then
        UPDATE_BRANCH="$(git -C "${PROJECT_DIR}" branch --show-current || true)"
    fi

    if [[ -z "${UPDATE_BRANCH}" ]]; then
        echo "[AIoT-Nexus] Could not detect git branch; skipping auto update." >&2
        return
    fi

    if [[ -n "$(git -C "${PROJECT_DIR}" status --porcelain --untracked-files=no)" ]]; then
        echo "[AIoT-Nexus] Local changes detected; skipping auto update to avoid overwriting work." >&2
        return
    fi

    echo "[AIoT-Nexus] Updating from ${UPDATE_REMOTE}/${UPDATE_BRANCH}..."

    local before
    local after
    before="$(git -C "${PROJECT_DIR}" rev-parse HEAD)"

    if ! git -C "${PROJECT_DIR}" fetch --prune "${UPDATE_REMOTE}" "${UPDATE_BRANCH}"; then
        echo "[AIoT-Nexus] git fetch failed; starting current version." >&2
        return
    fi

    if ! git -C "${PROJECT_DIR}" merge --ff-only "FETCH_HEAD"; then
        echo "[AIoT-Nexus] git update requires manual merge; starting current version." >&2
        return
    fi

    after="$(git -C "${PROJECT_DIR}" rev-parse HEAD)"

    if [[ "${before}" == "${after}" ]]; then
        echo "[AIoT-Nexus] Already up to date."
        return
    fi

    echo "[AIoT-Nexus] Updated to ${after}."

    if git -C "${PROJECT_DIR}" diff --name-only "${before}" "${after}" | grep -qx "requirements.txt"; then
        echo "[AIoT-Nexus] requirements.txt changed; installing dependencies..."
        "${PYTHON_BIN}" -m pip install -r "${PROJECT_DIR}/requirements.txt"
    fi
}

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

update_from_git
wait_for_display
configure_uart
exec "${PYTHON_BIN}" "${MAIN_FILE}"
