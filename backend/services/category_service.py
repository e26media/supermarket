from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.models.category import Category
from backend.schemas.category import CategoryCreate

class CategoryService:

    @staticmethod
    def get_all(db: Session) -> List[Category]:
        return db.query(Category).all()

    @staticmethod
    def create(db: Session, data: CategoryCreate) -> Category:
        existing = db.query(Category).filter(Category.name == data.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Category already exists")
        cat = Category(name=data.name)
        db.add(cat)
        db.commit()
        db.refresh(cat)
        return cat

    @staticmethod
    def update(db: Session, cat_id: int, data: CategoryCreate) -> Category:
        cat = db.query(Category).filter(Category.id == cat_id).first()
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        
        # If name is changing, check for duplicates
        if data.name and data.name != cat.name:
            existing = db.query(Category).filter(Category.name == data.name).first()
            if existing:
                raise HTTPException(status_code=400, detail="Category name already exists")
            cat.name = data.name
            
        db.commit()
        db.refresh(cat)
        return cat

    @staticmethod
    def delete(db: Session, cat_id: int) -> dict:
        cat = db.query(Category).filter(Category.id == cat_id).first()
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        # Optional: check if anything is linked before deletion
        db.delete(cat)
        db.commit()
        return {"message": "Category deleted"}
