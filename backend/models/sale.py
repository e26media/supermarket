"""
models/sale.py — A completed sale transaction
"""
from datetime import datetime
from sqlalchemy import Column, Integer, Float, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import relationship
from backend.database import Base
import enum


class PaymentMode(str, enum.Enum):
    cash = "cash"
    upi = "upi"
    card = "card"
    credit = "credit"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subtotal = Column(Float, nullable=False)
    discount = Column(Float, default=0.0)
    discount_pct = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    total = Column(Float, nullable=False)
    payment_mode = Column(Enum(PaymentMode), default=PaymentMode.cash, nullable=False)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.pending, nullable=False)
    transaction_ref = Column(String(100), nullable=True)   # POS / UPI reference
    notes = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    customer = relationship("Customer")
    cashier = relationship("User")

    @property
    def customer_name(self) -> str | None:
        return self.customer.name if self.customer else None
