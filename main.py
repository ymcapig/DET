# main.py
import argparse, sys, os, ctypes, io, locale
from ecio import EcIo, DEFAULT_CMD_PORT, DEFAULT_DATA_PORT, DLL_NAME, set_debug
from ecsim import EcSimulator
from modules import SUPPORTED_MODULES   # { "ecversion": ECVersion, "raw": RawCommand }
import modules


def _configure_stdio() -> None:
    """Prevent Windows console encoding errors (e.g. charmap) when printing."""
    preferred = locale.getpreferredencoding(False) or "utf-8"
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding=preferred, errors="replace")
            continue
        except (AttributeError, ValueError, OSError):
            pass
        buffer = getattr(stream, "buffer", None)
        if buffer is None:
            continue
        try:
            wrapper = io.TextIOWrapper(buffer, encoding=preferred, errors="replace")
        except Exception:
            continue
        setattr(sys, name, wrapper)


_configure_stdio()


def int_auto(s: str) -> int:
    return int(s, 0)


def _get_file_version_windows(path: str) -> str | None:
    try:
        GetFileVersionInfoSizeW = ctypes.windll.version.GetFileVersionInfoSizeW
        GetFileVersionInfoW = ctypes.windll.version.GetFileVersionInfoW
        VerQueryValueW = ctypes.windll.version.VerQueryValueW

        size = GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = (ctypes.c_byte * size)()
        if not GetFileVersionInfoW(path, 0, size, ctypes.byref(buf)):
            return None

        LPVOID = ctypes.c_void_p
        lptr = LPVOID()
        lsize = ctypes.c_uint()

        # Try StringFileInfo with language/codepage
        if VerQueryValueW(ctypes.byref(buf), "\\VarFileInfo\\Translation", ctypes.byref(lptr), ctypes.byref(lsize)) and lsize.value >= 4:
            trans = ctypes.cast(lptr, ctypes.POINTER(ctypes.c_ushort))
            lang = trans[0]
            codepage = trans[1]
            for key in ("ProductVersion", "FileVersion"):
                block = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\{key}"
                lptr = LPVOID(); lsize = ctypes.c_uint()
                if VerQueryValueW(ctypes.byref(buf), block, ctypes.byref(lptr), ctypes.byref(lsize)) and lptr.value:
                    s = ctypes.wstring_at(lptr.value)
                    if s:
                        return s

        # Fallback to VS_FIXEDFILEINFO structure
        if VerQueryValueW(ctypes.byref(buf), "\\", ctypes.byref(lptr), ctypes.byref(lsize)) and lptr.value:
            class VS_FIXEDFILEINFO(ctypes.Structure):
                _fields_ = [
                    ("dwSignature", ctypes.c_uint32),
                    ("dwStrucVersion", ctypes.c_uint32),
                    ("dwFileVersionMS", ctypes.c_uint32),
                    ("dwFileVersionLS", ctypes.c_uint32),
                    ("dwProductVersionMS", ctypes.c_uint32),
                    ("dwProductVersionLS", ctypes.c_uint32),
                    ("dwFileFlagsMask", ctypes.c_uint32),
                    ("dwFileFlags", ctypes.c_uint32),
                    ("dwFileOS", ctypes.c_uint32),
                    ("dwFileType", ctypes.c_uint32),
                    ("dwFileSubtype", ctypes.c_uint32),
                    ("dwFileDateMS", ctypes.c_uint32),
                    ("dwFileDateLS", ctypes.c_uint32),
                ]
            info = ctypes.cast(lptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
            def HI(d): return (d >> 16) & 0xFFFF
            def LO(d): return d & 0xFFFF
            return f"{HI(info.dwProductVersionMS)}.{LO(info.dwProductVersionMS)}.{HI(info.dwProductVersionLS)}.{LO(info.dwProductVersionLS)}"
    except Exception:
        return None
    return None


def _print_version_and_exit():
    exe = sys.executable if getattr(sys, 'frozen', False) else None
    ver = None
    if exe and os.name == 'nt':
        ver = _get_file_version_windows(exe)
    # Dev fallback
    if not ver:
        ver = "dev"
    print(f"DiagECtool {ver}")
    sys.exit(0)


def build_parser():
    ap = argparse.ArgumentParser(
        description="EC tool (subparser style)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    ap.add_argument("--cmd-port", metavar="", type=int_auto,
                    default=DEFAULT_CMD_PORT, help="EC command port")
    ap.add_argument("--data-port", metavar="", type=int_auto,
                    default=DEFAULT_DATA_PORT, help="EC data port")
    ap.add_argument("--dll", metavar="", default=DLL_NAME,
                    help="Path to InpOutx64.dll")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Verbose EC I/O logging")
    ap.add_argument("--sim", action="store_true",
                    help="Use built-in EC simulator (ignore ports/DLL)")

    sub = ap.add_subparsers(dest="module", required=True, metavar="MODULE")

    for name, handler in SUPPORTED_MODULES.items():
        sp = sub.add_parser(name, help=handler.help,
                            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        handler.add_arguments(sp)
        sp.set_defaults(_handler=handler)
    return ap


def main():
    # Handle version early to allow `--version` without a module
    if "--version" in sys.argv or "-V" in sys.argv:
        _print_version_and_exit()

    ap = build_parser()
    args = ap.parse_args()
    if getattr(args, "verbose", False):
        set_debug(True)

    try:
        ec = EcSimulator() if args.sim else EcIo(args.cmd_port, args.data_port, args.dll)
        rc = args._handler.run(args, ec)
        sys.exit(rc)
    except Exception as e:
        print("[ERROR]", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
