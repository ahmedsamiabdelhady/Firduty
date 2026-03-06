"""FastAPI application entry point for Firduty backend."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
from routers import auth, teachers, locations, shifts, weeks, points, reports

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Create all tables on startup (including new points tables)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Firduty API",
    description="School Duty Roster Management System with Points",
    version="2.0.0"
)

# CORS — allow admin UI and Flutter app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ─────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(teachers.router)
app.include_router(locations.router)
app.include_router(shifts.router)
app.include_router(weeks.router)
app.include_router(points.router)    # Duty confirmation & teacher points
app.include_router(reports.router)   # Admin monthly reports


@app.get("/")
def root():
    return {"service": "Firduty API", "version": "2.0.0", "status": "running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}