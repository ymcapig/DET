# modules/smbios.py
import string
import uuid
import time
from dataclasses import dataclass, replace
from typing import Dict, List, Tuple

from modules.base import BaseCommand, register
from ecio import txrx, EcIo, EC_DEBUG


@dataclass(frozen=True)
class FieldDef:
    label: str
    length: int
    write_cmd: int
    write_sub: int
    read_cmd: int
    read_sub: int
    encoding: str = "ascii"


_UUID_SEGMENTS: Tuple[Tuple[int, int], ...] = ((0, 4), (4, 6), (6, 8))


def _swap_uuid_segments(data: bytes) -> bytes:
    if len(data) != 16:
        raise ValueError("UUID field must be 16 bytes")
    swapped = bytearray(data)
    for start, end in _UUID_SEGMENTS:
        swapped[start:end] = data[start:end][::-1]
    return bytes(swapped)


def _normalize_byte_tokens(value: str) -> List[str]:
    cleaned = value.replace("-", " ").replace(":", " ").replace(",", " ").strip()
    if not cleaned:
        return []
    tokens = cleaned.split()
    if len(tokens) == 1:
        token = tokens[0]
        lower = token.lower()
        if lower.startswith("0x"):
            token = lower[2:]
        if len(token) % 2 == 0 and token and all(c in string.hexdigits for c in token):
            return [f"0x{token[i : i + 2]}" for i in range(0, len(token), 2)]
        return [tokens[0]]
    return tokens


def _parse_single_byte(token: str) -> int:
    try:
        val = int(token, 10)
        if 0 <= val <= 255:
            return val
    except ValueError:
        pass
    val = int(token, 16)
    if 0 <= val <= 255:
        return val
    raise ValueError(f"Byte '{token}' out of range (0-255)")


def _parse_bytes_string(value: str, length: int) -> bytes:
    tokens = _normalize_byte_tokens(value)
    if not tokens:
        raise ValueError("Value must contain at least one byte")
    if len(tokens) != length:
        raise ValueError(f"Expected {length} byte(s) but got {len(tokens)}")
    try:
        values = [_parse_single_byte(tok) for tok in tokens]
    except ValueError as exc:
        raise ValueError(str(exc)) from None
    return bytes(values)


def _decode_field(field: FieldDef, data: bytes) -> str:
    if field.encoding == "ascii":
        return data.split(b"\x00", 1)[0].decode("ascii", errors="replace")
    if field.encoding == "uuid":
        original = uuid.UUID(bytes=data)
        swapped = uuid.UUID(bytes=_swap_uuid_segments(data))
        if EC_DEBUG:
            print(str(original))
            print(str(swapped))
        return str(swapped)
    if field.encoding == "mac":
        return ":".join(f"{b:02X}" for b in data)
    if field.encoding == "bcd_date":
        digits = []
        for b in data:
            hi = (b >> 4) & 0xF
            lo = b & 0xF
            if hi > 9 or lo > 9:
                raise ValueError("Invalid BCD digit in battery date")
            digits.append(str(hi))
            digits.append(str(lo))
        return "".join(digits)
    return " ".join(f"0x{b:02X}" for b in data)


def _encode_field(field: FieldDef, value: str) -> Tuple[bytes, str]:
    if field.encoding == "ascii":
        try:
            raw = value.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError("ASCII field cannot encode the given value") from None
        if len(raw) > field.length:
            raise ValueError(f"Value too long ({len(raw)} bytes) for field (max {field.length})")
        padded = raw + b"\x00" * (field.length - len(raw))
        printable = raw.decode("ascii", errors="replace")
        return padded, printable
    if field.encoding == "uuid":
        parsed = uuid.UUID(value)
        encoded = _swap_uuid_segments(parsed.bytes)
        return encoded, str(parsed)
    if field.encoding == "mac":
        raw = _parse_bytes_string(value, field.length)
        printable = ":".join(f"{b:02X}" for b in raw)
        return raw, printable
    if field.encoding == "bcd_date":
        digits = [c for c in value if c.isdigit()]
        if len(digits) != field.length * 2:
            raise ValueError(f"Expected {field.length * 2} digits but got {len(digits)}")
        raw = bytearray()
        for i in range(0, len(digits), 2):
            hi = int(digits[i])
            lo = int(digits[i + 1])
            raw.append((hi << 4) | lo)
        printable = "".join(digits)
        return bytes(raw), printable
    if field.encoding == "hex":
        raw = _parse_bytes_string(value, field.length)
        printable = " ".join(f"0x{b:02X}" for b in raw)
        return raw, printable
    raise ValueError(f"Unsupported field encoding '{field.encoding}'")


FIELDS: Dict[str, FieldDef] = {
    "system_product_name": FieldDef(
        label="System Product Name",
        length=50,
        write_cmd=0x60,
        write_sub=0x01,
        read_cmd=0x61,
        read_sub=0x01,
        encoding="ascii",
    ),
    "product_name2": FieldDef(
        label="Product Name2",
        length=50,
        write_cmd=0x60,
        write_sub=0x02,
        read_cmd=0x61,
        read_sub=0x02,
        encoding="ascii",
    ),
    "system_family": FieldDef(
        label="System Family",
        length=30,
        write_cmd=0x60,
        write_sub=0x03,
        read_cmd=0x61,
        read_sub=0x03,
        encoding="ascii",
    ),
    "marketing_name2": FieldDef(
        label="Marketing Name2",
        length=30,
        write_cmd=0x60,
        write_sub=0x04,
        read_cmd=0x61,
        read_sub=0x04,
        encoding="ascii",
    ),
    "uuid": FieldDef(
        label="UUID",
        length=16,
        write_cmd=0x60,
        write_sub=0x05,
        read_cmd=0x61,
        read_sub=0x05,
        encoding="uuid",
    ),
    "serial_number_system": FieldDef(
        label="Serial Number (System)",
        length=22,
        write_cmd=0x60,
        write_sub=0x06,
        read_cmd=0x61,
        read_sub=0x06,
        encoding="ascii",
    ),
    "serial_number_mb": FieldDef(
        label="Serial Number (MB)",
        length=22,
        write_cmd=0x60,
        write_sub=0x07,
        read_cmd=0x61,
        read_sub=0x07,
        encoding="ascii",
    ),
    "asset_tag": FieldDef(
        label="Asset Tag",
        length=22,
        write_cmd=0x60,
        write_sub=0x08,
        read_cmd=0x61,
        read_sub=0x08,
        encoding="ascii",
    ),
    "project_define": FieldDef(
        label="Project Define",
        length=3,
        write_cmd=0x60,
        write_sub=0x09,
        read_cmd=0x61,
        read_sub=0x09,
        encoding="ascii",
    ),
    "country_type": FieldDef(
        label="Country Type",
        length=1,
        write_cmd=0x60,
        write_sub=0x0A,
        read_cmd=0x61,
        read_sub=0x0A,
        encoding="hex",
    ),
    "project_id": FieldDef(
        label="Project ID",
        length=1,
        write_cmd=0x60,
        write_sub=0x0B,
        read_cmd=0x61,
        read_sub=0x0B,
        encoding="hex",
    ),
    "manufacture_name": FieldDef(
        label="Manufacture Name",
        length=16,
        write_cmd=0x60,
        write_sub=0x0C,
        read_cmd=0x61,
        read_sub=0x0C,
        encoding="ascii",
    ),
    "shipping_region": FieldDef(
        label="Shipping Region",
        length=1,
        write_cmd=0x60,
        write_sub=0x0D,
        read_cmd=0x61,
        read_sub=0x0D,
        encoding="hex",
    ),
    "secure_boot": FieldDef(
        label="Secure Boot",
        length=1,
        write_cmd=0x60,
        write_sub=0x0E,
        read_cmd=0x61,
        read_sub=0x0E,
        encoding="hex",
    ),
    "uefi_boot_type": FieldDef(
        label="UEFI Boot Type",
        length=1,
        write_cmd=0x60,
        write_sub=0x0F,
        read_cmd=0x61,
        read_sub=0x0F,
        encoding="hex",
    ),
    "vmd_controller": FieldDef(
        label="VMD Controller",
        length=1,
        write_cmd=0x60,
        write_sub=0x10,
        read_cmd=0x61,
        read_sub=0x10,
        encoding="hex",
    ),
    "vpro_sku": FieldDef(
        label="Vpro SKU",
        length=1,
        write_cmd=0x60,
        write_sub=0x11,
        read_cmd=0x61,
        read_sub=0x11,
        encoding="hex",
    ),
    "os_type": FieldDef(
        label="OS Type",
        length=1,
        write_cmd=0x60,
        write_sub=0x12,
        read_cmd=0x61,
        read_sub=0x12,
        encoding="hex",
    ),
    "mac_address": FieldDef(
        label="MAC Address",
        length=6,
        write_cmd=0x60,
        write_sub=0x13,
        read_cmd=0x61,
        read_sub=0x13,
        encoding="mac",
    ),
    "touch_pad": FieldDef(
        label="Touch Pad",
        length=1,
        write_cmd=0x60,
        write_sub=0x14,
        read_cmd=0x61,
        read_sub=0x14,
        encoding="hex",
    ),
    "keyboard_backlight_enable": FieldDef(
        label="Keyboard Backlight Enable",
        length=1,
        write_cmd=0x60,
        write_sub=0x15,
        read_cmd=0x61,
        read_sub=0x15,
        encoding="hex",
    ),
    "kb_matrix_type": FieldDef(
        label="KB Matrix Type",
        length=1,
        write_cmd=0x60,
        write_sub=0x16,
        read_cmd=0x61,
        read_sub=0x16,
        encoding="hex",
    ),
    "copilotkey_type": FieldDef(
        label="Copilotkey Type",
        length=1,
        write_cmd=0x60,
        write_sub=0x17,
        read_cmd=0x61,
        read_sub=0x17,
        encoding="hex",
    ),
    "mic_type": FieldDef(
        label="MIC Type",
        length=1,
        write_cmd=0x60,
        write_sub=0x18,
        read_cmd=0x61,
        read_sub=0x18,
        encoding="hex",
    ),
    "computrace": FieldDef(
        label="Computrace",
        length=1,
        write_cmd=0x60,
        write_sub=0x19,
        read_cmd=0x61,
        read_sub=0x19,
        encoding="hex",
    ),
    "custom_logo": FieldDef(
        label="Custom Logo",
        length=1,
        write_cmd=0x60,
        write_sub=0x1A,
        read_cmd=0x61,
        read_sub=0x1A,
        encoding="hex",
    ),
    "battery_first_use_date": FieldDef(
        label="Battery First Use Date",
        length=4,
        write_cmd=0x60,
        write_sub=0x1B,
        read_cmd=0x61,
        read_sub=0x1B,
        encoding="bcd_date",
    ),
    "mfg_force_boot": FieldDef(
        label="MFG Force Boot",
        length=1,
        write_cmd=0x60,
        write_sub=0x1C,
        read_cmd=0x61,
        read_sub=0x1C,
        encoding="hex",
    ),
    "ownership_tag": FieldDef(
        label="Ownership Tag",
        length=50,
        write_cmd=0x60,
        write_sub=0x1D,
        read_cmd=0x61,
        read_sub=0x1D,
        encoding="ascii",
    ),
    "load_default": FieldDef(
        label="Load Default",
        length=1,
        write_cmd=0x60,
        write_sub=0x1E,
        read_cmd=0x61,
        read_sub=0x1E,
        encoding="hex",
    ),
    "sku_number": FieldDef(
        label="SKU Number",
        length=16,
        write_cmd=0x60,
        write_sub=0x1F,
        read_cmd=0x61,
        read_sub=0x1F,
        encoding="ascii",
    ),
}

def _sync_simulator_field_length(ec: EcIo, field: FieldDef) -> None:
    handler = getattr(ec, "override_smbios_field_length", None)
    if callable(handler):
        try:
            handler(field.read_sub, field.length)
        except Exception:
            pass


@register("smbios")
class SMBIOS(BaseCommand):
    name = "smbios"
    help = "Read or write SMBIOS fields via EC commands 0x60/0x61"

    def add_arguments(self, ap):
        ap.add_argument(
            "--field",
            choices=tuple(FIELDS.keys()),
            required=True,
            help="target SMBIOS field",
        )
        ops = ap.add_mutually_exclusive_group(required=True)
        ops.add_argument("--read", action="store_true", help="read field value")
        ops.add_argument(
            "--write",
            metavar="VALUE",
            help="write field value (ASCII text, UUID, or hex bytes depending on field)",
        )
        ap.add_argument(
            "--field-length",
            type=int,
            metavar="",
            help="override field length in bytes for this run",
        )
        ap.add_argument("--wait", type=float, metavar="", default=0.5, help="wait after command (sec)")
        ap.add_argument("-t", "--timeout", type=float, metavar="", default=5.0, help="overall timeout (sec)")

    def run(self, args, ec: EcIo) -> int:
        field = FIELDS[args.field]
        override_len = getattr(args, "field_length", None)
        if override_len is not None:
            if override_len <= 0:
                print("[ERROR] --field-length must be greater than 0")
                return 2
            field = replace(field, length=override_len)
            _sync_simulator_field_length(ec, field)
        if args.read:
            try:
                resp = txrx(
                    ec,
                    field.read_cmd,
                    [field.read_sub],
                    expect_len=field.length,
                    wait_s=args.wait,
                    overall_timeout_s=args.timeout,
                )
            except TimeoutError as exc:
                print(f"[ERROR] {field.label} read timed out: {exc}")
                return 2
            if len(resp) != field.length:
                print(f"[ERROR] Unexpected length: {len(resp)} (expected {field.length})")
                return 2
            data = bytes(resp)
            try:
                printable = _decode_field(field, data)
            except ValueError as exc:
                print(f"[ERROR] {exc}")
                return 2
            print(f"{field.label}: {printable}")
            return 0

        value = args.write
        if value is None:
            print("[ERROR] --write requires VALUE")
            return 2

        try:
            payload_bytes, printable = _encode_field(field, value)
        except (ValueError, TypeError) as exc:
            print(f"[ERROR] {exc}")
            return 2

        payload = [field.write_sub] + list(payload_bytes)
        try:
            txrx(
                ec,
                field.write_cmd,
                payload,
                expect_len=0,
                wait_s=args.wait,
                overall_timeout_s=args.timeout,
            )
        except TimeoutError as exc:
            print(f"[ERROR] Failed to write {field.label}: {exc}")
            return 2
        ### Trigger EC write data to EC eflash ###
        time.sleep(0.3)
        print("sleep 0.3s for writing data to eflash")
        try:
            txrx(
                ec,
                0x62,
                [0x01],
                expect_len=0,
                wait_s=args.wait,
                overall_timeout_s=args.timeout,
            )
        except TimeoutError as exc:
            print(f"[ERROR] Commit command (0x62) timed out: {exc}")
            return 2
        print(f"{field.label} updated: {printable}")
        ###########################################
        return 0

