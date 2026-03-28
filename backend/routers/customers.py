from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.auth_service import get_current_user
from backend.services.customer_service import CustomerService
from backend.models.user import User

router = APIRouter(prefix="/customers", tags=["Customers"])

@router.get("/")
def get_customers(q: str = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return CustomerService.get_customers_summary(db, q=q)
