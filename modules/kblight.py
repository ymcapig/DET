# modules/kblight.py
from modules.base import BaseCommand, register
from ecio import txrx, EcIo


def _int_auto(s: str) -> int:
    return int(s, 0)


@register("kblight")
class KeyboardBacklight(BaseCommand):
    name = "kblight"
    help = "Keyboard backlight control (on/off/level)"

    def add_arguments(self, ap):
        ops = ap.add_mutually_exclusive_group(required=True)
        ops.add_argument("--on", action="store_true", help="turn keyboard backlight ON")
        ops.add_argument("--off", action="store_true", help="turn keyboard backlight OFF")
        ops.add_argument("--level", type=_int_auto, metavar="LEVEL", help="set brightness level 0-3")

        ap.add_argument("--wait", type=float, metavar="", default=0.5, help="wait after write (sec)")
        ap.add_argument("-t", "--timeout", type=float, metavar="", default=5.0, help="overall timeout (sec)")

    def run(self, args, ec: EcIo) -> int:
        CMD = 0x40

        if args.on:
            # Sub-command 0x01, reserved parameter not used
            txrx(ec, CMD, [0x01], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
            print("KB Backlight: ON")
            return 0

        if args.off:
            # Sub-command 0x02, reserved parameter not used
            txrx(ec, CMD, [0x02], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
            print("KB Backlight: OFF")
            return 0

        if args.level is not None:
            lvl = max(0, min(3, int(args.level)))
            # Sub-command 0x03 with brightness parameter 0x00~0x03
            txrx(ec, CMD, [0x03, lvl & 0xFF], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
            print(f"KB Backlight Level: {lvl}")
            return 0

        print("[ERROR] No operation specified")
        return 2

