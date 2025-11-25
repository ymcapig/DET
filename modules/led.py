# modules/led.py
from modules.base import BaseCommand, register
from ecio import txrx, EcIo


@register("led")
class LedControl(BaseCommand):
    name = "led"
    help = "Control Power/Charge LED (Off/Blue/Amber)"

    def add_arguments(self, ap):
        group_target = ap.add_mutually_exclusive_group(required=True)
        group_target.add_argument("--power", action="store_true", help="select Power LED")
        group_target.add_argument("--charge", action="store_true", help="select Charge LED")

        group_state = ap.add_mutually_exclusive_group(required=True)
        group_state.add_argument("--off", action="store_true", help="turn LED off (0x01)")
        group_state.add_argument("--blue", action="store_true", help="turn LED blue (0x02)")
        group_state.add_argument("--amber", action="store_true", help="turn LED amber (0x03)")

        ap.add_argument("--wait", type=float, metavar="", default=0.5, help="wait after write (sec)")
        ap.add_argument("-t", "--timeout", type=float, metavar="", default=5.0, help="overall timeout (sec)")

    def run(self, args, ec: EcIo) -> int:
        CMD = 0x10
        if args.power:
            sub = 0x01
            which = "Power"
        else:
            sub = 0x02
            which = "Charge"

        if args.off:
            val = 0x01
            state = "Off"
        elif args.blue:
            val = 0x02
            state = "Blue"
        elif args.amber:
            val = 0x03
            state = "Amber"
        else:
            print("[ERROR] No state specified")
            return 1

        txrx(ec, CMD, [sub, val], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
        print(f"{which} LED: {state}")
        return 0