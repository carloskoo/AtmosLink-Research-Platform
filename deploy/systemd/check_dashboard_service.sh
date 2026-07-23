#!/usr/bin/env bash

set -u

SERVICE_NAME="atmoslink-dashboard.service"
BASE_URL="http://127.0.0.1:5000"

echo "=============================================="
echo " AtmosLink Dashboard - Verificación operativa"
echo "=============================================="

echo
echo "1. Estado systemd"
echo "-----------------"

systemctl is-enabled "${SERVICE_NAME}" 2>/dev/null || true
systemctl is-active "${SERVICE_NAME}" 2>/dev/null || true

echo
echo "2. Proceso principal"
echo "--------------------"

systemctl show "${SERVICE_NAME}" \
    --property=MainPID \
    --property=ExecMainStartTimestamp \
    --property=Environment \
    --no-pager

MAIN_PID="$(
    systemctl show "${SERVICE_NAME}" \
    --property=MainPID \
    --value
)"

if [[ -n "${MAIN_PID}" && "${MAIN_PID}" != "0" ]]; then
    echo
    pstree -ap "${MAIN_PID}" || true
fi

echo
echo "3. Endpoints HTTP"
echo "-----------------"

curl -s -o /dev/null \
    -w 'Dashboard: %{http_code}\n' \
    "${BASE_URL}/"

curl -s -o /dev/null \
    -w 'Latest API: %{http_code}\n' \
    "${BASE_URL}/api/latest"

curl -s -o /dev/null \
    -w 'Health API: %{http_code}\n' \
    "${BASE_URL}/api/health"

echo
echo "4. Health-check"
echo "---------------"

curl --fail --silent \
    "${BASE_URL}/api/health" |
    python3 -m json.tool

echo
echo "5. Últimos registros"
echo "--------------------"

journalctl \
    -u "${SERVICE_NAME}" \
    -n 20 \
    --no-pager
