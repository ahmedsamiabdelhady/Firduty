"""
points_models.py — Re-exports the points models from models.py.

DutyConfirmation and MonthlyPointsSummary are defined in models/models.py
alongside all other models. This file exists only as a convenience import
alias so that services/points_service.py can import from either location.

DO NOT redefine the classes here — that causes SQLAlchemy's
"Table already defined for this MetaData" error.
"""

from models.models import DutyConfirmation, MonthlyPointsSummary

__all__ = ["DutyConfirmation", "MonthlyPointsSummary"]