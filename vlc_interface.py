from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, List, Optional
import serial


class VLCInterface:
    """Handles the serial protocol for ETH's VLC boards."""

    BAUD_RATE = 115200
    READ_TIMEOUT = 0.2      # seconds after reading from serial
    STARTUP_DELAY = 2.0     # seconds after writing the config params
    COMMAND_PAUSE = 0.1     # seconds after commands
    MAX_PAYLOAD = 200

    def __init__(self, *, config: Dict[str, int | str], port: Optional[str] = None) -> None:
        if serial is None:
            raise ImportError("pyserial is required to use VLCInterface. Install it via 'pip install pyserial'.")

        self.config = config
        self.port = port
        self._serial: Optional[Serial] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._logger = logging.getLogger(__name__)

        self._message_callbacks: List[Callable[[str, str, Optional[dict]], None]] = []
        self._stats_callbacks: List[Callable[[dict], None]] = []
        self._ack_callbacks: List[Callable[[str, str], None]] = []

        self._pending_rx: Deque[dict] = deque()
        self._pending_acks: Dict[str, Deque[str]] = defaultdict(deque)
        self._acks_lock = threading.Lock()
        self._started = False

    # ------------------------------------------------------------------ Lifecycle
    def start(self) -> None:
        if self._started:
            return

        port = self._determine_port()
        self._logger.info("Opening serial port %s @ %s baud...", port, self.BAUD_RATE)

        try:
            self._serial = serial.Serial(port, self.BAUD_RATE, timeout=self.READ_TIMEOUT)
        except SerialException as exc:  # pragma: no cover - hardware dependent
            raise RuntimeError(f"Unable to open serial port {port}: {exc}") from exc

        time.sleep(self.STARTUP_DELAY)  # device resets when the port opens
        self._configure_device()
        self._serial.reset_input_buffer()

        self._stop_event.clear()
        self._reader_thread = threading.Thread(target=self._reader_loop, name="VLCSerialReader", daemon=True)
        self._reader_thread.start()
        self._started = True
        self._logger.info("VLC interface ready.")

    def stop(self) -> None:
        if not self._started:
            return
        self._stop_event.set()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2)
        if self._serial:
            self._serial.close()
            self._serial = None
        self._started = False
        self._logger.info("VLC interface stopped.")

    # ------------------------------------------------------------------ Registration
    def register_message_callback(self, callback: Callable[[str, str, Optional[dict]], None]) -> None:
        self._message_callbacks.append(callback)

    def register_statistics_callback(self, callback: Callable[[dict], None]) -> None:
        self._stats_callbacks.append(callback)

    def register_ack_callback(self, callback: Callable[[str, str], None]) -> None:
        self._ack_callbacks.append(callback)

    # ------------------------------------------------------------------ Sending
    def send_message(self, *, dest_mac: str, message: str, timestamp: datetime) -> None:
        if not self._started or not self._serial:
            raise RuntimeError("VLC interface not started.")

        dest = dest_mac.strip().upper()
        if not dest:
            raise ValueError("Destination MAC must not be empty.")

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        ts_iso = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

        if len(message) + 1 > self.MAX_PAYLOAD:
            raise ValueError(f"Message payload exceeds {self.MAX_PAYLOAD} character limit required by the VLC device.")
        try:
            message.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("Messages must be ASCII.") from exc

        escaped = _escape_payload(message)
        payload = f"m[{escaped}\0,{dest}]"
        self._send_command(payload)

        with self._acks_lock:
            self._pending_acks[dest].append(ts_iso)

        self._logger.info("Queued TX -> %s (%s chars)", dest, len(message))

    # ------------------------------------------------------------------ Internal helpers
    def _determine_port(self) -> str:
        if self.port:
            return self.port
        cfg_port = self.config.get("SERIAL_PORT")
        if isinstance(cfg_port, str) and cfg_port.strip():
            return cfg_port.strip()
        raise ValueError(
            "Serial port not specified. Provide it when instantiating VLCInterface, "
            "set config['SERIAL_PORT'], or define the VLC_SERIAL_PORT environment variable."
        )

    def _configure_device(self) -> None:
        mac = str(self.config.get("MAC", "")).strip().upper()
        if not mac:
            raise ValueError("Device MAC address is missing from the configuration.")

        self._logger.info("Configuring VLC device with MAC %s", mac)
        self._send_command(f"a[{mac}]")
        time.sleep(self.COMMAND_PAUSE)

        n_retries = int(self.config.get("N_RETRANSMISSIONS", 0))
        self._send_command(f"c[1,0,{n_retries}]")
        time.sleep(self.COMMAND_PAUSE)

        fec_threshold = max(10, int(self.config.get("FEC_THRESHOLD", 30)))
        self._send_command(f"c[0,1,{fec_threshold}]")
        time.sleep(self.COMMAND_PAUSE)

        busy_threshold = int(self.config.get("CHANNEL_BUSY_THRESHOLD", 20))
        self._send_command(f"c[0,2,{busy_threshold}]")
        time.sleep(self.COMMAND_PAUSE)

    def _send_command(self, command: str) -> None:
        if not self._serial:
            raise RuntimeError("Serial connection not established.")
        payload = f"{command}\n".encode("ascii")
        self._serial.write(payload)
        self._serial.flush()
        self._logger.debug("SERIAL >> %s", command)

    # ------------------------------------------------------------------ Reader loop
    def _reader_loop(self) -> None:  # pragma: no cover - hardware dependent
        assert self._serial is not None
        while not self._stop_event.is_set():
            try:
                raw = self._serial.readline()
            except SerialException as exc:
                self._logger.error("Serial read error: %s", exc)
                break

            if not raw:
                continue

            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            self._logger.debug("SERIAL << %s", line)
            try:
                self._process_line(line)
            except Exception:  # pragma: no cover - defensive
                self._logger.exception("Failed to process serial line: %s", line)

        self._stop_event.set()

    def _process_line(self, line: str) -> None:
        if line.startswith("m["):
            self._handle_message_event(line)
        elif line.startswith("s["):
            self._handle_stats_event(line)
        else:
            self._logger.debug("Ignoring line: %s", line)

    def _handle_message_event(self, line: str) -> None:
        inner = _strip_brackets(line)
        if not inner:
            return

        if inner.startswith("R,"):
            parts = inner.split(",", 2)
            if len(parts) < 3:
                return
            payload = parts[2]
            message = _sanitize_payload(payload)
            self._pending_rx.append({"message": message, "raw": payload, "received_at": datetime.now(timezone.utc)})
        elif inner.startswith("P,"):
            parts = inner.split(",", 2)
            if len(parts) < 3:
                return
            status = parts[1]
            mac = parts[2].strip().upper()
            self._handle_ack_update(mac, status == "1")
        else:
            self._logger.debug("Unhandled message event: %s", inner)

    def _handle_ack_update(self, mac: str, success: bool) -> None:
        timestamp_iso: Optional[str] = None
        with self._acks_lock:
            queue = self._pending_acks.get(mac)
            if queue:
                timestamp_iso = queue.popleft()
                if not queue:
                    self._pending_acks.pop(mac, None)

        if not timestamp_iso:
            self._logger.warning("Ack event for %s with no pending messages (success=%s)", mac, success)
            return

        if success:
            for callback in self._ack_callbacks:
                callback(mac, timestamp_iso)
        else:
            self._logger.warning("Device reported drop for %s @ %s", mac, timestamp_iso)

    def _handle_stats_event(self, line: str) -> None:
        inner = _strip_brackets(line)
        if not inner:
            return

        fields = inner.split(",")
        if len(fields) < 2:
            return
        stats = _parse_stats(fields)
        stats["raw"] = line

        if stats.get("mode") == "R" and self._pending_rx:
            pending = self._pending_rx.popleft()
            src = stats.get("src") or stats.get("dest") or ""
            for callback in self._message_callbacks:
                callback(src, pending["message"], stats)

        for cb in self._stats_callbacks:
            cb(stats)


# ---------------------------------------------------------------------- Utility helpers
def _strip_brackets(line: str) -> str:
    if line.endswith("]") and "[" in line:
        start = line.find("[")
        return line[start + 1 : -1]
    start = line.find("[")
    return line[start + 1 :] if start >= 0 else line


def _escape_payload(message: str) -> str:
    return (
        message.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _sanitize_payload(payload: str) -> str:
    text = payload.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
    text = text.replace("\\0", "")
    text = text.replace("\0", "")
    return text


def _parse_stats(fields: List[str]) -> Dict[str, object]:
    stats: Dict[str, object] = {
        "mode": fields[0],
        "type": fields[1] if len(fields) > 1 else "",
    }
    if len(fields) > 2:
        path = fields[2]
        stats["path"] = path
        src, dest = _split_path(path)
        if src:
            stats["src"] = src
        if dest:
            stats["dest"] = dest
    if len(fields) > 3:
        size, txsize = _parse_size_field(fields[3])
        stats["size"] = size
        stats["tx_size"] = txsize
    if len(fields) > 4:
        stats["seq"] = _safe_int(fields[4])
    if len(fields) > 5:
        stats["cw"] = _safe_int(fields[5])
    if len(fields) > 6:
        stats["cw_size"] = _safe_int(fields[6])
    if len(fields) > 7:
        stats["dispatch_ms"] = _safe_float(fields[7])
    if len(fields) > 8:
        stats["timestamp_ms"] = _safe_float(fields[8])
    return stats


def _split_path(path: str) -> tuple[Optional[str], Optional[str]]:
    if "->" not in path:
        return path.strip(), None
    src, dest = path.split("->", 1)
    return src.strip(), dest.strip()


def _parse_size_field(field: str) -> tuple[Optional[int], Optional[int]]:
    if "(" in field and field.endswith(")"):
        size_part, tx_part = field.split("(", 1)
        tx_part = tx_part[:-1]
        return _safe_int(size_part), _safe_int(tx_part)
    return _safe_int(field), None


def _safe_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
