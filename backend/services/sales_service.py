"""
services/sales_service.py — Create sales, deduct stock, handle credit.
"""
from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.models.product import Product
from backend.models.sale import Sale, PaymentMode, PaymentStatus
from backend.models.sale_item import SaleItem
from backend.models.inventory import InventoryLog, MovementType
from backend.models.credit_ledger import CreditLedger
from backend.models.customer import Customer
from backend.schemas.sale import SaleCreate


class SalesService:

    @staticmethod
    def create_sale(db: Session, data: SaleCreate, user_id: int) -> Sale:
        if not data.customer_id and data.customer_phone:
            customer = db.query(Customer).filter(Customer.phone == data.customer_phone).first()
            if not customer:
                customer = Customer(
                    name=data.customer_name or "Walk-in",
                    phone=data.customer_phone
                )
                db.add(customer)
                db.commit()
                db.refresh(customer)
            data.customer_id = customer.id

        subtotal = 0.0
        tax_total = 0.0
        sale_items = []

        # ── Validate items & compute totals ────────────────────────────────
        for item_in in data.items:
            product = db.query(Product).filter(Product.id == item_in.product_id).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item_in.product_id} not found")
            if product.stock_qty < item_in.qty:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for '{product.name}' (available: {product.stock_qty})"
                )

            item_subtotal = item_in.unit_price * item_in.qty
            item_discount = item_subtotal * (item_in.discount / 100)
            item_after_discount = item_subtotal - item_discount
            item_tax = item_after_discount * (product.tax_rate / 100)
            item_total = item_after_discount + item_tax

            subtotal += item_after_discount
            tax_total += item_tax

            sale_items.append(SaleItem(
                product_id=product.id,
                product_name=product.name,
                qty=item_in.qty,
                unit_price=item_in.unit_price,
                discount=item_discount,
                tax=item_tax,
                subtotal=item_total,
            ))

        # ── Cart-level discount ─────────────────────────────────────────────
        cart_discount = (subtotal + tax_total) * (data.discount / 100) if data.discount else 0.0
        total = subtotal + tax_total - cart_discount

        # ── Credit validation ───────────────────────────────────────────────
        if data.payment_mode == "credit":
            if not data.customer_id:
                raise HTTPException(status_code=400, detail="Customer required for credit payment")
            customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
            if not customer:
                raise HTTPException(status_code=404, detail="Customer not found")
            available_credit = customer.credit_limit - customer.outstanding_credit
            if total > available_credit:
                raise HTTPException(
                    status_code=400,
                    detail=f"Credit limit exceeded. Available: ₹{available_credit:.2f}"
                )

        # ── Create Sale record ──────────────────────────────────────────────
        sale = Sale(
            customer_id=data.customer_id,
            user_id=user_id,
            subtotal=round(subtotal, 2),
            discount=round(cart_discount, 2),
            discount_pct=round(data.discount, 2),
            tax=round(tax_total, 2),
            total=round(total, 2),
            payment_mode=data.payment_mode,
            payment_status=PaymentStatus.success if data.payment_mode != "card" else PaymentStatus.pending,
            notes=data.notes,
        )
        db.add(sale)
        db.flush()  # get sale.id before committing

        # ── Attach items & deduct stock ────────────────────────────────────
        for item, item_in in zip(sale_items, data.items):
            product = db.query(Product).filter(Product.id == item_in.product_id).first()
            item.sale_id = sale.id
            db.add(item)

            before_qty = product.stock_qty
            product.stock_qty -= item_in.qty
            after_qty = product.stock_qty

            log = InventoryLog(
                product_id=product.id,
                movement_type=MovementType.sale,
                change_qty=-item_in.qty,
                before_qty=before_qty,
                after_qty=after_qty,
                reference_id=sale.id,
                reason=f"Sale #{sale.id}",
                created_by=user_id,
            )
            db.add(log)

        # ── Credit ledger entry ────────────────────────────────────────────
        if data.payment_mode == "credit" and data.customer_id:
            customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
            customer.outstanding_credit += total
            ledger = CreditLedger(
                customer_id=data.customer_id,
                sale_id=sale.id,
                entry_type="debit",
                amount=total,
                balance_after=customer.outstanding_credit,
                notes=f"Credit sale #{sale.id}",
            )
            db.add(ledger)

        db.commit()
        db.refresh(sale)
        return sale

    @staticmethod
    def get_sales(db: Session, skip: int = 0, limit: int = 100):
        return db.query(Sale).order_by(Sale.created_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def get_sale_by_id(db: Session, sale_id: int) -> Sale:
        sale = db.query(Sale).filter(Sale.id == sale_id).first()
        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")
        return sale

    @staticmethod
    def update_payment_status(db: Session, sale_id: int, status: str, ref: str = None) -> Sale:
        sale = SalesService.get_sale_by_id(db, sale_id)
        sale.payment_status = status
        if ref:
            sale.transaction_ref = ref
        db.commit()
        db.refresh(sale)
        return sale
