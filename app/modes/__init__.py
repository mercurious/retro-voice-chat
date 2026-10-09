"""The app's modes, one per file in this directory. A new mode is a file here with a Mode subclass that sets
an id (see base.py); it appears in the SELECT menu at its `order`."""
import importlib, os, pkgutil

from .base import Mode


def discover():
    """Every Mode subclass with an id, in menu order."""
    found = {}
    for info in pkgutil.iter_modules([os.path.dirname(__file__)]):
        if info.name == "base":
            continue
        mod = importlib.import_module(f"{__name__}.{info.name}")
        for obj in vars(mod).values():
            if isinstance(obj, type) and issubclass(obj, Mode) and obj.id and obj.__module__ == mod.__name__:
                found[obj.id] = obj
    return sorted(found.values(), key=lambda c: (c.order, c.id))
