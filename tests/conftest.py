"""Pytest configuration for Question Paper Studio test suite."""
from __future__ import annotations

import faulthandler
import os

# Disable non-fatal Windows COM RPC_E_CANTCALLOUT_ININPUTSYNCCALL (0x8001010d) stack trace noise
# emitted by faulthandler when Qt6 shows top-level widgets on Windows 11.
if os.name == "nt":
    try:
        faulthandler.disable()
    except Exception:
        pass
