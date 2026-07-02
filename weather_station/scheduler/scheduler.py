import os
import time
import subprocess
from datetime import datetime
from pathlib import Path

import yaml

from weather_station.config.station_manager import get_station_context


CONFIG_FILE = Path("config/scheduler.yaml")


def load_scheduler_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"No existe {CONFIG_FILE}")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def station_task_policy(ctx):
    station_id = ctx["station_id"]
    mode = ctx.get("deployment_mode", "field")

    base = {
        "sync_master_dataset": True,
        "telegram_alert_sender": True,
        "health_monitor": True,
        "notification_engine": True,
        "remote_backup": True,
        "nasa_power_downloader": True,
        "era5_downloader": False,
        "daily_backup": False,
        "weather_logger": False,
        "radio_collector": False,
    }

    if station_id == "CU01":
        base["weather_logger"] = True
        base["radio_collector"] = True

    if station_id == "SJ01":
        base["weather_logger"] = True
        base["radio_collector"] = mode != "windows_lab"

    if mode == "windows_lab":
        base["weather_logger"] = False
        base["radio_collector"] = False
        base["remote_backup"] = False
        base["telegram_alert_sender"] = False
        base["notification_engine"] = False
        base["nasa_power_downloader"] = False

    return base


def should_run(task_name, task_cfg, policy):
    if task_name in policy:
        return bool(policy[task_name])
    return bool(task_cfg.get("enabled", False))


def run_task(task_name, task_cfg, env):
    command = task_cfg.get("command", [])
    timeout = task_cfg.get("_timeout", 300)

    if not command:
        print(f"[{task_name}] sin comando")
        return

    print(f"[{datetime.now().isoformat(timespec='seconds')}] Ejecutando: {task_name}")

    try:
        result = subprocess.run(
            command,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        if result.stdout.strip():
            print(result.stdout.strip())

        if result.returncode != 0:
            print(f"[{task_name}] ERROR returncode={result.returncode}")
            if result.stderr.strip():
                print(result.stderr.strip())

    except subprocess.TimeoutExpired:
        print(f"[{task_name}] TIMEOUT")


def main():
    cfg = load_scheduler_config()
    ctx = get_station_context()
    policy = station_task_policy(ctx)

    scheduler_cfg = cfg.get("scheduler", {})
    tasks = cfg.get("tasks", {})

    loop_sleep = scheduler_cfg.get("loop_sleep_seconds", 5)
    default_timeout = scheduler_cfg.get("task_timeout_seconds", 300)

    env = os.environ.copy()
    env["ATMOSLINK_STATION"] = os.getenv("ATMOSLINK_STATION", "")

    print("======================================")
    print(" AtmosLink Smart Scheduler")
    print("======================================")
    print(f"Station : {ctx['station_id']} | {ctx['station_name']}")
    print(f"Role    : {ctx['radio_role']}")
    print(f"Mode    : {ctx.get('deployment_mode')}")
    print(f"Config  : {ctx['config_file']}")
    print("======================================")

    last_run = {}

    while True:
        now = time.time()

        for task_name, task_cfg in tasks.items():
            task_cfg["_timeout"] = default_timeout

            if not should_run(task_name, task_cfg, policy):
                continue

            interval = task_cfg.get("interval_seconds", 60)
            previous = last_run.get(task_name, 0)

            if now - previous >= interval:
                run_task(task_name, task_cfg, env)
                last_run[task_name] = now

        time.sleep(loop_sleep)


if __name__ == "__main__":
    main()
