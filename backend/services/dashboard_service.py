"""
services/dashboard_service.py — Aggregate KPIs for the admin dashboard.
"""
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from backend.models.sale import Sale, PaymentStatus
from backend.models.sale_item import SaleItem
from backend.models.product import Product
from backend.models.customer import Customer
from backend.models.credit_ledger import CreditLedger


class DashboardService:

    @staticmethod
    def daily_summary(db: Session, target_date: date = None, period: str = None) -> dict:
        if period:
            today = date.today()
            if period == "week":
                start_d = today - timedelta(days=today.weekday())
                end_d = today
            elif period == "month":
                start_d = today.replace(day=1)
                end_d = today
            elif period == "year":
                start_d = today.replace(month=1, day=1)
                end_d = today
            else:
                start_d = today
                end_d = today
            start = datetime.combine(start_d, datetime.min.time())
            end = datetime.combine(end_d, datetime.max.time())
            date_str = period
        else:
            if not target_date:
                target_date = date.today()
            start = datetime.combine(target_date, datetime.min.time())
            end = datetime.combine(target_date, datetime.max.time())
            date_str = str(target_date)

        sales = db.query(Sale).filter(
            Sale.created_at >= start,
            Sale.created_at <= end,
            Sale.payment_status != PaymentStatus.failed,
        ).all()

        total_revenue = sum(s.total for s in sales)
        total_transactions = len(sales)
        cash_total = sum(s.total for s in sales if s.payment_mode.value == "cash")
        upi_total = sum(s.total for s in sales if s.payment_mode.value == "upi")
        card_total = sum(s.total for s in sales if s.payment_mode.value == "card")
        credit_total = sum(s.total for s in sales if s.payment_mode.value == "credit")

        return {
            "date": date_str,
            "total_revenue": round(total_revenue, 2),
            "total_transactions": total_transactions,
            "payment_breakdown": {
                "cash": round(cash_total, 2),
                "upi": round(upi_total, 2),
                "card": round(card_total, 2),
                "credit": round(credit_total, 2),
            },
        }

    @staticmethod
    def top_products(db: Session, limit: int = 10) -> list:
        results = (
            db.query(
                SaleItem.product_id,
                SaleItem.product_name,
                func.sum(SaleItem.qty).label("total_qty"),
                func.sum(SaleItem.subtotal).label("total_revenue"),
            )
            .group_by(SaleItem.product_id, SaleItem.product_name)
            .order_by(desc("total_revenue"))
            .limit(limit)
            .all()
        )
        return [
            {
                "product_id": r.product_id,
                "product_name": r.product_name,
                "total_qty": round(r.total_qty, 2),
                "total_revenue": round(r.total_revenue, 2),
            }
            for r in results
        ]

    @staticmethod
    def low_stock_alerts(db: Session) -> list:
        products = (
            db.query(Product)
            .filter(Product.stock_qty <= Product.min_stock_alert)
            .order_by(Product.stock_qty)
            .all()
        )
        return [
            {
                "id": p.id,
                "name": p.name,
                "stock_qty": p.stock_qty,
                "min_stock_alert": p.min_stock_alert,
                "unit": p.unit,
            }
            for p in products
        ]

    @staticmethod
    def credit_summary(db: Session) -> list:
        customers = (
            db.query(Customer)
            .filter(Customer.outstanding_credit > 0)
            .order_by(desc(Customer.outstanding_credit))
            .all()
        )
        return [
            {
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "outstanding_credit": round(c.outstanding_credit, 2),
                "credit_limit": round(c.credit_limit, 2),
            }
            for c in customers
        ]

    @staticmethod
    def monthly_revenue(db: Session, year: int = None) -> list:
        if not year:
            year = date.today().year
        results = (
            db.query(
                func.extract("month", Sale.created_at).label("month"),
                func.sum(Sale.total).label("revenue"),
                func.count(Sale.id).label("transactions"),
            )
            .filter(
                func.extract("year", Sale.created_at) == year,
                Sale.payment_status != PaymentStatus.failed,
            )
            .group_by("month")
            .order_by("month")
            .all()
        )
        return [{"month": int(r.month), "revenue": round(r.revenue, 2), "transactions": r.transactions}
                for r in results]
