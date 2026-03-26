from pydantic import BaseModel, validator
from typing import Optional, Any
from datetime import datetime


def validate_strict_int(v, field_name: str):
    if v is None: return v
    try:
        val = float(v)
        if val != int(val):
            raise ValueError(f"{field_name} must be a whole number (no decimals like 1.5 allowed)")
        return int(val)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {field_name}. Must be a whole number.")



class ProductCreate(BaseModel):
    barcode: Optional[str] = None
    name: str
    category: Optional[str] = None
    image_data: Optional[str] = None
    unit: str = "pcs"
    unit_measure: Optional[str] = None
    base_unit: Optional[str] = "pcs"
    unit_value: Optional[float] = 1.0
    stock_unit: str = "pcs"
    price: float
    tax_rate: float = 0.0
    stock_qty: int = 0
    min_stock_alert: int = 5
    description: Optional[str] = None

    @validator('stock_qty', 'min_stock_alert', pre=True)
    def validate_ints(cls, v, field):
        return validate_strict_int(v, field.name.replace('_', ' ').title())


class ProductUpdate(BaseModel):
    barcode: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    image_data: Optional[str] = None
    unit: Optional[str] = None
    unit_measure: Optional[str] = None
    base_unit: Optional[str] = None
    unit_value: Optional[float] = None
    stock_unit: Optional[str] = None
    price: Optional[float] = None
    tax_rate: Optional[float] = None
    stock_qty: Optional[int] = None
    min_stock_alert: Optional[int] = None
    description: Optional[str] = None

    @validator('stock_qty', 'min_stock_alert', pre=True)
    def validate_ints(cls, v, field):
        return validate_strict_int(v, field.name.replace('_', ' ').title())


class ProductResponse(BaseModel):
    id: int
    barcode: Optional[str]
    name: str
    category: Optional[str]
    image_data: Optional[str]
    unit: str
    unit_measure: Optional[str]
    base_unit: Optional[str]
    unit_value: Optional[float]
    stock_unit: str
    price: float
    tax_rate: float
    stock_qty: int
    min_stock_alert: int
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
