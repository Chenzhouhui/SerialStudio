"""Unit tests for serial_utils and SerialManager simulation mode."""

from __future__ import annotations

import pathlib
import struct
import sys
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from serial_manager import SIM_PORT_ID, SerialManager
from serial_utils import (
    JUSTFLOAT_TAIL,
    apply_checksum,
    apply_line_ending,
    checksum8,
    crc16_modbus,
    format_hex_bytes,
    parse_hex_string,
    parse_justfloat_frames,
    parse_waveform_line,
    xor_checksum,
)


class TestSerialUtils(unittest.TestCase):
    def test_parse_and_format_hex(self) -> None:
        raw = parse_hex_string("aa 55 0x01, 02;0F")
        self.assertEqual(raw, b"\xaa\x55\x01\x02\x0f")
        self.assertEqual(format_hex_bytes(raw), "AA 55 01 02 0F")
        self.assertEqual(parse_hex_string("   "), b"")
        with self.assertRaises(ValueError):
            parse_hex_string("AAB")
        with self.assertRaises(ValueError):
            parse_hex_string("ZZ")

    def test_checksums(self) -> None:
        # Standard Modbus RTU query: 01 03 00 00 00 02 -> CRC = C4 0B
        frame = bytes.fromhex("01 03 00 00 00 02")
        self.assertEqual(crc16_modbus(frame), b"\xc4\x0b")
        self.assertEqual(apply_checksum(frame, "CRC16-Modbus"), frame + b"\xc4\x0b")
        self.assertEqual(checksum8(b"\x01\x02\xff"), b"\x02")
        self.assertEqual(xor_checksum(b"\xaa\x55\xff"), b"\x00")
        self.assertEqual(apply_checksum(frame, "无"), frame)

    def test_line_ending(self) -> None:
        self.assertEqual(apply_line_ending(b"AT", "CRLF (\\r\\n)"), b"AT\r\n")
        self.assertEqual(apply_line_ending(b"AT", "LF (\\n)"), b"AT\n")
        self.assertEqual(apply_line_ending(b"AT", "CR (\\r)"), b"AT\r")
        self.assertEqual(apply_line_ending(b"AT", "无"), b"AT")

    def test_waveform_parsers(self) -> None:
        self.assertEqual(parse_waveform_line("1.5, -2.25, 3.0\r\n"), [1.5, -2.25, 3.0])
        self.assertEqual(parse_waveform_line("ch0:10.5, ch1:20.0"), [10.5, 20.0])
        self.assertEqual(parse_waveform_line("d:3.14"), [3.14])
        self.assertIsNone(parse_waveform_line("OK"))
        self.assertIsNone(parse_waveform_line(""))

    def test_justfloat_frames(self) -> None:
        f1 = struct.pack("<2f", 1.25, -3.5) + JUSTFLOAT_TAIL
        f2 = struct.pack("<3f", 0.0, 2.0, 4.0) + JUSTFLOAT_TAIL
        buf = bytearray(f1 + f2 + b"\x01\x02")
        frames, rem = parse_justfloat_frames(buf)
        self.assertEqual(len(frames), 2)
        self.assertAlmostEqual(frames[0][0], 1.25, places=5)
        self.assertAlmostEqual(frames[0][1], -3.5, places=5)
        self.assertAlmostEqual(frames[1][2], 4.0, places=5)
        self.assertEqual(rem, bytearray(b"\x01\x02"))


class TestSerialManagerSim(unittest.TestCase):
    def test_sim_port_echo_and_at(self) -> None:
        mgr = SerialManager()
        ports = mgr.list_ports(include_sim=True)
        self.assertTrue(any(p.device == SIM_PORT_ID for p in ports))

        mgr.open(SIM_PORT_ID)
        mgr.set_sim_wave(False)
        self.assertTrue(mgr.is_open)
        mgr.write(b"AT\r\n")
        time.sleep(0.05)
        items = []
        while not mgr.rx_queue.empty():
            items.append(mgr.rx_queue.get_nowait()[1])
        self.assertIn(b"OK\r\n", items)
        mgr.close()
        self.assertFalse(mgr.is_open)


class TestSerialWebAPI(unittest.TestCase):
    def test_web_api_flow_and_ui_exists(self) -> None:
        from web_app import APP_ICON_PATH, UI_HTML_PATH, SerialWebAPI

        self.assertTrue(UI_HTML_PATH.exists())
        self.assertTrue(APP_ICON_PATH.exists())
        api = SerialWebAPI()
        self.assertFalse(hasattr(api, "window"))
        self.assertFalse(hasattr(api, "manager"))

        ports = api.list_ports()
        self.assertTrue(any(p["device"] == SIM_PORT_ID for p in ports))

        open_res = api.open_port({"port": SIM_PORT_ID})
        self.assertTrue(open_res["ok"])
        api._manager.set_sim_wave(False)

        send_res = api.send_data("AT", False, "CRLF (\\r\\n)", "无")
        self.assertTrue(send_res["ok"])
        self.assertGreater(send_res["sent_bytes"], 0)

        time.sleep(0.05)
        poll_res = api.poll_rx(False, True, "文本 CSV / FireWater")
        self.assertTrue(any(e["text"] == "OK" for e in poll_res["entries"]))

        close_res = api.close_port()
        self.assertTrue(close_res["ok"])


if __name__ == "__main__":
    unittest.main()
