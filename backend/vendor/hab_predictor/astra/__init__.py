# -*- coding: utf-8 -*-
# @Author: p-chambers
# @Date:   2016-11-17 17:32:25
# @Last Modified by:   Paul Chambers
# @Last Modified time: 2017-05-10 22:03:57
import importlib
import logging

__all__ = [
    "flight_tools",
    "global_tools",
    "interpolate",
    "sim_manager",
    "simulator",
    "weather",
    "target_landing",
    "flight",
]


def __getattr__(name):
    if name in {"simulator", "weather", "target_landing"}:
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module

    if name == "flight":
        flight_cls = importlib.import_module(".simulator", __name__).flight
        globals()[name] = flight_cls
        return flight_cls

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))


try:  # Python 2.7+
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
logging.basicConfig(level=logging.DEBUG)
logging.getLogger(__name__).addHandler(NullHandler())
