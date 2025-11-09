from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional


class VLCInterface:
    """Stub implementation that will later talk to the physical VLC device."""

    def __init__(self, *, config: Dict[str, int | str], port: Optional[str] = None) -> None:
        self.config = config
        self.port = port
        self._logger = logging.getLogger(__name__)
        self._message_callbacks: List[Callable[[str, str, Optional[dict]], None]] = []
        self._stats_callbacks: List[Callable[[dict], None]] = []
        self._started = False
        self._ack_callbacks: List[Callable[[str, str], None]] = []

    def start(self) -> None:
        if self._started:
            return
        self._logger.info("Starting VLC interface (stub). Config: %s", self.config)
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._logger.info("Stopping VLC interface (stub).")
        self._started = False

    def register_message_callback(self, callback: Callable[[str, str, Optional[dict]], None]) -> None:
        self._message_callbacks.append(callback)

    def register_statistics_callback(self, callback: Callable[[dict], None]) -> None:
        self._stats_callbacks.append(callback)

    def register_ack_callback(self, callback: Callable[[str, str], None]) -> None:
        self._ack_callbacks.append(callback)

    def send_message(self, *, dest_mac: str, message: str) -> None:
        if not self._started:
            raise RuntimeError("VLC interface not started.")
        payload = message + "\0"
        if len(payload) > 200:
            raise ValueError("Message payload exceeds 200 character limit required by the VLC device.")
        self._logger.info("Dispatching message to %s: %s", dest_mac, message)
        # Real implementation will format and forward the serial command here.

    # Helper for tests/manual simulation.
    def simulate_incoming_message(self, mac: str, message: str, stats: Optional[dict] = None) -> None:
        for callback in self._message_callbacks:
            callback(mac, message, stats)
        if stats:
            for cb in self._stats_callbacks:
                cb(stats)

    def simulate_ack(self, mac: str, timestamp: str) -> None:
        for callback in self._ack_callbacks:
            callback(mac, timestamp)
