# ecio.py
import ctypes, os, time, sys
from typing import Optional

DLL_NAME = "inpoutx64.dll"
DEFAULT_CMD_PORT = 0x6C
DEFAULT_DATA_PORT = 0x68

def _env_truthy(name: str) -> bool:
    v = os.environ.get(name, "")
    return str(v).strip().lower() in {"1", "true", "yes", "on", "debug"}


EC_DEBUG = _env_truthy("EC_DEBUG") or _env_truthy("ECIO_DEBUG")


def set_debug(enabled: bool = True) -> None:
    """Enable/disable verbose EC I/O logging at runtime."""
    global EC_DEBUG
    EC_DEBUG = bool(enabled)


def _dbg(*args):
    if EC_DEBUG:
        print("[ECIO]", *args, file=sys.stderr)

class EcIo:
    def __init__(self, cmd_port=DEFAULT_CMD_PORT, dat_port=DEFAULT_DATA_PORT, dll_path=DLL_NAME):
        dll_candidates = []
        base = os.path.basename(dll_path)
        if os.path.isabs(dll_path):
            dll_candidates.append(dll_path)
        else:
            cwd = os.getcwd()
            here = os.path.dirname(os.path.abspath(__file__))
            dll_candidates.extend([
                os.path.join(cwd, dll_path),
                os.path.join(here, dll_path),
                os.path.join(cwd, 'dist', base),
                os.path.join(here, 'dist', base),
            ])

        chosen = next((p for p in dll_candidates if os.path.exists(p)), None)
        if not chosen:
            raise FileNotFoundError(f"Missing {dll_path} (searched: " + ", ".join(dll_candidates) + ")")

        dll_dir = os.path.dirname(os.path.abspath(chosen))
        add_ctx = None
        if hasattr(os, 'add_dll_directory'):
            try:
                add_ctx = os.add_dll_directory(dll_dir)
            except Exception:
                add_ctx = None

        try:
            self.dll = ctypes.WinDLL(os.path.abspath(chosen))
        except OSError as e:
            arch = 64 if ctypes.sizeof(ctypes.c_void_p) == 8 else 32
            msg = [
                f"Failed to load '{chosen}'",
                f"Python arch: {arch}-bit",
                "Possible causes:",
                "- Architecture mismatch (use x64 DLL with 64-bit Python)",
                "- Missing VC++ runtime or dependent DLLs",
                "- DLL directory not on search path (try --dll with absolute path)",
            ]
            raise OSError("; ".join(msg)) from e
        finally:
            if add_ctx is not None:
                try:
                    add_ctx.close()
                except Exception:
                    pass
        self.cmd = ctypes.c_short(cmd_port)
        self.dat = ctypes.c_short(dat_port)

    def outb(self, port, val):
        self.dll.Out32(ctypes.c_short(port), ctypes.c_short(val & 0xFF))

    def inb(self, port):
        return self.dll.Inp32(ctypes.c_short(port)) & 0xFF

    def status(self):
        return self.inb(self.cmd.value)

    def wait_ibf_clear(self, timeout_s=0.5, poll_s=0.001):
        """Wait for Input Buffer Full (IBF) flag to clear (Bit 1 = 0)."""
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < timeout_s:
            if (self.status() & 0x02) == 0:
                return True
            time.sleep(poll_s)
        
        _dbg(f"WAIT_IBF_CLEAR timeout after {(time.perf_counter()-t0)*1000:.1f} ms")
        return False

    def wait_obf_set(self, timeout_s=0.5, poll_s=0.001):
        """Wait for Output Buffer Full (OBF) flag to set (Bit 0 = 1)"""
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < timeout_s:
            if (self.status() & 0x01) != 0:
                return True
            time.sleep(poll_s)
        return False

    def write_command(self, cmd):
        # [FIX] IBF Check restored
        if not self.wait_ibf_clear():
            raise TimeoutError(f"IBF not cleared before command 0x{cmd:02X}")
        self.outb(self.cmd.value, cmd)

    def write_data(self, b):
        # [FIX] IBF Check restored
        if not self.wait_ibf_clear():
            raise TimeoutError(f"IBF not cleared before data 0x{b:02X}")
        self.outb(self.dat.value, b)

    def read_byte(self, timeout_s=0.5):
        if not self.wait_obf_set(timeout_s=timeout_s):
            raise TimeoutError("OBF not set (no data)")
        return self.inb(self.dat.value)


def txrx(ec: 'EcIo', cmd: int, data: list[int], expect_len: int|None,
         wait_s: float, overall_timeout_s: float) -> list[int]:
    """Write, then drain all bytes; return only expected length.
    
    Restored IBF checks on write, but keeps the original 'drain' behavior
    on read (doesn't stop early even if expect_len is met).
    """
    
    cmd_port_attr = getattr(ec, "cmd", None)
    if cmd_port_attr is not None and hasattr(cmd_port_attr, "value"):
        cmd_port_repr = f"0x{int(cmd_port_attr.value) & 0xFFFF:04X}"
    else:
        cmd_port_repr = "sim"

    dat_port_attr = getattr(ec, "dat", None)
    if dat_port_attr is not None and hasattr(dat_port_attr, "value"):
        dat_port_repr = f"0x{int(dat_port_attr.value) & 0xFFFF:04X}"
    else:
        dat_port_repr = "sim"

    _dbg(f"WRITE CMD 0x{cmd:02X} -> port {cmd_port_repr}")
    
    # 1. Write Command (will wait for IBF)
    ec.write_command(cmd)
    
    # Slight delay to let EC digest the command byte before we push args
    time.sleep(0.05) 

    for i, d in enumerate(data):
        _dbg(f"WRITE DATA[{i}] 0x{d & 0xFF:02X} -> port {dat_port_repr}")
        # 2. Write Data (will wait for IBF)
        ec.write_data(d)
        time.sleep(0.005)
    
    _dbg("[Info] Waiting for EC to process command ...")
    
    # [OPTIONAL] Kept a small sleep here to be safe, but relies on read_byte timeout mainly.
    time.sleep(0.2) 

    out: list[int] = []
    t0 = time.perf_counter()
    timed_out = False
    timeout_exc: Optional[TimeoutError] = None

    while time.perf_counter() - t0 <= overall_timeout_s:
        # [USER REQUEST]: No "break if len >= expect_len".
        # We continue looping to drain any extra bytes or until silence (timeout).
        
        t_read0 = time.perf_counter()
        try:
            b = ec.read_byte(timeout_s=wait_s)
            
            dt_ms = (time.perf_counter() - t_read0) * 1000.0
            out.append(b)
            _dbg(f"READ wait {dt_ms:.1f} ms -> 0x{b:02X} (count={len(out)})")
            
        except TimeoutError as exc:
            # Silence detected (no more data from EC)
            dt_ms = (time.perf_counter() - t_read0) * 1000.0
            _dbg(f"READ wait {dt_ms:.1f} ms -> timeout (drain complete)")
            timed_out = True
            timeout_exc = exc
            break

    if expect_len is not None:
        if len(out) > expect_len:
            _dbg(f"TRUNCATE response: got {len(out)} > expected {expect_len}, discarding {len(out)-expect_len} byte(s)")
        elif len(out) < expect_len:
            _dbg(f"SHORT response: got {len(out)} < expected {expect_len}")
            reason = "response timed out"
            if not timed_out:
                reason = "response ended before expected length"
            msg = f"{reason}: received {len(out)} of {expect_len} byte(s)"
            
            if timeout_exc:
                raise TimeoutError(msg) from timeout_exc
            else:
                raise TimeoutError(msg)
        return out[:expect_len]
    return out
