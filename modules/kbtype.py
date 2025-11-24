# modules/kbtype.py
from modules.base import BaseCommand, register
from ecio import txrx, EcIo


def _int_auto(s: str) -> int:
    return int(s, 0)


@register("kbtype")
class KeyboardType(BaseCommand):
    name = "kbtype"
    help = "Keyboard type setting (brand/category/size or brand-specific type)"

    def add_arguments(self, ap):
        ap.add_argument(
            "--brand",
            choices=["acer", "asus", "dell", "hp"],
            required=True,
            help="brand selection",
        )

        ap.add_argument("--type", type=_int_auto, metavar="TYPE", help="brand-specific type code (e.g., Acer)")
        ap.add_argument("--category", type=_int_auto, metavar="CAT", help="product category code")
        ap.add_argument("--size", type=_int_auto, metavar="SIZE", help="product size code (optional)")

        ap.add_argument("--wait", type=float, metavar="", default=0.5, help="wait after write (sec)")
        ap.add_argument("-t", "--timeout", type=float, metavar="", default=5.0, help="overall timeout (sec)")

    def run(self, args, ec: EcIo) -> int:
        CMD = 0x50
        brand_map = {
            "acer": 0x01,
            "asus": 0x02,
            "dell": 0x03,
            "hp": 0x04,
        }
        brand = brand_map[args.brand]

        payload = [brand]
        if args.type is not None:
            payload.append(int(args.type) & 0xFF)
            desc = f"brand={args.brand}, type=0x{int(args.type)&0xFF:02X}"
        else:
            if args.category is None:
                print("[ERROR] --category is required when --type is not used")
                return 2
            payload.append(int(args.category) & 0xFF)
            if args.size is not None:
                payload.append(int(args.size) & 0xFF)
                desc = f"brand={args.brand}, category=0x{int(args.category)&0xFF:02X}, size=0x{int(args.size)&0xFF:02X}"
            else:
                desc = f"brand={args.brand}, category=0x{int(args.category)&0xFF:02X}"

        txrx(ec, CMD, payload, expect_len=0, wait_s=args.wait, overall_timeout_s=args.timeout)
        print(f"Keyboard type set: {desc}")
        return 0
