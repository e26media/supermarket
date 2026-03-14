"""
models/product.py — Supermarket product / SKU
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from backend.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    barcode = Column(String(50), unique=True, nullable=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    category = Column(String(80), nullable=True)
    image_data = Column(Text, nullable=True)
    unit = Column(String(20), default="pcs")      # pcs, kg, litre…
    price = Column(Float, nullable=False)
    tax_rate = Column(Float, default=0.0)          # percentage e.g. 5.0
    stock_qty = Column(Float, default=0.0)
    min_stock_alert = Column(Float, default=5.0)   # alert threshold
    description = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
