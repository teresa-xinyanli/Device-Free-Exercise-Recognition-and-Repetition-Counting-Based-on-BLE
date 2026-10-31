"""Version-2 ESP32-S3 USB protocol, independent of the GUI and Windows BLE APIs."""
from __future__ import annotations
from dataclasses import dataclass
import math
import re
import time

BAUD_RATE = 115200
MAC = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\Z")


@dataclass(frozen=True)
class Sample:
    source_time_s: float
    rssi_dbm: int
    device_id: str
    callback_seq: int
    queue_drops_total: int


def parse_sample(line):
    """Comments/boot text return None; malformed D rows raise instead of hiding data loss."""
    if not line.startswith("D,"):
        return None
    values = line.split(",")
    if len(values) != 6:
        raise ValueError("Malformed sample row (expected D,time_us,RSSI,MAC,seq,drops): " + line)
    try:
        source_us, rssi, seq, drops = (int(values[i]) for i in (1, 2, 4, 5))
    except ValueError as error:
        raise ValueError("Non-integer field in sample row: " + line) from error
    if source_us < 0 or not -126 <= rssi < 0 or seq < 1 or drops < 0 or not MAC.fullmatch(values[3]):
        raise ValueError("Invalid sample values: " + line)
    return Sample(source_us/1_000_000, rssi, values[3].lower(), seq, drops)


def open_port(port):
    import serial
    # Deassert boot/reset control lines before opening. Some USB bridges still reset on open;
    # the handshake tolerates normal startup and refuses a bootloader/wrong firmware.
    connection = serial.Serial()
    connection.port = port
    connection.baudrate = BAUD_RATE
    connection.timeout = 0.2
    connection.write_timeout = 1
    connection.dtr = False
    connection.rts = False
    connection.open()
    return connection


class ReceiverStream:
    def __init__(self, connection, stop_event, raw_file, status=None, target_mac=""):
        self.connection, self.stop_event, self.raw_file = connection, stop_event, raw_file
        self.status = status or (lambda value: None)
        self.target_mac = target_mac.strip().lower()
        if self.target_mac and not MAC.fullmatch(self.target_mac):
            raise ValueError("Target MAC must look like aa:bb:cc:dd:ee:ff, or be empty.")
        self.epoch_s = None
        self.last_source_s = None
        self.last_seq = None
        self.last_drops = None
        self.partial = bytearray()
        self.partial_started = None
        self.stats = dict(protocol=2, saved_packets=0, other_transmitter_packets=0,
                          callback_sequence_gaps=0, initial_queue_drops_total=None,
                          final_queue_drops_total=None, local_queue_drops_during_session=0,
                          note="Sequence gaps/local queue drops describe callback/USB transport, not over-the-air packet loss.")

    def line(self):
        data = self.connection.read_until(b"\n", size=512)
        if not data:
            if self.partial_started is not None and time.monotonic()-self.partial_started > 3:
                raise ValueError("Serial row incomplete for over 3 seconds. Check USB/baud/firmware; raw bytes saved.")
            return ""
        # Preserve exact received bytes even for invalid UTF-8 or truncated serial records.
        self.raw_file.write(data)
        self.raw_file.flush()
        if not self.partial:
            self.partial_started = time.monotonic()
        self.partial.extend(data)
        if len(self.partial) >= 512:
            raise ValueError("Serial row too long. Check firmware/baud; raw bytes saved.")
        if not self.partial.endswith(b"\n"):
            return ""
        line = self.partial.decode("utf-8", errors="replace").strip()
        self.partial.clear()
        self.partial_started = None
        return line

    def check_hello(self, line):
        if line.startswith("#ERROR"):
            raise RuntimeError("Receiver firmware: " + line)
        if not line.startswith("#HELLO,"):
            return False
        fields = line.split(",")
        if len(fields) >= 2 and fields[1] == "TX":
            raise RuntimeError("You selected transmitter A. Select receiver B's COM port.")
        if len(fields) != 5 or fields[1:4] != ["RX", "2", "ESP32-S3"]:
            raise RuntimeError("Wrong firmware/protocol. Upload this package's ESP32S3_RX sketch to board B.")
        if fields[4] != "OK":
            raise RuntimeError("Receiver BLE scan did not start. Reset board B and check firmware settings.")
        return True

    def handshake(self, timeout=12):
        self.connection.reset_input_buffer()
        deadline = time.monotonic()+timeout
        sent_at, found_rx = -math.inf, False
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            now = time.monotonic()
            if now-sent_at >= 1:
                self.connection.write(b"START\n" if found_rx else b"INFO\n")
                self.connection.flush()
                sent_at = now
            line = self.line()
            if self.check_hello(line) and not found_rx:
                found_rx = True
                sent_at = -math.inf
                self.status("Receiver B identified; starting a fresh device-clock session...")
            if found_rx and line.startswith("#SESSION,"):
                parts = line.split(",")
                if len(parts) != 3 or parts[2] != "2":
                    raise ValueError("Invalid START acknowledgment.")
                epoch_us = int(parts[1])
                if epoch_us < 0:
                    raise ValueError("Invalid receiver epoch.")
                self.epoch_s = epoch_us/1_000_000
                return self.epoch_s
        if self.stop_event.is_set():
            return None
        raise TimeoutError("No ESP32-S3 RX v2 handshake within 12 s. Close Serial Monitor; check B's COM port and SerialCheck/USB settings.")

    def next_sample(self):
        line = self.line()
        self.check_hello(line)
        if line.startswith("#SESSION,"):
            raise RuntimeError("Unexpected new receiver session. Start a separate recording.")
        row = parse_sample(line)
        if row is None:
            return None
        if self.epoch_s is None:
            raise RuntimeError("Handshake required before reading samples.")
        if row.source_time_s < self.epoch_s:
            raise RuntimeError("Receiver restarted during capture. Partial data saved; start a new session.")
        if not self.target_mac:
            self.target_mac = row.device_id
            self.status("Locked to TX " + self.target_mac)
        if row.device_id != self.target_mac:
            self.stats["other_transmitter_packets"] += 1
            return None
        if self.last_source_s is not None and row.source_time_s <= self.last_source_s:
            raise ValueError("Receiver timestamps repeated or went backwards; recording stopped.")
        if self.last_seq is not None:
            if row.callback_seq <= self.last_seq or row.queue_drops_total < self.last_drops:
                raise RuntimeError("Receiver sequence/counter reset. Start a new recording.")
            self.stats["callback_sequence_gaps"] += row.callback_seq-self.last_seq-1
        else:
            self.stats["initial_queue_drops_total"] = row.queue_drops_total
        self.last_source_s, self.last_seq, self.last_drops = row.source_time_s, row.callback_seq, row.queue_drops_total
        self.stats["saved_packets"] += 1
        self.stats["final_queue_drops_total"] = row.queue_drops_total
        self.stats["local_queue_drops_during_session"] = row.queue_drops_total-self.stats["initial_queue_drops_total"]
        return row
