# AtmosLink Dashboard — Gunicorn y systemd

Este directorio contiene la configuración reproducible del dashboard
AtmosLink Research Platform.

## Componentes

- `atmoslink-dashboard.service`: servicio base de systemd.
- `atmoslink-dashboard.override.conf`: ejecución mediante Gunicorn.
- `install_dashboard_service.sh`: instala y reinicia el servicio.
- `check_dashboard_service.sh`: verifica procesos, endpoints y registros.

## Requisitos

- Proyecto: `/home/carlos/Proyectos/EstacionMeteorologica`
- Entorno virtual: `venv`
- Gunicorn instalado desde `requirements.txt`
- Linux con systemd

## Instalación

    cd ~/Proyectos/EstacionMeteorologica
    source venv/bin/activate
    pip install -r requirements.txt
    sudo bash deploy/systemd/install_dashboard_service.sh

## Verificación

    bash deploy/systemd/check_dashboard_service.sh

Resultados esperados:

    enabled
    active
    Dashboard: 200
    Latest API: 200
    Health API: 200
    status: healthy

## Configuración de producción

- Puerto: 5000
- Workers: 2
- Clase: gthread
- Threads: 4 por worker
- Timeout: 30 segundos
- Reinicio automático: 5 segundos

## Variables de entorno

    ATMOSLINK_STATION=CU01
    ATMOSLINK_WIND_ENABLED=0
    PYTHONUNBUFFERED=1

## Operación

Reiniciar:

    sudo systemctl restart atmoslink-dashboard.service

Consultar estado:

    systemctl status atmoslink-dashboard.service --no-pager -l

Consultar registros:

    journalctl -u atmoslink-dashboard.service -n 100 --no-pager

Health-check:

    curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool

## Adaptación para San José

Antes de desplegar en la Raspberry Pi deben ajustarse el usuario Linux,
la ruta del proyecto, el identificador de estación, la base SQLite,
la habilitación del viento y el número de workers.
