# modules/battery.py
from modules.base import BaseCommand, register
from ecio import txrx, EcIo


@register("battery")
class Battery(BaseCommand):
    name = "battery"
    help = "Battery control (0x30) and information (0x31)"

    def add_arguments(self, ap):
        ops = ap.add_mutually_exclusive_group(required=True)
        ops.add_argument("--mode", choices=["auto", "debug"], help="set battery mode")
        ops.add_argument("--charge", action="store_true", help="start charging")
        ops.add_argument("--discharge", action="store_true", help="start discharging")
        ops.add_argument(
            "--get",
            choices=[
                "all",
                "manufacturer_access",
                "battery_mode",
                "temperature",
                "voltage",
                "current",
                "average_current",
                "max_error",
                "relative_state_of_charge",
                "absolute_state_of_charge",
                "remaining_capacity",
                "full_charge_capacity",
                "charging_current",
                "charging_voltage",
                "battery_status",
                "cycle_count",
                "design_capacity",
                "design_voltage",
                "specification_info",
                "manufacture_date",
                "serial_number",
                "manufacturer_name",
                "device_name",
                "device_chemistry",
                "manufacturer_data",
                "cell_voltage4",
                "cell_voltage3",
                "cell_voltage2",
                "cell_voltage1",
                "run_time_to_empty",
                "average_time_to_empty",
                "average_time_to_full",
            ],
            help="read battery information item",
        )

        ap.add_argument("--wait", type=float, metavar="", default=0.5, help="wait after write (sec)")
        ap.add_argument("-t", "--timeout", type=float, metavar="", default=5.0, help="overall timeout (sec)")

    def run(self, args, ec: EcIo) -> int:
        CTRL = 0x30
        INFO = 0x31

        # Control path
        if args.mode:
            sub = 0x01
            val = 0x01 if args.mode == "auto" else 0x02
            txrx(ec, CTRL, [sub, val], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
            print(f"Battery mode set: {args.mode}")
            return 0
        if args.charge:
            txrx(ec, CTRL, [0x02, 0x01], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
            print("Battery charge: start")
            return 0
        if args.discharge:
            txrx(ec, CTRL, [0x03, 0x01], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
            print("Battery discharge: start")
            return 0

        # Info path
        get_map = {
            "manufacturer_access": (0x01, 2, "le16"),
            "battery_mode": (0x02, 2, "le16"),
            "temperature": (0x03, 2, "le16"),
            "voltage": (0x04, 2, "le16"),
            "current": (0x05, 2, "le16"),
            "average_current": (0x06, 2, "le16"),
            "max_error": (0x07, 2, "le16"),
            "relative_state_of_charge": (0x08, 2, "le16"),
            "absolute_state_of_charge": (0x09, 2, "le16"),
            "remaining_capacity": (0x0A, 2, "le16"),
            "full_charge_capacity": (0x0B, 2, "le16"),
            "charging_current": (0x0C, 2, "le16"),
            "charging_voltage": (0x0D, 2, "le16"),
            "battery_status": (0x0E, 2, "le16"),
            "cycle_count": (0x0F, 2, "le16"),
            "design_capacity": (0x10, 2, "le16"),
            "design_voltage": (0x11, 2, "le16"),
            "specification_info": (0x12, 2, "le16"),
            "manufacture_date": (0x13, 2, "le16"),
            "serial_number": (0x14, 2, "le16"),
            "manufacturer_name": (0x15, 14, "ascii"),
            "device_name": (0x16, 14, "ascii"),
            "device_chemistry": (0x17, 6, "ascii"),
            "manufacturer_data": (0x18, 14, "ascii"),
            "cell_voltage4": (0x19, 2, "le16"),
            "cell_voltage3": (0x1A, 2, "le16"),
            "cell_voltage2": (0x1B, 2, "le16"),
            "cell_voltage1": (0x1C, 2, "le16"),
            "run_time_to_empty": (0x1D, 2, "le16"),
            "average_time_to_empty": (0x1E, 2, "le16"),
            "average_time_to_full": (0x1F, 2, "le16"),
        }

        def _print_item(name: str, data: list[int], kind: str):
            if kind == "le16":
                val = data[0] | (data[1] << 8)
                print(f"{name}: {val}")
            elif kind == "ascii":
                text = bytes(data).split(b"\x00", 1)[0].decode("ascii", errors="replace")
                print(f"{name}: {text}")
            else:
                print(f"{name}:", " ".join(f"0x{b:02X}" for b in data))

        if args.get == "all":
            rc = 0
            for name, (sub, expect, kind) in get_map.items():
                resp = txrx(ec, INFO, [sub], expect_len=expect, wait_s=args.wait, overall_timeout_s=args.timeout)
                if len(resp) != expect:
                    print(f"[ERROR] {name}: Unexpected length {len(resp)} (expected {expect})")
                    rc = 1
                    continue
                _print_item(name, resp, kind)
            return rc
        else:
            sub, expect, kind = get_map[args.get]
            resp = txrx(ec, INFO, [sub], expect_len=expect, wait_s=args.wait, overall_timeout_s=args.timeout)
            if len(resp) != expect:
                print("[ERROR] Unexpected length:", len(resp), f"(expected {expect})")
                return 2
            _print_item(args.get, resp, kind)
            return 0
