#!/usr/bin/python3
"""
Docstring for sy_sitter
"""
import os
import subprocess
import time
import yaml
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

CONFIG_DIR = os.getenv("CONFIG_DIRECTORY")

def load_checks(config_dir: str):
    checks = []
    path = Path(config_dir)
    for file in path.iterdir():
        if file.is_dir() or file.suffix not in (".yml", ".yaml"):
            continue
        with file.open() as f:
            config_data = yaml.safe_load(f)
        service_name = config_data['service']['unit']
        mode = config_data['service'].get("mode", "observe")
        interval = config_data['interval']
        checks.append({
            "unit": service_name,
            "mode": mode,
            "interval": interval,
            "next_run": time.time()
        })

    return checks


def check_systemd(unit : str) -> bool:
    isActive = subprocess.run(
        ["systemctl", "is-active", unit],
        capture_output=True, text=True
    )
    
    return isActive.stdout.strip() == "active"


def main():
    configs = load_checks(CONFIG_DIR)
    while True:
        now = time.time()
        for c in configs:            
            if now >= c['next_run']:
                status = check_systemd(c['unit'])
                if status:
                    print(f"[{time.strftime('%H:%M:%S')}] ... {c['unit']} ... {status}")
                    
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] ... {c['unit']} ... FAIL")
                c['next_run'] = now + c['interval']
  
        print("-" * 30)
        time.sleep(1)

if __name__ == "__main__":
    main()