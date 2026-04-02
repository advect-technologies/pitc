# MCC 134 Thermocouple Logger

A reliable systemd service that reads temperature data from a Measurement Computing MCC 134 Thermocouple HAT and forwards it using the `daq-tools` library to MQTT (and other configured sinks).

Designed for long-term, unattended operation on a Raspberry Pi.

## Features

- Supports one or multiple MCC 134 boards
- Per-channel thermocouple type configuration (K, J, T, etc.)
- Flexible tagging (global, per-board, per-channel)
- Long-format output (one `DataPoint` per channel) — ideal for time-series databases and Grafana
- Robust error handling for open thermocouples (sent as `null`)
- Uses `daq-tools` for queuing, retries, and reliable delivery
- Runs as a systemd service using `uv run`

## Project Structure

```
pitc/
├── main.py                    # Main logger application
├── config.toml                # DAQIngestor and sink configuration
├── thermo_config.toml         # Hardware and sampling configuration
├── thermo-logger.service      # Systemd service definition
├── incoming/                  # Directory watched by DAQIngestor
├── data/                      # Internal queue and sink folders
└── daq_tools/                 # Local package
```

## Setup Instructions

### 1. Clone the Project

```bash
cd /home/st
git clone <your-repo-url> pitc
cd pitc
```

### 2. Install Dependencies

First, follow instructions [here](https://mccdaq.github.io/daqhats/install.html) for installing the daqhats library. Skip step 8 though, as we'll handle that differently.


```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies
uv sync
```

### 3. Configure the Application

Copy the example config files and customize them:

```bash
cp config.toml.example config.toml
cp thermo_config.toml.example thermo_config.toml
```

Edit both files to match your setup:

- `config.toml` — MQTT broker settings, topics, and other sinks
- `thermo_config.toml` — Board addresses, thermocouple types, sensor tags, sampling rate, batch size, etc.

**Important:** Make sure the `watch_dir` setting matches in both config files.

### 4. Create Required Directories

```bash
mkdir -p incoming data/queue
```

### 5. Install the Systemd Service

```bash
sudo cp thermo-logger.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable thermo-logger.service
sudo systemctl start thermo-logger.service
```

### 6. Verify Everything is Working

```bash
# Check service status
sudo systemctl status thermo-logger.service

# View live logs
sudo journalctl -u thermo-logger.service -f
```

## Useful Commands

```bash
# Restart the service
sudo systemctl restart thermo-logger.service

# Stop the service
sudo systemctl stop thermo-logger.service

# View recent logs
sudo journalctl -u thermo-logger.service -n 100

# Tail logs in real time
sudo journalctl -u thermo-logger.service -f
```

## Manual Testing

To run the logger manually (useful for debugging):

```bash
uv run python main.py
```

## Files Overview

- **`main.py`** — Core logging application
- **`config.toml`** — Controls `DAQIngestor` and data sinks
- **`thermo_config.toml`** — MCC 134 hardware and sampling settings
- **`thermo-logger.service`** — Systemd service definition

## Notes

- Open thermocouples are reported as `null` to prevent false spikes in dashboards.
- The service uses `uv run`, so it automatically manages dependencies.
- Logs are sent to `journalctl` for easy viewing and monitoring.

---

**Advect Technologies** – Built with `daq-tools`
