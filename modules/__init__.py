# modules/__init__.py
from .ecversion import ECVersion  # noqa: F401
from .raw import RawCommand       # noqa: F401
from .led import LedControl       # noqa: F401
from .fan import FanControl       # noqa: F401
from .temp import Temperature      # noqa: F401
from .battery import Battery       # noqa: F401
from .kblight import KeyboardBacklight  # noqa: F401
from .kbtype import KeyboardType   # noqa: F401
from .smbios import SMBIOS       # noqa: F401

from .base import REGISTRY
SUPPORTED_MODULES = REGISTRY
