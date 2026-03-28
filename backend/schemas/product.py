from pydantic import BaseModel, field_validator, FieldValidationInfo
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
    subcategory_id: Optional[int] = None
    image_data: Optional[str] = None
    unit: str = "pcs"
    unit_measure: Optional[str] = None
    base_unit: Optional[str] = "pcs"
    unit_value: Optional[float] = 1.0
    stock_unit: str = "pcs"
    price: float
    tax_rate: float = 0.0
    discount: float = 0.0
    stock_qty: int = 0
    min_stock_alert: int = 5
    description: Optional[str] = None

    @field_validator('stock_qty', 'min_stock_alert', mode='before')
    @classmethod
    def validate_ints(cls, v, info: FieldValidationInfo):
        return validate_strict_int(v, info.field_name.replace('_', ' ').title())


class ProductUpdate(BaseModel):
    barcode: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    subcategory_id: Optional[int] = None
    image_data: Optional[str] = None
    unit: Optional[str] = None
    unit_measure: Optional[str] = None
    base_unit: Optional[str] = None
    unit_value: Optional[float] = None
    stock_unit: Optional[str] = None
    price: Optional[float] = None
    tax_rate: Optional[float] = None
    discount: Optional[float] = None
    stock_qty: Optional[int] = None
    min_stock_alert: Optional[int] = None
    description: Optional[str] = None

    @field_validator('stock_qty', 'min_stock_alert', mode='before')
    @classmethod
    def validate_ints(cls, v, info: FieldValidationInfo):
        return validate_strict_int(v, info.field_name.replace('_', ' ').title())


class ProductResponse(BaseModel):
    id: int
    barcode: Optional[str]
    name: str
    category: Optional[str]
    subcategory_id: Optional[int]
    subcategory_name: Optional[str] = None
    is_active: bool = True
    image_data: Optional[str]
    unit: str
    unit_measure: Optional[str]
    base_unit: Optional[str]
    unit_value: Optional[float]
    stock_unit: str
    price: float = 0.0
    tax_rate: float = 0.0
    discount: float = 0.0
    stock_qty: int = 0
    min_stock_alert: int = 5
    description: Optional[str] = None
    created_at: datetime

    @field_validator('stock_qty', 'min_stock_alert', mode='before')
    @classmethod
    def cast_to_int(cls, v, info: FieldValidationInfo):
        if v is None: return v
        try:
            # Leniently round and cast to int for Response
            return int(round(float(v)))
        except (ValueError, TypeError):
            return 0

    class Config:
        from_attributes = True
