#!/usr/bin/python3
'''happy pylint'''
import os
import subprocess
import yaml
from dotenv import load_dotenv

load_dotenv()

CONFIG_DIRECTORY = os.getenv("CONFIG_DIRECTORY")

for file in os.listdir(CONFIG_DIRECTORY):
    if not file.endswith((".yaml", ".yml")):
        continue

    file_path = os.path.join(CONFIG_DIRECTORY, file)

    try:
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

            interval = data["interval"]
            service = data["service"]["unit"]
            mode = data["service"]["mode"]

            if not service or not mode:
                continue

    except (KeyError, IsADirectoryError):
        print(f"Invalid or bad config file: {file}")
        continue

    # Check service status
    result = subprocess.run(
        ["systemctl", "is-active", service],
        capture_output=True,
        text=True
    )
    status = result.stdout.strip()

    if status == "active":
        print(f"{service} is running")
        continue

    print(f"{service} is down (status: {status})")

    # Try to restart
    restart_result = subprocess.run(
        ["systemctl", "restart", service],
        capture_output=True,
        text=True
    )

    if restart_result.returncode == 0:
        print(f"{service} restarted successfully")
    else:
        print(f"Failed to restart {service}: {restart_result.stderr.strip()}")
