#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="aiot-nexus"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename -- "${BASH_SOURCE[0]}")"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
MAIN_FILE="${PROJECT_DIR}/main.py"
LAUNCHER_FILE="${PROJECT_DIR}/scripts/launch-pi.sh"
RUN_USER="${SUDO_USER:-${USER}}"
RUN_GROUP="$(id -gn "${RUN_USER}")"
RUN_UID="$(id -u "${RUN_USER}")"
RUN_HOME="$(getent passwd "${RUN_USER}" | cut -d: -f6)"

usage() {
    cat <<EOF
AIoT-Nexus production process manager

Usage: ./scripts/${SCRIPT_NAME} <command>

Commands:
  install     Create, enable and start the systemd service
  uninstall   Stop, disable and remove the systemd service
  start       Start the background process
  stop        Stop the background process
  restart     Restart the background process
  status      Show service status
  logs        Follow service logs
  enable      Enable automatic startup on boot
  disable     Disable automatic startup on boot
EOF
}

require_pi_environment() {
    if [[ "$(uname -s)" != "Linux" ]]; then
        echo "This production script must run on Raspberry Pi/Linux." >&2
        exit 1
    fi

    if ! command -v systemctl >/dev/null 2>&1; then
        echo "systemd is required but systemctl was not found." >&2
        exit 1
    fi
}

require_installation() {
    if [[ ! -f "${SERVICE_FILE}" ]]; then
        echo "Service is not installed. Run: ./scripts/${SCRIPT_NAME} install" >&2
        exit 1
    fi
}

install_service() {
    if [[ ! -x "${PYTHON_BIN}" ]]; then
        echo "Missing virtual environment: ${PYTHON_BIN}" >&2
        echo "Create it and install requirements before installing the service." >&2
        exit 1
    fi

    if [[ ! -f "${MAIN_FILE}" ]]; then
        echo "Missing application entry point: ${MAIN_FILE}" >&2
        exit 1
    fi

    if [[ ! -f "${LAUNCHER_FILE}" ]]; then
        echo "Missing Raspberry Pi launcher: ${LAUNCHER_FILE}" >&2
        exit 1
    fi

    chmod +x "${LAUNCHER_FILE}"

    sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=AIoT-Nexus
Wants=network-online.target
After=network-online.target display-manager.service graphical.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=-${PROJECT_DIR}/.env
Environment=AIOT_IS_PI=true
Environment=FLET_DESKTOP_FLAVOR=full
Environment=XDG_RUNTIME_DIR=/run/user/${RUN_UID}
Environment=HOME=${RUN_HOME}
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${RUN_UID}/bus
ExecStart=${LAUNCHER_FILE}
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
KillSignal=SIGINT

[Install]
WantedBy=graphical.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable --now "${SERVICE_NAME}.service"
    echo "Installed and started ${SERVICE_NAME}.service"
    sudo systemctl --no-pager --full status "${SERVICE_NAME}.service" || true
}

uninstall_service() {
    if [[ -f "${SERVICE_FILE}" ]]; then
        sudo systemctl disable --now "${SERVICE_NAME}.service" || true
        sudo rm -f "${SERVICE_FILE}"
        sudo systemctl daemon-reload
        sudo systemctl reset-failed
    fi
    echo "Removed ${SERVICE_NAME}.service"
}

main() {
    require_pi_environment

    case "${1:-}" in
        install)
            install_service
            ;;
        uninstall)
            uninstall_service
            ;;
        start|stop|restart|enable|disable)
            require_installation
            sudo systemctl "$1" "${SERVICE_NAME}.service"
            ;;
        status)
            require_installation
            sudo systemctl --no-pager --full status "${SERVICE_NAME}.service"
            ;;
        logs)
            require_installation
            sudo journalctl -u "${SERVICE_NAME}.service" -f
            ;;
        help|-h|--help)
            usage
            ;;
        *)
            usage >&2
            exit 1
            ;;
    esac
}

main "$@"
