from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from history import History
from gui.app import ChatApp
from vlc_interface import VLCInterface

CONFIG_PATH = Path(".data") / "config.json"


def load_config(path: str | Path = CONFIG_PATH) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Missing configuration file: {path}")

    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in configuration file: {path}") from exc

    required_fields = ["MAC", "FEC_THRESHOLD", "CHANNEL_BUSY_THRESHOLD", "N_RETRANSMISSIONS"]
    for field in required_fields:
        if field not in config:
            raise KeyError(f"Configuration missing required field '{field}'.")

    mac = str(config["MAC"]).strip()
    if not mac:
        raise ValueError("MAC address in configuration must not be empty.")
    config["MAC"] = mac.upper()
    return config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    config = load_config()
    history = History()
    vlc_interface = VLCInterface(config=config)
    recv_color = config.get("RECV_COLOR", "black")
    app = ChatApp(history=history, vlc_interface=vlc_interface, local_mac=config["MAC"], recv_color=recv_color)

    try:
        vlc_interface.start()
        app.run()
    finally:
        vlc_interface.stop()


if __name__ == "__main__":
    main()
