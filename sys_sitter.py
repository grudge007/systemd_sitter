#!/usr/bin/python3
'''
Docstring for sys_sitter
'''
import subprocess
import time
import os
import logging
from pathlib import Path
import yaml
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='siiter.log',
    filemode='a')
logger = logging.getLogger(__name__)

CONFIG_DIR = os.getenv('CONFIG_DIRECTORY')
path = Path(CONFIG_DIR)


def load_checks():
    '''
    Docstring for load_checks
    
    :return: Description
    :rtype: list
    '''
    checks = []
    for file in path.iterdir():
        if file.is_dir() or file.suffix not in ['.yml', '.yaml']:
            continue

        with file.open() as f:
            config_data = yaml.safe_load(f)

        unit = config_data['service']['unit']
        interval = config_data['interval']
        mode = config_data['service']['mode']

        checks.append ({
            'unit': unit,
            'mode': mode,
            'interval': interval,
            'next_run': time.time()
        })

    return checks


def check_systemd(unit : str) -> bool:
    '''
    Docstring for check_systemd
    
    :param unit: Description
    :type unit: str
    :return: Description
    :rtype: bool
    '''
    
    result = subprocess.run(
        ['systemctl', 'is-active', unit],
        capture_output=True, text=True
    ).stdout.strip()

    return result == "active"


def main():
    checks = load_checks()
    while True:
        now = time.time()
        for check in checks:
            unit = check['unit']
            mode = check['mode']
            if now >= check['next_run']:
                status = check_systemd(unit)
                # print(f"[{time.strftime('%H:%M:%S')}] ... {check['unit']} ... {'OK' if status else 'FAIL'}")
                if status:
                    print(f"[{time.strftime('%H:%M:%S')}] ... {check['unit']} ... OK")
                    logger.info(f"{unit} is active")
                    print('-' * 40)
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] ... {check['unit']} ... FAIL")
                    print('-' * 40)
                    logger.info(f"{unit} is inactive")
                    if mode == 'enforce':
                        logger.info(f'we will restart {unit} after day 5')
   
                check['next_run'] = now + check['interval']
        time.sleep(1)

if __name__ == "__main__":
    main()
