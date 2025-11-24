# modules/temp.py
from modules.base import BaseCommand, register
from ecio import txrx, EcIo


@register("temp")
class Temperature(BaseCommand):
    name = "temp"
    help = "Read system temperature by sensor"

    def add_arguments(self, ap):
        ap.add_argument(
            "--sensor",
            choices=[
                "cpu",
                "pch",
                "gpu",
                "ts1",
                "ts2",
                "ts3",
                "ts4",
            ],
            required=True,
            help="which temperature sensor to read",
        )
        ap.add_argument("--wait", type=float, metavar="", default=0.5, help="processing delay (sec)")
        ap.add_argument("-t", "--timeout", type=float, metavar="", default=5.0, help="overall timeout (sec)")

    def run(self, args, ec: EcIo) -> int:
        CMD = 0x28
        sensor_map = {
            "cpu": 0x01,
            "pch": 0x02,
            "gpu": 0x03,
            "ts1": 0x04,
            "ts2": 0x05,
            "ts3": 0x06,
            "ts4": 0x07,
        }
        sub = sensor_map[args.sensor]

        resp = txrx(ec, CMD, [sub], expect_len=2, wait_s=args.wait, overall_timeout_s=args.timeout)
        if len(resp) != 2:
            print("[ERROR] Unexpected length:", len(resp), "bytes")
            return 2
        value = resp[0] | (resp[1] << 8)
        print(f"Temperature ({args.sensor.upper()}): {value}")
        return 0

