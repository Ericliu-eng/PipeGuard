import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from pipeguard.config import get_settings

API_KEY_HEADER = "X-API-Key"


def require_ingest_key(
    x_api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
) -> None:
    """Guard the endpoint that accepts run reports from outside.

    Disabled rather than open when no key is configured: this endpoint writes
    rows on behalf of a caller, so an unset secret must fail closed.
    """
    settings = get_settings()

    if not settings.ingest_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Run ingestion is not configured",
        )

    # Constant-time comparison: a plain == leaks the key a character at a time
    # to anyone who can measure the response.
    if not secrets.compare_digest(x_api_key or "", settings.ingest_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
