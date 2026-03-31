from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from backend.models.customer import Customer
from backend.models.sale import Sale
from backend.models.sale_item import SaleItem

class CustomerService:
    @staticmethod
    def get_customers_summary(db: Session, q: str = None):
        # ... existing implementation ...
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

    @staticmethod
    def get_customer_insights(db: Session, customer_id: int):
        customer = db.query(Customer).get(customer_id)
        if not customer:
            return None

        sales = db.query(Sale).filter(Sale.customer_id == customer_id).all()
        total_orders = len(sales)
        total_spending = sum(s.total for s in sales)
        last_purchase = max([s.created_at for s in sales]) if sales else None

        # Fetch highest purchased products
        top_products = (
            db.query(
                SaleItem.product_name,
                func.sum(SaleItem.qty).label("total_qty")
            )
            .join(Sale)
            .filter(Sale.customer_id == customer_id)
            .group_by(SaleItem.product_name)
            .order_by(desc("total_qty"))
            .limit(5)
            .all()
        )

        return {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "total_orders": total_orders,
            "total_spending": round(total_spending, 2),
            "last_purchase": last_purchase.strftime("%Y-%m-%d") if last_purchase else "Never",
            "top_products": [
                {"name": p.product_name, "qty": round(p.total_qty, 2)}
                for p in top_products
            ]
        }
