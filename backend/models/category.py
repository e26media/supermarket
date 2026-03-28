"""
models/category.py — Product categories
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, func
from backend.database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
