# modules/fan.py
from modules.base import BaseCommand, register
from ecio import txrx, EcIo


def _int_auto(s: str) -> int:
    return int(s, 0)


@register("fan")
class FanControl(BaseCommand):
    name = "fan"
    help = "Fan control: mode, duty, RPM; and readback"

    def add_arguments(self, ap):
        # Exactly one operation must be chosen
        ops = ap.add_mutually_exclusive_group(required=True)
        ops.add_argument("--mode", choices=["auto", "debug"], help="set fan control mode")
        ops.add_argument("--set-duty", type=_int_auto, metavar="DUTY", help="set duty (0-255), debug mode only")
        ops.add_argument("--set-rpm", type=_int_auto, metavar="RPM", help="set target RPM, debug mode only")
        ops.add_argument("--get-duty", action="store_true", help="read current duty")
        ops.add_argument("--get-rpm", action="store_true", help="read current RPM")

        ap.add_argument("--wait", type=float, metavar="", default=0.5, help="wait after write (sec)")
        ap.add_argument("-t", "--timeout", type=float, metavar="", default=5.0, help="overall timeout (sec)")

    def run(self, args, ec: EcIo) -> int:
        CMD = 0x20

        # Mode switching
        if args.mode:
            sub = 0x01
            mode_val = 0x01 if args.mode == "auto" else 0x02
            txrx(ec, CMD, [sub, mode_val], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
            print(f"Fan mode set: {args.mode}")
            return 0

        # Set duty (debug mode only per spec)
        if args.set_duty is not None:
            duty = max(0, min(255, int(args.set_duty)))
            sub = 0x02
            txrx(ec, CMD, [sub, 0x02, duty & 0xFF], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
            print(f"Fan duty set: {duty}")
            return 0

        # Set RPM (debug mode only per spec)
        if args.set_rpm is not None:
            rpm = max(0, min(0xFFFF, int(args.set_rpm)))
            sub = 0x03
            lsb = rpm & 0xFF
            msb = (rpm >> 8) & 0xFF
            txrx(ec, CMD, [sub, 0x03, lsb, msb], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
            print(f"Fan RPM set: {rpm}")
            return 0

        # Read duty
        if args.get_duty:
            sub = 0x04
            resp = txrx(ec, CMD, [sub, 0x01], expect_len=1, wait_s=args.wait, overall_timeout_s=args.timeout)
            if len(resp) != 1:
                print("[ERROR] Unexpected length:", len(resp), "bytes")
                return 2
            print(f"Fan Duty: {resp[0]}")
            return 0

        # Read RPM
        if args.get_rpm:
            sub = 0x05
            resp = txrx(ec, CMD, [sub, 0x02], expect_len=2, wait_s=args.wait, overall_timeout_s=args.timeout)
            if len(resp) != 2:
                print("[ERROR] Unexpected length:", len(resp), "bytes")
                return 2
            rpm = resp[0] | (resp[1] << 8)
            print(f"Fan RPM: {rpm}")
            return 0

        # Should not reach here due to mutually exclusive required group
        print("[ERROR] No operation specified")
        return 2

