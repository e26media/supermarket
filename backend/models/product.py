"""
models/product.py — Supermarket product / SKU
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    barcode = Column(String(50), unique=True, nullable=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    category = Column(String(80), nullable=True)
    subcategory_id = Column(Integer, ForeignKey("subcategories.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    image_data = Column(Text, nullable=True)
    unit = Column(String(20), default="pcs")      # pcs, kg, litre…
    unit_measure = Column(String(50), nullable=True) # e.g. "100 gm", "250 gm"
    base_unit = Column(String(20), nullable=True)    # g, ml, pcs
    unit_value = Column(Float, nullable=True)        # 100, 500, 1 etc.
    stock_unit = Column(String(20), default="pcs")   # always pcs/packets count
    price = Column(Float, nullable=False)
    tax_rate = Column(Float, default=0.0)          # percentage e.g. 5.0
    discount = Column(Float, default=0.0)          # default discount percentage
    stock_qty = Column(Integer, default=0)
    min_stock_alert = Column(Integer, default=5)   # alert threshold
    # description = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subcategory = relationship("Subcategory")

    @property
    def subcategory_name(self) -> Optional[str]:
        return self.subcategory.name if self.subcategory else None
