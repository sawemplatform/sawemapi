"""Client for the SAWEM API."""
from sawemapi._version import __version__
from sawemapi.client import DEFAULT_TIMEOUT, LATEST, SAWEMApi, ApiReturnType
from sawemapi.errors import ApiError, ApiWarning
from sawemapi.ratelimit import DEFAULT_RATE_LIMITS, RateLimiter

__all__ = [
    "DEFAULT_RATE_LIMITS", "DEFAULT_TIMEOUT", "LATEST", "ApiError", "ApiReturnType",
    "ApiWarning", "RateLimiter", "SAWEMApi", "__version__",
]
