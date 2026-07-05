#!/usr/bin/python3
"""
sys-sitter: A lightweight, robust systemd babysitter daemon.
Monitors systemd units and restarts them per configuration policies.
Supports dynamic config reloading and non-blocking restarts.
"""

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any
import yaml
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Global logger
logger = logging.getLogger("sys-sitter")


class ServiceCheck:
    """Represents the configuration and monitoring state of a systemd unit."""

    def __init__(self, unit: str, mode: str, interval: float, max_restarts: int, file_path: Path, mtime: float):
        self.unit = unit
        self.mode = mode
        self.interval = interval
        self.max_restarts = max_restarts
        self.file_path = file_path
        self.mtime = mtime

        self.next_run = time.time()
        self.restarts = 0
        self.lock = threading.Lock()
        self.restarting = False


def setup_logging(log_file: str) -> None:
    """Configures the logging format and handlers with fallback to local log or stdout."""
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Try setting up log file handler
    log_path = Path(log_file)
    file_handler = None
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
    except (PermissionError, FileNotFoundError, OSError) as e:
        fallback_path = Path("sys-sitter.log")
        print(f"Warning: Cannot write to log file {log_file} ({e}). Falling back to local {fallback_path.absolute()}")
        try:
            file_handler = logging.FileHandler(fallback_path, mode='a', encoding='utf-8')
        except OSError:
            print("Warning: Falling back to console-only logging.")

    if file_handler:
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Console stream handler for interactive run
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def validate_config(data: Dict[str, Any], file_path: Path) -> bool:
    """Validates the structure and types of the configuration data."""
    try:
        if not isinstance(data, dict):
            logger.warning(f"Config file {file_path} is not a YAML dictionary.")
            return False

        if "interval" not in data or not isinstance(data["interval"], (int, float)) or data["interval"] <= 0:
            logger.warning(f"Config file {file_path} is missing a valid positive 'interval'.")
            return False

        if "service" not in data or not isinstance(data["service"], dict):
            logger.warning(f"Config file {file_path} is missing a 'service' section.")
            return False

        service = data["service"]
        if "unit" not in service or not isinstance(service["unit"], str) or not service["unit"].strip():
            logger.warning(f"Config file {file_path} is missing a valid service 'unit'.")
            return False

        if "mode" not in service or service["mode"] not in ("observe", "enforce"):
            logger.warning(f"Config file {file_path} service 'mode' must be 'observe' or 'enforce'.")
            return False

        return True
    except Exception as e:
        logger.warning(f"Error validating config file {file_path}: {e}")
        return False


def check_systemd(unit: str) -> bool:
    """Queries systemd to check if a unit is active."""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', unit],
            capture_output=True,
            text=True,
            check=False
        )
        return result.stdout.strip() == "active"
    except FileNotFoundError:
        logger.error("systemctl command not found. systemd is required for sys-sitter.")
        return False
    except Exception as e:
        logger.error(f"Error running systemctl is-active for {unit}: {e}")
        return False


def perform_restart(check: ServiceCheck) -> None:
    """Executes the systemctl restart command in a background thread."""
    try:
        logger.info(f"Triggering restart for unit {check.unit}...")
        result = subprocess.run(
            ['systemctl', 'restart', check.unit],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            logger.info(f"Successfully restarted unit {check.unit}")
        else:
            logger.error(f"Failed to restart unit {check.unit}: {result.stderr.strip()}")
    except Exception as e:
        logger.exception(f"Exception while restarting unit {check.unit}: {e}")
    finally:
        with check.lock:
            check.restarts += 1
            check.restarting = False


def check_and_recover(check: ServiceCheck) -> None:
    """Runs a status check and handles service recovery if needed."""
    with check.lock:
        if check.restarting:
            logger.debug(f"Skip check for {check.unit}: restart is currently in progress.")
            return

    # Check status (outside of lock to keep it responsive)
    is_active = check_systemd(check.unit)
    timestamp = time.strftime('%H:%M:%S')

    with check.lock:
        if is_active:
            if check.restarts > 0:
                logger.info(f"Service {check.unit} recovered after {check.restarts} restart attempt(s).")
                check.restarts = 0
            print(f"[{timestamp}] ... {check.unit} ... OK")
            logger.info(f"{check.unit} is active")
        else:
            print(f"[{timestamp}] ... {check.unit} ... FAIL")
            logger.warning(f"{check.unit} is inactive (mode: {check.mode})")

            if check.mode == 'enforce':
                if check.restarts < check.max_restarts:
                    check.restarting = True
                    # Launch non-blocking restart in background
                    threading.Thread(target=perform_restart, args=(check,), daemon=True).start()
                elif check.restarts == check.max_restarts:
                    logger.error(f"Failed to restart {check.unit} after {check.max_restarts} attempts. Giving up.")
                    print(f"[{timestamp}] ... {check.unit} ... gave up")
                    check.restarts += 1
                else:
                    logger.warning(f"Still gave up on {check.unit} (max restarts reached)")


def reload_configs(config_dir: str, checks: Dict[str, ServiceCheck]) -> None:
    """Scans the config directory and updates the active monitoring list."""
    path = Path(config_dir)
    if not path.exists() or not path.is_dir():
        logger.error(f"Config directory {config_dir} does not exist or is not a directory.")
        return

    current_keys = set()
    for file in path.iterdir():
        if file.is_dir() or file.suffix not in ('.yml', '.yaml'):
            continue

        file_key = str(file.resolve())
        try:
            mtime = file.stat().st_mtime

            # Load and parse config
            with file.open('r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)

            if not validate_config(config_data, file):
                continue

            unit = config_data['service']['unit']
            mode = config_data['service']['mode']
            interval = float(config_data['interval'])
            max_restarts = config_data['service'].get('max_restarts', 3)

            current_keys.add(file_key)

            if file_key not in checks:
                logger.info(f"Loaded new monitor: {unit} from {file.name} (interval={interval}s, mode={mode})")
                checks[file_key] = ServiceCheck(unit, mode, interval, max_restarts, file, mtime)
            elif checks[file_key].mtime != mtime:
                logger.info(f"Reloading updated config for: {unit} from {file.name}")
                with checks[file_key].lock:
                    checks[file_key].unit = unit
                    checks[file_key].mode = mode
                    checks[file_key].interval = interval
                    checks[file_key].max_restarts = max_restarts
                    checks[file_key].mtime = mtime
                    # Force a check run soon
                    checks[file_key].next_run = min(checks[file_key].next_run, time.time() + interval)
        except Exception as e:
            logger.error(f"Failed to process config file {file}: {e}")

    # Clean up deleted configurations
    for file_key in list(checks.keys()):
        if file_key not in current_keys:
            removed = checks.pop(file_key)
            logger.info(f"Stopped monitoring unit {removed.unit} (config file deleted)")


def main() -> None:
    """Main entrypoint parsing arguments and driving the loop."""
    parser = argparse.ArgumentParser(description="sys-sitter: systemd babysitter daemon")
    parser.add_argument(
        "--config-dir",
        type=str,
        default=os.getenv("CONFIG_DIRECTORY", "./conf.d"),
        help="Directory containing service YAML files"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=os.getenv("LOG_FILE", "/var/log/sys-sitter.log"),
        help="Log file location"
    )
    args, unknown = parser.parse_known_args()

    setup_logging(args.log_file)
    logger.info("Starting sys-sitter daemon...")

    checks: Dict[str, ServiceCheck] = {}
    last_config_reload = 0.0
    reload_interval = 10.0  # Seconds between scanning directory for config changes

    # ThreadPoolExecutor to run systemctl checks in parallel without blocking main loop
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor(max_workers=5)

    try:
        while True:
            now = time.time()

            # Dynamic config reload
            if now - last_config_reload >= reload_interval:
                reload_configs(args.config_dir, checks)
                last_config_reload = now

            # Process checks
            for check in list(checks.values()):
                if now >= check.next_run:
                    # Update next run time before submitting to avoid duplicate submits
                    with check.lock:
                        check.next_run = now + check.interval
                    executor.submit(check_and_recover, check)

            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Stopping sys-sitter daemon (KeyboardInterrupt)...")
    finally:
        executor.shutdown(wait=True)
        logger.info("sys-sitter daemon stopped.")


if __name__ == "__main__":
    main()
