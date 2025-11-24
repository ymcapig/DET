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
    """Enable/disable verbose EC I/O logging at runtime.

    Preferred control path for CLI (e.g. -v). Still honors environment
    variables as defaults, and this call overrides them.
    """
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

    def wait_ibf_clear(self, timeout_s=0.5, poll_s=0.02):
        t0 = time.perf_counter()
        _dbg(f"WAIT_IBF_CLEAR start timeout={timeout_s*1000:.0f}ms poll={poll_s*1000:.0f}ms")
        polls = 0
        while time.perf_counter() - t0 < timeout_s:
            if (self.status() & 0x02) == 0:
                _dbg(f"WAIT_IBF_CLEAR ready after {(time.perf_counter()-t0)*1000:.1f} ms (polls={polls})")
                return True
            polls += 1
            _dbg(f"WAIT_IBF_CLEAR sleep {poll_s*1000:.0f} ms")
            time.sleep(poll_s)
        _dbg(f"WAIT_IBF_CLEAR timeout after {(time.perf_counter()-t0)*1000:.1f} ms (polls={polls})")
        return False

    def wait_obf_set(self, timeout_s=0.5, poll_s=0.02):
        t0 = time.perf_counter()
        _dbg(f"WAIT_OBF_SET start timeout={timeout_s*1000:.0f}ms poll={poll_s*1000:.0f}ms")
        polls = 0
        while time.perf_counter() - t0 < timeout_s:
            if (self.status() & 0x01) != 0:
                _dbg(f"WAIT_OBF_SET ready after {(time.perf_counter()-t0)*1000:.1f} ms (polls={polls})")
                return True
            polls += 1
            _dbg(f"WAIT_OBF_SET sleep {poll_s*1000:.0f} ms")
            time.sleep(poll_s)
        _dbg(f"WAIT_OBF_SET timeout after {(time.perf_counter()-t0)*1000:.1f} ms (polls={polls})")
        return False

    def write_command(self, cmd):
        #if not self.wait_ibf_clear():
        #    raise TimeoutError("IBF not cleared before command")
        self.outb(self.cmd.value, cmd)

    def write_data(self, b):
        #if not self.wait_ibf_clear():
        #    raise TimeoutError("IBF not cleared before data")
        self.outb(self.dat.value, b)

    def read_byte(self, timeout_s=0.5):
        if not self.wait_obf_set(timeout_s=timeout_s):
            raise TimeoutError("OBF not set (no data)")
        return self.inb(self.dat.value)


def txrx(ec: 'EcIo', cmd: int, data: list[int], expect_len: int|None,
         wait_s: float, overall_timeout_s: float) -> list[int]:
    """Write, then drain all bytes; return only expected length.

    To prevent leaving unread bytes in the EC OBF (which may hang later I/O),
    this function keeps reading until no more data arrives within a short
    per-read timeout, rather than stopping exactly at expect_len. If
    expect_len is provided, the returned list is truncated to that length —
    but any extra bytes are still consumed from the port.
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
    ec.write_command(cmd)
    time.sleep(0.05)
    _dbg(f"sleep 20ms")
    for i, d in enumerate(data):
        _dbg(f"WRITE DATA[{i}] 0x{d & 0xFF:02X} -> port {dat_port_repr}")
        time.sleep(0.005)
        ec.write_data(d)
    
    _dbg("[Info] Waiting for EC to process command ... (0.2s)")
    time.sleep(0.3)

    out: list[int] = []
    t0 = time.perf_counter()
    timed_out = False
    timeout_exc: Optional[TimeoutError] = None

    while time.perf_counter() - t0 <= overall_timeout_s:
        t_read0 = time.perf_counter()
        try:
            #b = ec.read_byte(timeout_s=READ_SLICE_TIMEOUT_S)
            b = ec.read_byte(timeout_s=wait_s)
            dt_ms = (time.perf_counter() - t_read0) * 1000.0
            out.append(b)
            _dbg(f"READ wait {dt_ms:.1f} ms -> 0x{b:02X} (count={len(out)})")
            # keep looping to drain more
        except TimeoutError as exc:
            dt_ms = (time.perf_counter() - t_read0) * 1000.0
            _dbg(f"READ wait {dt_ms:.1f} ms -> timeout (drain complete)")
            timed_out = True
            timeout_exc = exc
            break

    if expect_len is not None:
        if len(out) > expect_len:
            _dbg(f"TRUNCATE response: got {len(out)} > expected {expect_len}, discarding {len(out)-expect_len} byte(s)")
        elif len(out) < expect_len and expect_len > 0:
            _dbg(f"SHORT response: got {len(out)} < expected {expect_len}")
            reason = "response timed out"
            if not timed_out:
                reason = "response ended before expected length"
            msg = f"{reason}: received {len(out)} of {expect_len} byte(s)"
            raise TimeoutError(msg) from timeout_exc
        return out[:expect_len]
    return out
