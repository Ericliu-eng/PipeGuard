import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pipeguard import __version__
from pipeguard.config import get_settings
from pipeguard.database import get_db
from pipeguard.routers.runs import router as runs_router
from pipeguard.schemas import HealthResponse

logger = logging.getLogger(__name__)

DbSession = Annotated[Session, Depends(get_db)]


settings = get_settings()
app = FastAPI(title=settings.app_name, version=__version__)
app.include_router(runs_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Send the bare host to the API docs.

    The README advertises this host as "open the API", and it answered 404 —
    there was no route here at all. The platform's own probes hit it too, so the
    logs filled with 404s from requests nothing had asked a question of.
    """
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health(db: DbSession, response: Response) -> HealthResponse:
    """Report whether the service can actually serve requests.

    This probes the database rather than returning a constant. A health check
    that cannot fail is not a health check: this one answered "ok" for two
    months while the database behind it no longer existed, so every dashboard
    watching it stayed green through a complete outage.
    """
    try:
        db.execute(select(1))
        database = "ok"
    except SQLAlchemyError:
        logger.exception("Health check could not reach the database")
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        service=settings.app_name,
        environment=settings.app_env,
        database=database,
    )
