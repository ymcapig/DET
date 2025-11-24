# modules/led.py
from modules.base import BaseCommand, register
from ecio import txrx, EcIo


@register("led")
class LedControl(BaseCommand):
    name = "led"
    help = "Control Power/Charge LED"

    def add_arguments(self, ap):
        group_target = ap.add_mutually_exclusive_group(required=True)
        group_target.add_argument("--power", action="store_true", help="select Power LED")
        group_target.add_argument("--charge", action="store_true", help="select Charge LED")

        group_state = ap.add_mutually_exclusive_group(required=True)
        group_state.add_argument("--on", action="store_true", help="turn LED on")
        group_state.add_argument("--off", action="store_true", help="turn LED off")

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

        val = 0x01 if args.on else 0x00
        state = "On" if args.on else "Off"

        txrx(ec, CMD, [sub, val], expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
        print(f"{which} LED: {state}")
        return 0

