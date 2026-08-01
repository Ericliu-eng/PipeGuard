from contextlib import asynccontextmanager

from fastapi import FastAPI

from pipeguard.config import get_settings
from pipeguard.database import Base, engine
from pipeguard.routers.runs import router as runs_router
from pipeguard.schemas import HealthResponse


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(runs_router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.app_env,
    )

