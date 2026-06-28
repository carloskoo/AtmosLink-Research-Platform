# AtmosLink Research Platform

AtmosLink Research Platform es una plataforma científica de adquisición, integración, monitoreo y respaldo de datos meteorológicos y de radioenlace para investigación en enlaces inalámbricos rurales altoandinos.

El sistema integra mediciones locales de una estación meteorológica basada en ESP32, datos externos de ERA5-Land y NASA POWER, telemetría de radioenlaces Cambium ePMP, monitoreo de salud del sistema, alertas por Telegram, dashboard científico y respaldo automático en Google Drive.

## Objetivo

Recolectar y fusionar datos ambientales y de desempeño de radioenlace para analizar la relación entre variables meteorológicas y parámetros de comunicación inalámbrica como RSSI, SNR, MCS, throughput y disponibilidad.

## Componentes principales

- Estación meteorológica local ESP32.
- Sensor BME280 para temperatura, humedad y presión.
- Pluviómetro para lluvia por minuto, lluvia última hora y acumulado.
- Base de datos SQLite.
- Dataset maestro `master_observations`.
- Dashboard científico Flask.
- Descarga de ERA5-Land.
- Descarga de NASA POWER.
- Colector Cambium ePMP.
- Scheduler automático.
- Health Monitor.
- Alertas por Telegram.
- Backup local y remoto a Google Drive mediante rclone.
- Acceso remoto por Tailscale.

## Arquitectura general

```text
ESP32 Weather Station
        ↓
weather_local
        ↓
quality control
        ↓
master_observations
        ↑
        ├── ERA5-Land
        ├── NASA POWER
        └── Cambium Radio Telemetry
        ↓
Scientific Dashboard
        ↓
Telegram Alerts / Google Drive Backups
