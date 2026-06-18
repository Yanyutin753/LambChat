"""Compatibility alias for Feedback plugin tools."""

from __future__ import annotations

import sys

from src.plugins.feedback import tools as _tools

sys.modules[__name__] = _tools
