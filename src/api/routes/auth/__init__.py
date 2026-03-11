"""
Authentication routes module

Aggregates all authentication-related routes from submodules.
"""

from fastapi import APIRouter

from .core import router as core_router
from .oauth import router as oauth_router
from .profile import router as profile_router
from .rate_limiter import RateLimiter, get_rate_limiter
from .utils import _get_client_ip, _get_frontend_url, _store_oauth_state, _verify_oauth_state
from .verification import router as verification_router

# Main router that aggregates all sub-routers
router = APIRouter()
router.include_router(core_router)
router.include_router(profile_router)
router.include_router(oauth_router)
router.include_router(verification_router)

__all__ = [
    "router",
    "RateLimiter",
    "get_rate_limiter",
    "_get_client_ip",
    "_get_frontend_url",
    "_store_oauth_state",
    "_verify_oauth_state",
]
