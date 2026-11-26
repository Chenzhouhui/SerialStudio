"""Modern pywebview desktop application bridging HTML5 UI with SerialManager."""

from __future__ import annotations

import json
import pathlib
import queue
import sys
from datetime import datetime
from typing import Any

import webview

from serial_manager import SIM_PORT_ID, SerialManager
from serial_utils import (
    apply_checksum,
    apply_line_ending,
    format_hex_bytes,
    parse_hex_string,
    parse_justfloat_frames,
    parse_waveform_line,
)

if getattr(sys, "frozen", False):
    _BUNDLE_DIR = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(sys.executable).parent))
    _APP_DIR = pathlib.Path(sys.executable).parent
else:
    _BUNDLE_DIR = pathlib.Path(__file__).parent
    _APP_DIR = pathlib.Path(__file__).parent

UI_HTML_PATH = _BUNDLE_DIR / "ui" / "index.html"
APP_ICON_PATH = _BUNDLE_DIR / "assets" / "app.ico"
CONFIG_PATH = _APP_DIR / "quick_commands.json"

DEFAULT_QUICK_COMMANDS = [
    {"name": "AT 测试", "payload": "AT", "hex": False, "ending": "CRLF (\\r\\n)"},
    {"name": "ESP 复位", "payload": "AT+RST", "hex": False, "ending": "CRLF (\\r\\n)"},
    {"name": "查询版本", "payload": "AT+GMR", "hex": False, "ending": "CRLF (\\r\\n)"},
    {"name": "Modbus 读寄存器", "payload": "01 03 00 00 00 02", "hex": True, "ending": "无"},
    {"name": "LED 开启帧", "payload": "AA 55 01 01", "hex": True, "ending": "无"},
    {"name": "LED 关闭帧", "payload": "AA 55 01 00", "hex": True, "ending": "无"},
]


class SerialWebAPI:
    """JS-callable Python API exposed to pywebview.

    NOTE: Keep internal objects (_manager, _window) private with a leading underscore
    so pywebview's inject_pywebview() does not recursively traverse WinForms Window
    properties on a background thread (which causes STA deadlocks on startup).
    """

    def __init__(self) -> None:
        self._manager = SerialManager()
        self._window: webview.Window | None = None
        self._maximized = False
        self._text_wave_buf = ""
        self._bin_wave_buf = bytearray()

    def win_minimize(self) -> None:
        if self._window:
            self._window.minimize()

    def win_toggle_maximize(self) -> dict[str, bool]:
        if self._window:
            if self._maximized:
                self._window.restore()
                self._maximized = False
            else:
                self._window.maximize()
                self._maximized = True
        return {"maximized": self._maximized}

    def win_close(self) -> None:
        if self._window:
            self._window.destroy()

    def list_ports(self) -> list[dict[str, str]]:
        return [
            {
                "device": p.device,
                "description": p.description,
                "display_name": p.display_name,
            }
            for p in self._manager.list_ports(include_sim=True)
        ]

    def open_port(self, cfg: dict[str, Any]) -> dict[str, Any]:
        try:
            device = str(cfg.get("port", "")).strip()
            if not device:
                return {"ok": False, "error": "请先选择一个串口"}
            baud = int(cfg.get("baudrate", 115200))
            bytesize = int(cfg.get("bytesize", 8))
            parity = str(cfg.get("parity", "N"))
            stopbits = float(cfg.get("stopbits", 1))
            if stopbits == 1.0:
                stopbits = 1
            elif stopbits == 2.0:
                stopbits = 2
            flow = str(cfg.get("flow_control", "无"))
            dtr = bool(cfg.get("dtr", False))
            rts = bool(cfg.get("rts", False))

            self._manager.open(
                port=device,
                baudrate=baud,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                flow_control=flow,
                dtr=dtr,
                rts=rts,
            )
            label = "模拟测试模式" if device == SIM_PORT_ID else f"{device} · {baud} {bytesize}{parity}{stopbits}"
            return {"ok": True, "label": label}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def close_port(self) -> dict[str, Any]:
        self._manager.close()
        return {"ok": True}

    def set_dtr(self, value: bool) -> None:
        self._manager.set_dtr(bool(value))

    def set_rts(self, value: bool) -> None:
        self._manager.set_rts(bool(value))

    def send_data(self, raw_text: str, use_hex: bool, ending: str, checksum: str) -> dict[str, Any]:
        if not self._manager.is_open:
            return {"ok": False, "error": "串口未打开"}
        try:
            data = parse_hex_string(raw_text) if use_hex else raw_text.encode("utf-8")
            data = apply_checksum(data, checksum)
            data = apply_line_ending(data, ending)
            if not data:
                return {"ok": True, "sent_bytes": 0, "display_text": "", "ts": ""}
            sent = self._manager.write(data)
            shown = format_hex_bytes(data) if use_hex else data.decode("utf-8", errors="replace").rstrip("\r\n")
            ts_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            return {"ok": True, "sent_bytes": sent, "display_text": shown, "ts": ts_str}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def poll_rx(self, rx_hex: bool, rx_newline: bool, wave_protocol: str) -> dict[str, Any]:
        entries: list[dict[str, str]] = []
        waves: list[list[float]] = []
        rx_delta = 0

        try:
            for _ in range(120):
                ts, chunk = self._manager.rx_queue.get_nowait()
                rx_delta += len(chunk)
                ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3]

                if rx_hex:
                    display = format_hex_bytes(chunk)
                else:
                    display = chunk.decode("utf-8", errors="replace")
                    if rx_newline:
                        display = display.rstrip("\r\n")
                entries.append({"ts": ts_str, "text": display})

                if wave_protocol.startswith("JustFloat"):
                    self._bin_wave_buf.extend(chunk)
                    frames, self._bin_wave_buf = parse_justfloat_frames(self._bin_wave_buf)
                    waves.extend(frames)
                else:
                    self._text_wave_buf += chunk.decode("utf-8", errors="ignore")
                    while "\n" in self._text_wave_buf:
                        line, self._text_wave_buf = self._text_wave_buf.split("\n", 1)
                        vals = parse_waveform_line(line)
                        if vals:
                            waves.append(vals)
                    if len(self._text_wave_buf) > 2048:
                        self._text_wave_buf = self._text_wave_buf[-512:]
        except queue.Empty:
            pass

        return {"entries": entries, "waves": waves, "rx_bytes_delta": rx_delta}

    def save_log(self, content: str) -> dict[str, Any]:
        if not self._window:
            return {"ok": False, "error": "窗口未就绪"}
        dialog_type = getattr(webview, "FileDialog", None)
        save_mode = dialog_type.SAVE if dialog_type is not None else webview.SAVE_DIALOG
        result = self._window.create_file_dialog(
            save_mode,
            save_filename=f"serial_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            file_types=("文本文件 (*.txt)", "所有文件 (*.*)"),
        )
        if not result:
            return {"ok": False, "path": ""}
        target = result[0] if isinstance(result, (list, tuple)) else str(result)
        pathlib.Path(target).write_text(content, encoding="utf-8")
        return {"ok": True, "path": target}

    def load_quick_commands(self) -> list[dict[str, Any]]:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
        return [dict(item) for item in DEFAULT_QUICK_COMMANDS]

    def save_quick_commands(self, cmds: list[dict[str, Any]]) -> dict[str, Any]:
        CONFIG_PATH.write_text(json.dumps(cmds, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}

    def reset_quick_commands(self) -> list[dict[str, Any]]:
        return [dict(item) for item in DEFAULT_QUICK_COMMANDS]


def launch() -> None:
    api = SerialWebAPI()
    window = webview.create_window(
        "SerialStudio · 嵌入式串口调试助手",
        url=UI_HTML_PATH.as_uri(),
        js_api=api,
        width=1220,
        height=780,
        min_size=(980, 640),
        frameless=True,
        easy_drag=False,
        background_color="#090d16",
    )
    api._window = window
    try:
        icon_arg = str(APP_ICON_PATH) if APP_ICON_PATH.exists() else None
        webview.start(gui="edgechromium", icon=icon_arg)
    finally:
        api._manager.close()
