"""
services/inventory_service.py — Stock management and audit log.
"""
from typing import List
from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.models.product import Product
from backend.models.inventory import InventoryLog, MovementType
from backend.schemas.inventory import InventoryRestockRequest


class InventoryService:

    @staticmethod
    def restock(db: Session, data: InventoryRestockRequest, user_id: int) -> InventoryLog:
        product = db.query(Product).filter(Product.id == data.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        before_qty = product.stock_qty
        product.stock_qty += data.qty
        after_qty = product.stock_qty

        log = InventoryLog(
            product_id=product.id,
            movement_type=MovementType.restock,
            change_qty=data.qty,
            before_qty=before_qty,
            after_qty=after_qty,
            reason=data.reason or "Restock",
            created_by=user_id,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def adjust_stock(db: Session, product_id: int, qty_change: int,
                     reason: str, user_id: int) -> InventoryLog:
        """Manual positive or negative stock adjustment."""
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        before_qty = product.stock_qty
        product.stock_qty += qty_change
        after_qty = product.stock_qty

        log = InventoryLog(
            product_id=product.id,
            movement_type=MovementType.adjustment,
            change_qty=qty_change,
            before_qty=before_qty,
            after_qty=after_qty,
            reason=reason,
            created_by=user_id,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_logs(db: Session, product_id: int = None, limit: int = 200) -> List[InventoryLog]:
        q = db.query(InventoryLog).order_by(InventoryLog.created_at.desc())
        if product_id:
            q = q.filter(InventoryLog.product_id == product_id)
        return q.limit(limit).all()

    @staticmethod
    def get_low_stock(db: Session) -> List[Product]:
        return (
            db.query(Product)
            .filter(Product.stock_qty <= Product.min_stock_alert)
            .order_by(Product.stock_qty)
            .all()
        )
