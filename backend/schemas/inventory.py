from pydantic import BaseModel, field_validator, FieldValidationInfo
from typing import Optional, Any
from datetime import datetime


class InventoryRestockRequest(BaseModel):
    product_id: int
    qty: int
    reason: Optional[str] = "Restock"

    @field_validator('qty', mode='before')
    @classmethod
    def qty_must_be_whole_number(cls, v, info: FieldValidationInfo):
        if v is None: return v
        try:
            val = float(v)
            if val != int(val):
                raise ValueError("Quantity must be a positive whole number (no decimals like 1.5 allowed)")
            if val < 1:
                raise ValueError("Quantity must be at least 1")
            return int(val)
        except (ValueError, TypeError):
            raise ValueError("Invalid quantity. Must be a whole number.")


class InventoryLogResponse(BaseModel):
    id: int
    product_id: int
    movement_type: str
    change_qty: float
    before_qty: Optional[float]
    after_qty: Optional[float]
    reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
