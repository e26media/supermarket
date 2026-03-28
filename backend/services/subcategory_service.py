from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.models.subcategory import Subcategory
from backend.schemas.subcategory import SubcategoryCreate, SubcategoryUpdate

class SubcategoryService:

    @staticmethod
    def get_all(db: Session, category: Optional[str] = None) -> List[Subcategory]:
        query = db.query(Subcategory)
        if category:
            query = query.filter(Subcategory.category == category)
        return query.all()

    @staticmethod
    def get_by_id(db: Session, sub_id: int) -> Subcategory:
        sub = db.query(Subcategory).filter(Subcategory.id == sub_id).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Subcategory not found")
        return sub

    @staticmethod
    def create(db: Session, data: SubcategoryCreate) -> Subcategory:
        # User requested to match existing category enum/string values.
        # We assume the caller (router) handles basic validation.
        sub = Subcategory(**data.model_dump())
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    @staticmethod
    def update(db: Session, sub_id: int, data: SubcategoryUpdate) -> Subcategory:
        sub = SubcategoryService.get_by_id(db, sub_id)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(sub, field, value)
        db.commit()
        db.refresh(sub)
        return sub

    @staticmethod
    def delete(db: Session, sub_id: int) -> dict:
        from backend.models.product import Product
        sub = SubcategoryService.get_by_id(db, sub_id)
        
        # Block if products are linked
        linked_count = db.query(Product).filter(Product.subcategory_id == sub_id).count()
        if linked_count > 0:
            raise HTTPException(status_code=400, detail=f"Cannot delete: {linked_count} products are linked to this subcategory.")
            
        db.delete(sub)
        db.commit()
        return {"message": "Subcategory deleted"}
