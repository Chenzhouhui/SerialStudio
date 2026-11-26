"""Thread-safe serial port manager with pyserial backend and built-in simulation mode."""

from __future__ import annotations

import math
import queue
import struct
import threading
import time
from dataclasses import dataclass
from typing import Optional

import serial
import serial.tools.list_ports

from serial_utils import JUSTFLOAT_TAIL

SIM_PORT_ID = "__SIM_PORT__"


@dataclass
class PortInfo:
    device: str
    description: str

    @property
    def display_name(self) -> str:
        if self.device == SIM_PORT_ID:
            return "模拟串口 (内置波形与回环测试)"
        return f"{self.device} - {self.description}" if self.description else self.device


class SerialManager:
    """Manages serial connection lifecycle, async reading, and DTR/RTS control."""

    def __init__(self) -> None:
        self._ser: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._sim_mode = False
        self._sim_wave_enabled = True
        self.rx_queue: queue.Queue[tuple[float, bytes]] = queue.Queue()

    @staticmethod
    def list_ports(include_sim: bool = True) -> list[PortInfo]:
        ports = [
            PortInfo(device=p.device, description=p.description or "")
            for p in sorted(serial.tools.list_ports.comports(), key=lambda x: x.device)
        ]
        if include_sim:
            ports.append(PortInfo(device=SIM_PORT_ID, description="Virtual Loopback & Waveform"))
        return ports

    @property
    def is_open(self) -> bool:
        if self._sim_mode:
            return not self._stop_event.is_set()
        return self._ser is not None and self._ser.is_open

    @property
    def is_sim_mode(self) -> bool:
        return self._sim_mode

    def open(
        self,
        port: str,
        baudrate: int = 115200,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        flow_control: str = "无",
        dtr: bool = False,
        rts: bool = False,
    ) -> None:
        self.close()
        self._stop_event.clear()

        if port == SIM_PORT_ID:
            self._sim_mode = True
            self._thread = threading.Thread(target=self._sim_loop, daemon=True)
            self._thread.start()
            return

        self._sim_mode = False
        parity_map = {
            "N": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
            "M": serial.PARITY_MARK,
            "S": serial.PARITY_SPACE,
        }
        stopbits_map = {
            1: serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            2: serial.STOPBITS_TWO,
        }

        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baudrate
        ser.bytesize = bytesize
        ser.parity = parity_map.get(parity, serial.PARITY_NONE)
        ser.stopbits = stopbits_map.get(stopbits, serial.STOPBITS_ONE)
        ser.timeout = 0.05
        ser.rtscts = flow_control == "RTS/CTS"
        ser.xonxoff = flow_control == "XON/XOFF"
        ser.dtr = dtr
        ser.rts = rts
        ser.open()

        self._ser = ser
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
        self._sim_mode = False
        with self._lock:
            if self._ser is not None:
                try:
                    if self._ser.is_open:
                        self._ser.close()
                except Exception:
                    pass
                self._ser = None

    def set_dtr(self, value: bool) -> None:
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.dtr = value

    def set_rts(self, value: bool) -> None:
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.rts = value

    def set_sim_wave(self, enabled: bool) -> None:
        self._sim_wave_enabled = enabled

    def write(self, data: bytes) -> int:
        if not data:
            return 0
        if self._sim_mode:
            # Echo back in simulation mode (or respond to AT)
            if data.strip().upper() == b"AT":
                self.rx_queue.put((time.time(), b"OK\r\n"))
            else:
                self.rx_queue.put((time.time(), data))
            return len(data)
        with self._lock:
            if not self._ser or not self._ser.is_open:
                raise RuntimeError("串口未打开")
            return self._ser.write(data)

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                ser = self._ser
                if ser is None or not ser.is_open:
                    break
                waiting = ser.in_waiting
                chunk = ser.read(waiting if waiting > 0 else 1)
                if chunk:
                    self.rx_queue.put((time.time(), chunk))
            except serial.SerialException as exc:
                self.rx_queue.put((time.time(), f"\r\n[串口错误] {exc}\r\n".encode("utf-8", errors="replace")))
                self._stop_event.set()
                break
            except Exception:
                break

    def _sim_loop(self) -> None:
        t = 0.0
        while not self._stop_event.is_set():
            if self._sim_wave_enabled:
                ch0 = math.sin(t) * 10.0 + 12.0
                ch1 = math.cos(t * 0.7) * 6.0 + 12.0
                ch2 = ((t % 6.28) / 6.28) * 15.0
                line = f"{ch0:.2f},{ch1:.2f},{ch2:.2f}\r\n".encode("ascii")
                self.rx_queue.put((time.time(), line))
                t += 0.2
            time.sleep(0.08)
