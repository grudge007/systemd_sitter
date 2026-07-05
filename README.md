# sys-sitter

`sys-sitter` is a lightweight, robust, and concurrent systemd service babysitter daemon. It continuously monitors configured systemd units, logs their status, and automatically attempts to restart them according to policy.

---

## Key Features

1. **Concurrent Service Checks**: Uses a `ThreadPoolExecutor` to run systemd status checks in parallel. Slow/hanging checks for one service will never block checks for other services.
2. **Non-blocking Restarts**: Recovery actions (`systemctl restart`) are executed in background threads. A slow restart of one service will not freeze the daemon's main monitoring loop.
3. **Dynamic Configuration Reloading**: Scans the configuration directory periodically (every 10 seconds) to detect new, modified, or deleted configuration files. Services are added, updated, or removed from the monitor list in-memory without needing a daemon restart.
4. **Flexible CLI & Environment Variables**: Supports `--config-dir` and `--log-file` CLI arguments, falling back to environment variables (`CONFIG_DIRECTORY`, `LOG_FILE`), and finally to sensible defaults (`./conf.d` and `/var/log/sys-sitter.log`).
5. **Resilient Logging Fallback**: Automatically falls back to a local log file or standard output if `/var/log/sys-sitter.log` is not writable (e.g., when run locally or without root permissions).
6. **Debian Package Build Integration**: Includes an architecture-independent (`Architecture: all`) Debian package configuration to install the babysitter as a systemd service.

---

## Directory Structure

```
├── .env                  # Local environment overrides
├── .gitignore            # Git ignore rules for Pycache, builds, and logs
├── README.md             # Project documentation (this file)
├── sys_sitter.py         # Main daemon source code
├── conf.d/               # Local service configuration directory
│   ├── apache2.yaml
│   ├── nginx.yml
│   └── ssh.yml
└── package_build/        # Debian package build structure
    ├── sys-sitter_1.0.1.deb # Pre-built Debian package
    └── sys-sitter_1.0.1/    # Package source tree
        ├── DEBIAN/
        │   ├── control   # Package metadata (updated to 'all' arch)
        │   ├── postinst  # Creates syssitter user, log files, enables service
        │   └── prerm     # Stops and disables service on removal
        ├── etc/
        │   └── sys-sitter/
        ├── lib/
        │   └── systemd/system/sys-sitter.service  # Systemd service definition
        └── usr/
            └── local/bin/sys-sitter               # Executable script script (matching sys_sitter.py)
```

---

## Configuration

Service configuration files are placed in the config directory (e.g., `conf.d/`) and must be in YAML format.

Example configuration (`conf.d/nginx.yml`):
```yaml
interval: 10              # Frequency of checks (in seconds)

service:
  unit: nginx.service     # Systemd unit name
  mode: enforce           # 'enforce' (auto-restart) or 'observe' (log only)
  max_restarts: 3         # (Optional) Max consecutive restart attempts (default: 3)
```

---

## Local Usage

To run the daemon locally for testing:
```bash
python3 sys_sitter.py --config-dir ./conf.d --log-file ./sys-sitter.log
```

---

## Debian Packaging & Production Deployment

### 1. Build the Debian Package
Build the architecture-independent `.deb` file with correct root-level permissions:
```bash
dpkg-deb --root-owner-group --build package_build/sys-sitter_1.0.1
```

### 2. Install the Package
Installs the binary to `/usr/local/bin/sys-sitter`, installs the systemd unit file, creates the `syssitter` system user, and starts the service:
```bash
sudo apt install ./package_build/sys-sitter_1.0.1.deb
```

### 3. Systemd Service Control
Manage the daemon using standard systemd commands:
```bash
sudo systemctl status sys-sitter.service
sudo systemctl restart sys-sitter.service
sudo journalctl -u sys-sitter.service -f
```

---

## Improvements & Cleanup (Refactoring Notes)

- **Removed Unwanted/Redundant Files**:
  - `sitter.py`: A commented-out prototype.
  - `sy_sitter.py`: An outdated/incomplete duplicate script.
  - `conf.d/tets.txt`: A stray junk test file.
  - `siiter.log`: Removed old log file with a typo in the name.
- **Fixed Bottlenecks**:
  - Replaced the synchronous, single-threaded loop with a concurrent, thread-pool-based task executor.
  - Made the restart sequence non-blocking, resolving a deadlock/freeze bottleneck where a hanging unit restart blocked other checks.
- **Fixed Systemd Service Incompatibility**:
  - The packaged systemd service calls `/usr/local/bin/sys-sitter --config-dir /etc/sys-sitter/conf.d`. The previous script ignored CLI arguments and only read environment variables, causing it to crash or misbehave inside the service. The script now fully parses and utilizes command-line arguments.
  - Corrected log file typo from `siiter.log` to `sys-sitter.log` and enabled graceful permission fallback logging.
- **Updated Package Architecture**:
  - Changed `Architecture` in the Debian control file from `amd64` to `all` to reflect that this is a pure, platform-independent Python utility.
