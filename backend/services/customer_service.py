from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.models.customer import Customer
from backend.models.sale import Sale

class CustomerService:
    @staticmethod
    def get_customers_summary(db: Session, q: str = None):
        # We need to return id, name, phone, total_orders, total_spending, last_purchase
        query = db.query(Customer)
        if q:
            pattern = f"%{q}%"
            query = query.filter(
                (Customer.name.ilike(pattern)) |
                (Customer.phone.ilike(pattern))
            )
        customers = query.order_by(Customer.name).all()
        result = []
        for c in customers:
            # Aggregate sales for this customer
            sales = db.query(Sale).filter(Sale.customer_id == c.id).all()
            total_orders = len(sales)
            total_spending = sum(s.total for s in sales)
            last_purchase = max([s.created_at for s in sales]) if sales else None
            
            result.append({
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "total_orders": total_orders,
                "total_spending": total_spending,
                "last_purchase": last_purchase.strftime("%Y-%m-%d") if last_purchase else "Never"
            })
        return result
