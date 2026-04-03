"""Vendored HAB_Predictor package bootstrap for STRATOS."""
from __future__ import annotations

import sys
from pathlib import Path


_PACKAGE_ROOT = Path(__file__).resolve().parent
_PACKAGE_ROOT_STR = str(_PACKAGE_ROOT)

if _PACKAGE_ROOT_STR not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT_STR)
