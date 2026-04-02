#!/usr/bin/env python3
"""
Robust MCC 134 Thermocouple Logger → DAQIngestor

Supports multiple boards, per-channel configuration, long-format DataPoints.
"""
import signal
import sys
import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict

import tomllib
from daqhats import mcc134, HatIDs, TcTypes, hat_list

from daq_tools import DAQIngestor
from daq_tools.models import DataPoint

def handle_shutdown(signum, frame):
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

logger = logging.getLogger(__name__)

class ThermoConfig:
    def __init__(self, path: str | Path = "thermo_config.toml"):
        self.path = Path(path)
        self.app: Dict[str, Any] = {}
        self.boards: list[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if not self.path.exists():
            raise FileNotFoundError(f"Config file not found: {self.path}")

        with open(self.path, "rb") as f:
            data = tomllib.load(f)

        self.app = data.get("app", {})
        self.boards = data.get("boards", [])
        self.global_tags = data.get("global_tags", {})

        if not self.boards:
            raise ValueError("At least one board must be configured")

        logger.info(f"Loaded config with {len(self.boards)} board(s)")


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    config = ThermoConfig("thermo_config.toml")

    watch_dir = Path(config.app.get("watch_dir", "/home/st/daq_incoming"))
    watch_dir.mkdir(parents=True, exist_ok=True)

    read_interval = config.app.get("read_interval", 60.0)
    samples_per_batch = config.app.get("samples_per_batch", 3)
    measurement_name = config.app.get("measurement_name", "thermocouple")

    logger.info("Starting MCC 134 Thermocouple Logger")
    logger.info(f"Watch dir: {watch_dir}")
    logger.info(f"Sampling every {read_interval}s, batching every {samples_per_batch} samples")

    # Initialize all boards
    boards = []
    for board_cfg in config.boards:
        try:
            hats = hat_list(filter_by_id=HatIDs.MCC_134)
            matching = [h for h in hats if h.address == board_cfg["address"]]
            if not matching:
                logger.error(f"Board address {board_cfg['address']} not found")
                continue

            board = mcc134(board_cfg["address"])

            # Configure TC types per channel
            channel_configs = board_cfg.get("channels", [])
            for ch_cfg in channel_configs:
                ch = ch_cfg["channel"]
                tc_str = ch_cfg.get("tc_type", "K")
                tc_type = getattr(TcTypes, f"TYPE_{tc_str.upper()}", TcTypes.TYPE_K)
                board.tc_type_write(ch, tc_type)
                logger.info(f"Board {board_cfg['address']} ch{ch} → Type {tc_str}")

            boards.append({
                "board": board,
                "address": board_cfg["address"],
                "tags": board_cfg.get("tags", {}),
                "channels": channel_configs
            })

        except Exception as e:
            logger.error(f"Failed to initialize board {board_cfg.get('address')}: {e}")

    if not boards:
        logger.error("No boards initialized. Exiting.")
        return

    # Start DAQIngestor
    async with DAQIngestor.from_config_file("data_config.toml") as ingestor:
        logger.info(f"DAQIngestor started — {len(boards)} board(s) active")

        batch: list[DataPoint] = []

        try:
            while True:
                sample_time = time.time()

                for board_info in boards:
                    board = board_info["board"]
                    base_tags = {**config.global_tags, **board_info["tags"], "board_address": board_info["address"]}

                    for ch_cfg in board_info["channels"]:
                        ch = ch_cfg["channel"]
                        ch_tags = {**base_tags, **ch_cfg.get("tags", {}), "channel": ch}

                        try:
                            temp = board.t_in_read(ch)
                            if temp == mcc134.OPEN_TC_VALUE:
                                temperature = None
                            else:
                                temperature = round(float(temp), 2)
                        except Exception as e:
                            logger.warning(f"Read error on board {board_info['address']} ch{ch}: {e}")
                            temperature = None

                        dp = DataPoint(
                            time=sample_time,
                            measurement=measurement_name,
                            tags=ch_tags,
                            fields={"temperature": temperature}
                        )
                        batch.append(dp)

                # Write batch when ready
                if len(batch) >= samples_per_batch * len(boards) * 4:  # 4 channels per board
                    filename = f"thermo_{int(sample_time)}.jsonl"
                    file_path = watch_dir / filename

                    content = "\n".join(dp.to_json() for dp in batch)
                    file_path.write_text(content + "\n", encoding="utf-8")

                    logger.info(f"Wrote batch of {len(batch)} DataPoints → {filename}")
                    batch.clear()

                await asyncio.sleep(read_interval)

        except KeyboardInterrupt:
            logger.info("Shutdown requested — exiting gracefully")
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
        finally:
            logger.info("Thermo logger stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except SystemExit:
        logger.info("System exit requested")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise