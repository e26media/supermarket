"""
models/subcategory.py — Product subcategories
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, func
from backend.database import Base

class Subcategory(Base):
    __tablename__ = "subcategories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(80), nullable=False) # e.g. "food", "dairy"
    created_at = Column(DateTime, server_default=func.now())
