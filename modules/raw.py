# modules/raw.py
from modules.base import BaseCommand, register
from ecio import txrx, EcIo

def _int_auto(s: str) -> int:
    return int(s, 0)

@register("raw")
class RawCommand(BaseCommand):
    name = "raw"
    help = "Send raw EC command/data and read response"

    def add_arguments(self, ap):
        ap.add_argument("--cmd", type=_int_auto, metavar="", required=True, help="command byte")
        ap.add_argument("--subcmd", type=_int_auto, metavar="", help="optional sub-command byte")
        ap.add_argument("--data", nargs="*", metavar="BYTE", type=_int_auto, default=[], help="data bytes")
        ap.add_argument( "-n", "--length", type=int, metavar="", default=0, help="expected response bytes")
        ap.add_argument("--wait", type=float, metavar="", default=0.5, help="wait after write (sec)")
        ap.add_argument("-t", "--timeout", type=float, metavar="", default=5.0, help="overall timeout (sec)")

    def run(self, args, ec: EcIo) -> int:
        payload = []
        if args.subcmd is not None:
            payload.append(args.subcmd)
        payload.extend(args.data)
        resp = txrx(ec, args.cmd, payload, expect_len=args.length, wait_s=args.wait, overall_timeout_s=args.timeout)
        if resp:
            print("RESPONSE:", " ".join(f"0x{b:02X}" for b in resp))
        else:
            if args.length == 0:
                print("OK (no response expected)")
            else:
                print("No response")
        return 0
