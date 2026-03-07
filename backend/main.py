"""
main.py — FastAPI application entry point for Firduty.
"""

import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import Base, engine
from routers import auth, teachers, locations, shifts, weeks, points, reports
from routers.dashboard import router as dashboard_router
from scheduler import start_scheduler, stop_scheduler
from scheduler import router as scheduler_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Firduty API starting up...")
    start_scheduler()
    yield
    logger.info("Firduty API shutting down...")
    stop_scheduler()


app = FastAPI(
    title="Firduty API",
    description="School Duty Roster Management System",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(teachers.router)
app.include_router(locations.router)
app.include_router(shifts.router)
app.include_router(weeks.router)
app.include_router(points.router)
app.include_router(reports.router)
app.include_router(dashboard_router)
app.include_router(scheduler_router)


@app.get("/")
def root():
    return {"service": "Firduty API", "version": "2.1.0", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)