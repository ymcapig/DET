# modules/ecversion.py
from modules.base import BaseCommand, register
from ecio import txrx, EcIo

@register("ecversion")
class ECVersion(BaseCommand):
    name = "ecversion"
    help = "Read EC firmware version string"

    def add_arguments(self, ap):
        ap.add_argument("--wait", type=float, metavar="", default=0.5, help="processing delay (sec)")
        ap.add_argument("-t", "--timeout", type=float, metavar="", default=5.0, help="overall timeout (sec)")

    def run(self, args, ec: EcIo) -> int:
        CMD = 0x48
        SUBCMD = 0x01
        EXPECT = None
        resp = txrx(ec, CMD, [SUBCMD], expect_len=EXPECT, wait_s=args.wait, overall_timeout_s=args.timeout)
        if not resp:
            print("[FAIL] No response received from EC")
            return 1
        # if EXPECT != None and len(resp) != EXPECT :
        #     print("[ERROR] Unexpected length:", len(resp), "bytes:", " ".join(f"0x{b:02X}" for b in resp))
        #     return 2
        # Decode ASCII string, trim at first NUL if present
        version = bytes(resp).split(b"\x00", 1)[0].decode("ascii", errors="replace")
        print(f"EC Version: {version}")
        return 0
