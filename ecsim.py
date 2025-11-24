"""
ecsim.py

An in-process Embedded Controller simulator that implements the same public
interface used by txrx(): write_command, write_data, and read_byte. It keeps a
simple internal state for LEDs, fan, keyboard backlight, battery, temps, and
version, and synthesizes responses for the read-style commands used by the
modules in this project.
"""
from __future__ import annotations

import time
from typing import List

from modules.smbios import FIELDS as SMBIOS_FIELDS, _encode_field as _encode_smbios_field


def _le16(n: int) -> List[int]:
    return [n & 0xFF, (n >> 8) & 0xFF]


def _ascii_fixed(s: str, length: int) -> List[int]:
    b = s.encode("ascii", errors="replace")[:length]
    if len(b) < length:
        b = b + b"\x00" * (length - len(b))
    return list(b)


_SMBIOS_DEFAULTS = {
    "system_product_name": "XPS-9710-BOM123",
    "product_name2": "XPS-9710-RevB",
    "system_family": "XPS Performance Series",
    "marketing_name2": "XPS Marketing Name R2",
    "uuid": "12345678-90ab-cdef-1234-567890abcdef",
    "serial_number_system": "SYSNMB0001234567890",
    "serial_number_mb": "MBNMB0001234567890",
    "asset_tag": "Asset-Tag-001",
    "project_define": "P01",
    "country_type": "0x01",
    "project_id": "0x02",
    "manufacture_name": "ExampleMFG",
    "shipping_region": "0x21",
    "secure_boot": "0x01",
    "uefi_boot_type": "0x02",
    "vmd_controller": "0x01",
    "vpro_sku": "0x01",
    "os_type": "0x02",
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "touch_pad": "0x01",
    "keyboard_backlight_enable": "0x01",
    "kb_matrix_type": "0x02",
    "copilotkey_type": "0x01",
    "mic_type": "0x01",
    "computrace": "0x01",
    "custom_logo": "0x01",
    "battery_first_use_date": "0x20 0x24 0x03 0x15",
    "mfg_force_boot": "0x00",
    "ownership_tag": "Demo Ownership Tag",
    "load_default": "0x01",
}

class EcSimulator:
    def __init__(self):
        # Transaction book-keeping
        self._current_cmd: int | None = None
        self._data: List[int] = []
        self._out: List[int] = []
        self._responded: bool = False

        # Simulated state
        self.version = "SimEC v1.0"

        self.led_power = False
        self.led_charge = False

        self.fan_mode = "auto"  # or "debug"
        self.fan_duty = 128
        self.fan_rpm = 2500

        self.kb_backlight_on = False
        self.kb_backlight_level = 0

        self.kbtype = {"brand": 0, "type": None, "category": None, "size": None}

        self.batt_mode = "auto"
        self.batt_charging = False
        self.batt_discharging = False

        # Temperatures (arbitrary units)
        self.temps = {
            0x01: 450,  # cpu
            0x02: 420,  # pch
            0x03: 480,  # gpu
            0x04: 300,  # ts1
            0x05: 305,  # ts2
            0x06: 290,  # ts3
            0x07: 295,  # ts4
        }

        # Battery info map (subset of SBS-like items used by modules/battery.py)
        self.batt_info = {
            0x01: _le16(0x0000),  # manufacturer_access
            0x02: _le16(0x0001),  # battery_mode
            0x03: _le16(3000),    # temperature (0.1K or vendor-defined)
            0x04: _le16(11400),   # voltage (mV)
            0x05: _le16(1500),    # current (mA)
            0x06: _le16(1200),    # average_current (mA)
            0x07: _le16(5),       # max_error (%)
            0x08: _le16(80),      # relative_state_of_charge (%)
            0x09: _le16(78),      # absolute_state_of_charge (%)
            0x0A: _le16(4200),    # remaining_capacity (mAh)
            0x0B: _le16(5200),    # full_charge_capacity (mAh)
            0x0C: _le16(2000),    # charging_current (mA)
            0x0D: _le16(12600),   # charging_voltage (mV)
            0x0E: _le16(0x0000),  # battery_status (flags)
            0x0F: _le16(120),     # cycle_count
            0x10: _le16(5600),    # design_capacity (mAh)
            0x11: _le16(11400),   # design_voltage (mV)
            0x12: _le16(0x1234),  # specification_info
            0x13: _le16(0x5E21),  # manufacture_date (encoded)
            0x14: _le16(0x0420),  # serial_number
            0x15: _ascii_fixed("SimBattery", 14),
            0x16: _ascii_fixed("SimDevice", 14),
            0x17: _ascii_fixed("Li-Ion", 6),
            0x18: _ascii_fixed("SimData", 14),
            0x19: _le16(2850),    # cell_voltage4 (mV)
            0x1A: _le16(2850),    # cell_voltage3 (mV)
            0x1B: _le16(2850),    # cell_voltage2 (mV)
            0x1C: _le16(2850),    # cell_voltage1 (mV)
            0x1D: _le16(120),     # run_time_to_empty (min)
            0x1E: _le16(110),     # average_time_to_empty (min)
            0x1F: _le16(80),      # average_time_to_full (min)
        }

        self._smbios_by_read = {}
        self._smbios_by_write = {}
        self._smbios_store = {}
        self._smbios_length_override = {}
        self._init_smbios_defaults()

    def _init_smbios_defaults(self) -> None:
        for key, field in SMBIOS_FIELDS.items():
            self._smbios_by_read[field.read_sub] = field
            self._smbios_by_write[field.write_sub] = field
            default_text = _SMBIOS_DEFAULTS.get(key)
            self._smbios_store[field.read_sub] = self._make_smbios_payload(field, default_text)

    def _make_smbios_payload(self, field, text):
        if text is None:
            return [0] * field.length
        try:
            payload, _ = _encode_smbios_field(field, text)
        except Exception:
            return [0] * field.length
        return list(payload)

    # Compatibility no-ops with EcIo
    def outb(self, port: int, val: int) -> None:
        pass

    def inb(self, port: int) -> int:
        return 0

    def status(self) -> int:
        return 0

    def wait_ibf_clear(self, timeout_s: float = 0.2, poll_s: float = 0.001) -> bool:
        return True

    def wait_obf_set(self, timeout_s: float = 0.5, poll_s: float = 0.001) -> bool:
        return True

    def override_smbios_field_length(self, read_sub: int, length: int) -> None:
        if length <= 0:
            raise ValueError("Length must be positive")
        self._smbios_length_override[read_sub] = length
        stored = self._smbios_store.get(read_sub, [])
        stored = list(stored)
        if len(stored) < length:
            stored += [0] * (length - len(stored))
        elif len(stored) > length:
            stored = stored[:length]
        self._smbios_store[read_sub] = stored

    def _effective_length(self, field) -> int:
        return self._smbios_length_override.get(field.read_sub, field.length)

    # API used by txrx()
    def write_command(self, cmd: int) -> None:
        # New transaction begins; clear previous buffers
        self._current_cmd = cmd & 0xFF
        self._data = []
        self._out = []
        self._responded = False

    def write_data(self, b: int) -> None:
        self._data.append(b & 0xFF)

    def read_byte(self, timeout_s: float = 0.5) -> int:
        # Materialize a response on first read of this transaction only once
        if not self._out and not self._responded:
            self._generate_response()
            self._responded = True

        # Wait up to timeout for data to become available
        t0 = time.perf_counter()
        while not self._out:
            if time.perf_counter() - t0 > timeout_s:
                raise TimeoutError("OBF not set (no data)")
            time.sleep(0.001)

        return self._out.pop(0)

    # Command implementations
    def _generate_response(self) -> None:
        cmd = self._current_cmd
        if cmd is None:
            return

        # Dispatch based on command byte
        if cmd == 0x48:  # EC version
            self._resp_ecversion()
        elif cmd == 0x10:  # LEDs
            self._resp_led()
        elif cmd == 0x20:  # Fan control
            self._resp_fan()
        elif cmd == 0x28:  # Temperature
            self._resp_temp()
        elif cmd == 0x30:  # Battery control
            self._resp_batt_ctrl()
        elif cmd == 0x31:  # Battery info
            self._resp_batt_info()
        elif cmd == 0x40:  # Keyboard backlight
            self._resp_kblight()
        elif cmd == 0x60:  # SMBIOS write
            self._resp_smbios_write()
        elif cmd == 0x61:  # SMBIOS read
            self._resp_smbios_read()
        else:
            # Unknown command: no response by default
            self._out = []

    def _resp_smbios_write(self) -> None:
        if not self._data:
            self._out = []
            return
        sub = self._data[0]
        field = self._smbios_by_write.get(sub)
        if not field:
            self._out = []
            return
        length = self._effective_length(field)
        payload = self._data[1:]
        if len(payload) < length:
            payload = payload + [0] * (length - len(payload))
        if len(payload) > length:
            payload = payload[:length]
        self._smbios_store[field.read_sub] = [(b & 0xFF) for b in payload]
        # No response generated for write commands
        self._out = []

    def _resp_smbios_read(self) -> None:
        if not self._data:
            self._out = []
            return
        sub = self._data[0]
        field = self._smbios_by_read.get(sub)
        if not field:
            self._out = []
            return
        length = self._effective_length(field)
        stored = self._smbios_store.get(sub)
        if stored is None:
            stored = [0] * length
            self._smbios_store[sub] = stored
        data = list(stored)
        if len(data) < length:
            data += [0] * (length - len(data))
        elif len(data) > length:
            data = data[:length]
        self._out = data

    def _resp_ecversion(self) -> None:
        if not self._data or self._data[0] != 0x01:
            self._out = []
            return
        text = _ascii_fixed(self.version, 20)
        self._out = text

    def _resp_led(self) -> None:
        if len(self._data) < 2:
            self._out = []
            return
        which, val = self._data[0], self._data[1]
        if which == 0x01:  # power
            self.led_power = (val != 0)
        elif which == 0x02:  # charge
            self.led_charge = (val != 0)
        # No response
        self._out = []

    def _resp_fan(self) -> None:
        if not self._data:
            self._out = []
            return
        sub = self._data[0]
        if sub == 0x01 and len(self._data) >= 2:
            self.fan_mode = "auto" if self._data[1] == 0x01 else "debug"
            self._out = []
            return
        if sub == 0x02 and len(self._data) >= 3:
            # [0x02, 0x02, duty]
            self.fan_duty = max(0, min(255, self._data[2]))
            # Roughly map duty to rpm if in debug
            if self.fan_mode == "debug":
                self.fan_rpm = int(self.fan_duty * 20)
            self._out = []
            return
        if sub == 0x03 and len(self._data) >= 4:
            # [0x03, 0x03, lsb, msb]
            rpm = self._data[2] | (self._data[3] << 8)
            self.fan_rpm = max(0, min(0xFFFF, rpm))
            self._out = []
            return
        if sub == 0x04 and len(self._data) >= 2 and self._data[1] == 0x01:
            self._out = [self.fan_duty & 0xFF]
            return
        if sub == 0x05 and len(self._data) >= 2 and self._data[1] == 0x02:
            self._out = _le16(self.fan_rpm)
            return
        self._out = []

    def _resp_temp(self) -> None:
        if not self._data:
            self._out = []
            return
        sensor = self._data[0]
        val = self.temps.get(sensor, 0)
        self._out = _le16(val)

    def _resp_batt_ctrl(self) -> None:
        if not self._data:
            self._out = []
            return
        sub = self._data[0]
        if sub == 0x01 and len(self._data) >= 2:
            self.batt_mode = "auto" if self._data[1] == 0x01 else "debug"
        elif sub == 0x02 and len(self._data) >= 2 and self._data[1] == 0x01:
            self.batt_charging = True
            self.batt_discharging = False
        elif sub == 0x03 and len(self._data) >= 2 and self._data[1] == 0x01:
            self.batt_discharging = True
            self.batt_charging = False
        self._out = []

    def _resp_batt_info(self) -> None:
        if not self._data:
            self._out = []
            return
        sub = self._data[0]
        self._out = list(self.batt_info.get(sub, []))

    def _resp_kblight(self) -> None:
        if not self._data:
            self._out = []
            return
        sub = self._data[0]
        if sub == 0x01:
            self.kb_backlight_on = True
        elif sub == 0x02:
            self.kb_backlight_on = False
        elif sub == 0x03 and len(self._data) >= 2:
            self.kb_backlight_level = max(0, min(3, self._data[1]))
            self.kb_backlight_on = self.kb_backlight_level > 0
        self._out = []

    def _resp_kbtype(self) -> None:
        if not self._data:
            self._out = []
            return
        # brand + (type) OR (category [+ size])
        self.kbtype["brand"] = self._data[0]
        if len(self._data) == 2:
            self.kbtype["type"] = self._data[1]
            self.kbtype["category"] = None
            self.kbtype["size"] = None
        else:
            self.kbtype["type"] = None
            self.kbtype["category"] = self._data[1]
            self.kbtype["size"] = self._data[2] if len(self._data) >= 3 else None
        self._out = []
