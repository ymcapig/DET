# modules/base.py
from typing import Protocol, Dict
from ecio import EcIo

REGISTRY: Dict[str, 'BaseCommand'] = {}

def register(name: str):
    def deco(cls):
        REGISTRY[name] = cls()
        return cls
    return deco

class BaseCommand(Protocol):
    name: str
    help: str
    def add_arguments(self, ap) -> None: ...
    def run(self, args, ec: EcIo) -> int: ...
