from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

async def custom_rate_limit_exceeded(request, exc, retry_after_seconds: int = 30):  # default value set to 30
    return JSONResponse(
        content={"detail": "Too many requests"},
        status_code=429,
        headers={"Retry-After": str(retry_after_seconds)}
    )
