from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.subcategory_service import SubcategoryService
from backend.services.auth_service import get_current_user, require_admin
from backend.schemas.subcategory import SubcategoryCreate, SubcategoryUpdate, SubcategoryResponse
from backend.models.user import User

router = APIRouter(prefix="/subcategories", tags=["Subcategories"])

@router.get("/", response_model=List[SubcategoryResponse])
def list_subcategories(
    category: Optional[str] = Query(None, description="Filter by category name"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return SubcategoryService.get_all(db, category)

@router.post("/", response_model=SubcategoryResponse)
def create_subcategory(
    subcategory: SubcategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return SubcategoryService.create(db, subcategory)

@router.put("/{sub_id}", response_model=SubcategoryResponse)
def update_subcategory(
    sub_id: int,
    subcategory: SubcategoryUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return SubcategoryService.update(db, sub_id, subcategory)

@router.delete("/{sub_id}")
def delete_subcategory(
    sub_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return SubcategoryService.delete(db, sub_id)
