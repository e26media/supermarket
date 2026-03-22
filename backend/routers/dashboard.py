"""
routers/dashboard.py — Admin KPI endpoints
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from backend.database import get_db
from backend.services.dashboard_service import DashboardService
from backend.services.auth_service import require_admin
from backend.models.user import User

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
def daily_summary(
    target_date: Optional[date] = Query(None, description="ISO date e.g. 2024-12-25"),
    period: Optional[str] = Query(None, description="Date range: today, week, month, year"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return DashboardService.daily_summary(db, target_date=target_date, period=period)


@router.get("/top-products")
def top_products(
    limit: int = 10,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return DashboardService.top_products(db, limit)


@router.get("/low-stock")
def low_stock(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return DashboardService.low_stock_alerts(db)


@router.get("/credit-summary")
def credit_summary(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return DashboardService.credit_summary(db)


@router.get("/monthly-revenue")
def monthly_revenue(
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return DashboardService.monthly_revenue(db, year)
