from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class SaleItemIn(BaseModel):
    product_id: int
    qty: float
    unit_price: float
    discount: float = 0.0  # per-item discount %


class SaleCreate(BaseModel):
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    items: List[SaleItemIn]
    discount: float = 0.0         # overall cart discount %
    payment_mode: str = "cash"    # cash | upi | card | credit
    notes: Optional[str] = None


class SaleItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    qty: float
    unit_price: float
    discount: float
    tax: float
    subtotal: float

    class Config:
        from_attributes = True


class SaleResponse(BaseModel):
    id: int
    customer_id: Optional[int]
    customer_name: Optional[str] = None
    user_id: int
    subtotal: float
    discount: float
    discount_pct: float
    tax: float
    total: float
    payment_mode: str
    payment_status: str
    transaction_ref: Optional[str]
    notes: Optional[str]
    created_at: datetime
    items: List[SaleItemResponse] = []

    class Config:
        from_attributes = True
