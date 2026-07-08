"""Compatibility alias for the Feedback static plugin routes."""

from __future__ import annotations

import sys

from src.plugins.feedback import routes as _routes

sys.modules[__name__] = _routes
