from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ProductCreate(BaseModel):
    barcode: Optional[str] = None
    name: str
    category: Optional[str] = None
    image_data: Optional[str] = None
    unit: str = "pcs"
    price: float
    tax_rate: float = 0.0
    stock_qty: float = 0.0
    min_stock_alert: float = 5.0
    description: Optional[str] = None


class ProductUpdate(BaseModel):
    barcode: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    image_data: Optional[str] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    tax_rate: Optional[float] = None
    stock_qty: Optional[float] = None
    min_stock_alert: Optional[float] = None
    description: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    barcode: Optional[str]
    name: str
    category: Optional[str]
    image_data: Optional[str]
    unit: str
    price: float
    tax_rate: float
    stock_qty: float
    min_stock_alert: float
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
