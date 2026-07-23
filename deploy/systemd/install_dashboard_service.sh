#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="/home/carlos/Proyectos/EstacionMeteorologica"
SERVICE_NAME="atmoslink-dashboard.service"
SYSTEMD_DIR="/etc/systemd/system"
OVERRIDE_DIR="${SYSTEMD_DIR}/${SERVICE_NAME}.d"

echo "=============================================="
echo " AtmosLink Dashboard - Instalación systemd"
echo "=============================================="

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: ejecuta este script con sudo."
    echo
    echo "Ejemplo:"
    echo "  sudo bash deploy/systemd/install_dashboard_service.sh"
    exit 1
fi

if [[ ! -d "${PROJECT_DIR}" ]]; then
    echo "ERROR: no existe el proyecto:"
    echo "  ${PROJECT_DIR}"
    exit 1
fi

if [[ ! -x "${PROJECT_DIR}/venv/bin/gunicorn" ]]; then
    echo "ERROR: Gunicorn no está instalado en el entorno virtual."
    echo
    echo "Ejecuta:"
    echo "  cd ${PROJECT_DIR}"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

install -m 0644 \
    "${PROJECT_DIR}/deploy/systemd/atmoslink-dashboard.service" \
    "${SYSTEMD_DIR}/${SERVICE_NAME}"

mkdir -p "${OVERRIDE_DIR}"

install -m 0644 \
    "${PROJECT_DIR}/deploy/systemd/atmoslink-dashboard.override.conf" \
    "${OVERRIDE_DIR}/override.conf"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

sleep 5

echo
echo "===== ESTADO DEL SERVICIO ====="
systemctl status "${SERVICE_NAME}" --no-pager -l

echo
echo "===== HEALTH CHECK ====="

if curl --fail --silent \
    http://127.0.0.1:5000/api/health |
    python3 -m json.tool
then
    echo
    echo "Instalación completada correctamente."
else
    echo
    echo "ADVERTENCIA: el servicio inició, pero el health-check falló."
    echo
    echo "Revisa:"
    echo "  journalctl -u ${SERVICE_NAME} -n 100 --no-pager"
    exit 1
fi
