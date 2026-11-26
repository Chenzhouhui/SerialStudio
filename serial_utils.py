"""Protocol, encoding, checksum, and waveform parsing utilities for the serial debugger."""

from __future__ import annotations

import re
import struct
from typing import Iterable

JUSTFLOAT_TAIL = b"\x00\x00\x80\x7f"
_NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")


def parse_hex_string(text: str) -> bytes:
    """Parse a flexible hex string (e.g. 'AA 55 01', '0xAA,0x55', 'AA55') into bytes."""
    cleaned = re.sub(r"0[xX]", "", text)
    cleaned = re.sub(r"[\s,;]+", "", cleaned)
    if not cleaned:
        return b""
    if len(cleaned) % 2 != 0:
        raise ValueError("HEX 字符串长度必须为偶数（每个字节 2 位十六进制数）")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError(f"包含无效的十六进制字符: {text!r}") from exc


def format_hex_bytes(data: bytes) -> str:
    """Format bytes as uppercase space-separated hex pairs."""
    return " ".join(f"{b:02X}" for b in data)


def crc16_modbus(data: bytes) -> bytes:
    """Compute standard Modbus CRC-16 (poly 0xA001, init 0xFFFF) as 2 little-endian bytes."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return struct.pack("<H", crc)


def checksum8(data: bytes) -> bytes:
    """Compute 8-bit arithmetic sum checksum."""
    return bytes([sum(data) & 0xFF])


def xor_checksum(data: bytes) -> bytes:
    """Compute 8-bit XOR checksum."""
    acc = 0
    for b in data:
        acc ^= b
    return bytes([acc])


def apply_checksum(data: bytes, mode: str) -> bytes:
    """Append the selected checksum to data."""
    if not data or mode in ("无", "None", ""):
        return data
    if mode == "CRC16-Modbus":
        return data + crc16_modbus(data)
    if mode == "Sum8":
        return data + checksum8(data)
    if mode == "XOR8":
        return data + xor_checksum(data)
    raise ValueError(f"不支持的校验模式: {mode}")


def apply_line_ending(data: bytes, ending: str) -> bytes:
    """Append line ending bytes based on UI selection."""
    mapping = {
        "无": b"",
        "CRLF (\\r\\n)": b"\r\n",
        "LF (\\n)": b"\n",
        "CR (\\r)": b"\r",
    }
    return data + mapping.get(ending, b"")


def parse_waveform_line(line: str) -> list[float] | None:
    """Parse a text line (CSV or VOFA+ FireWater 'ch0:1.2,ch1:3.4') into float values."""
    stripped = line.strip()
    if not stripped:
        return None
    # Strip optional prefix like "data:" before numbers if it looks like FireWater
    if ":" in stripped and "," not in stripped:
        stripped = stripped.split(":", 1)[1]
    parts = [p.strip() for p in re.split(r"[,;\t ]+", stripped) if p.strip()]
    values: list[float] = []
    for part in parts:
        # Handle key:value pairs like "temp:25.3"
        if ":" in part:
            part = part.split(":", 1)[1].strip()
        match = _NUMBER_RE.fullmatch(part)
        if not match:
            return None
        values.append(float(match.group(0)))
    return values if values else None


def parse_justfloat_frames(buffer: bytearray) -> tuple[list[list[float]], bytearray]:
    """Extract complete VOFA+ JustFloat frames (N * float32 + 0x00 0x00 0x80 0x7F) from buffer."""
    frames: list[list[float]] = []
    search_start = 0
    while True:
        idx = buffer.find(JUSTFLOAT_TAIL, search_start)
        if idx == -1:
            break
        payload = bytes(buffer[search_start:idx])
        search_start = idx + len(JUSTFLOAT_TAIL)
        if payload and len(payload) % 4 == 0:
            count = len(payload) // 4
            if count <= 32:
                vals = list(struct.unpack(f"<{count}f", payload))
                frames.append(vals)
    remaining = bytearray(buffer[search_start:])
    # Prevent unbounded growth on garbage binary streams
    if len(remaining) > 4096:
        remaining = remaining[-1024:]
    return frames, remaining
