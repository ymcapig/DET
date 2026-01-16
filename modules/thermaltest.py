from modules.base import BaseCommand, register
from ecio import txrx, EcIo

@register("thermaltest")
class Thermaltest(BaseCommand):
    name = "thermaltest"
    help = "Read runin thermal test all data"

    def add_arguments(self, ap):
        # 保留時間參數以便調整穩定性
        ap.add_argument("--wait", type=float, metavar="", default=0.2, help="processing delay per sensor (sec)")
        ap.add_argument("-t", "--timeout", type=float, metavar="", default=5.0, help="overall timeout (sec)")
    
    def get_temp_sensor(self, args, ec: EcIo):
        CMD = 0x28
        sensor_map = {
            "cpu": 0x01,
            #"pch": 0x02,
            #"gpu": 0x03,
            "ts1": 0x04,
            "ts2": 0x05,
            #"ts3": 0x06,
            #"ts4": 0x07,
        }

        for name, sub in sensor_map.items():
            resp = []
            for i in range(3):
                resp = txrx(ec, CMD, [sub], expect_len=None, wait_s=0.1, overall_timeout_s=args.timeout)
                if resp:
                    break
            
            if not resp:
                # 3 次都失敗 (None)，填入 0
                value = 0
            else:
                # 取得回傳值的第一個 byte
                value = resp[0]

            print(f"{name}:{value}")
        return

    def get_fan_rpm(self, args, ec: EcIo):
        CMD = 0x20
        sub = 0x05       
        for fan_id in [1, 2]:
            resp = []
            for i in range(3):
                # 修正 Protocol: [SubCmd, RPM_Flag(0x02), FanID]
                # 注意這裡補回了 0x02
                payload = [sub, fan_id]
                
                resp = txrx(ec, CMD, payload, expect_len=None, wait_s=0.1, overall_timeout_s=args.timeout)
                if resp:
                    break           
            if not resp or len(resp) != 2:
                rpm = 0
            else:
                rpm = resp[0] | (resp[1] << 8)
            
            print(f"Fan {fan_id} RPM:{rpm}")

        return
    def run(self, args, ec: EcIo) -> int:
        self.get_temp_sensor(args, ec)
        self.get_fan_rpm(args, ec)
        return 0