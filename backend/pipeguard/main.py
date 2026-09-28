import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pipeguard import __version__
from pipeguard.config import get_settings
from pipeguard.database import Base, engine, get_db
from pipeguard.routers.runs import router as runs_router
from pipeguard.schemas import HealthResponse

logger = logging.getLogger(__name__)

DbSession = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A database that cannot be reached must not stop the application from
    # starting. Blocking here means no route is ever served, including /health,
    # so the failure surfaces as requests that hang forever instead of an error
    # anyone can read. Start anyway and let /health report the problem.
    try:
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError:
        logger.exception("Could not prepare the database schema at startup")
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
app.include_router(runs_router)


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
