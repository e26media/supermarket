from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SubcategoryBase(BaseModel):
    name: str
    category: str

class SubcategoryCreate(SubcategoryBase):
    pass

class SubcategoryUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None

class SubcategoryResponse(SubcategoryBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
