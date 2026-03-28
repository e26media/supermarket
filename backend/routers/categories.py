from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.category_service import CategoryService
from backend.services.auth_service import get_current_user, require_admin
from backend.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from backend.models.user import User

router = APIRouter(prefix="/categories", tags=["Categories"])

@router.get("/", response_model=List[CategoryResponse])
def list_categories(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return CategoryService.get_all(db)

@router.post("/", response_model=CategoryResponse)
def create_category(
    category: CategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return CategoryService.create(db, category)

@router.put("/{cat_id}", response_model=CategoryResponse)
def update_category(
    cat_id: int,
    category: CategoryUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return CategoryService.update(db, cat_id, category)

@router.delete("/{cat_id}")
def delete_category(
    cat_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return CategoryService.delete(db, cat_id)
