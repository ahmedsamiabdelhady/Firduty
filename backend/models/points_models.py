"""
models/points_models.py — Points system ORM models.

Kept in a separate file to mirror the original project layout.
Imported by models/models.py relationships and points_service.py.
"""

# DutyConfirmation and MonthlyPointsSummary are defined in models/models.py
# to keep all foreign-key references in one file.
# This module re-exports them for backward compatibility with any import path
# that does:  from models.points_models import DutyConfirmation, MonthlyPointsSummary

from models.models import DutyConfirmation, MonthlyPointsSummary

__all__ = ["DutyConfirmation", "MonthlyPointsSummary"]