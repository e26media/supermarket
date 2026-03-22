"""
backend/main.py — FastAPI application entry point.

Startup:
  1. Load .env
  2. Create DB tables (if not exist)
  3. Run schema migrations
  4. Include all routers
  5. Seed default admin user if no users exist
"""
import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Import DB and models to trigger Base registration ──────────────────────────
from backend.database import engine, SessionLocal
from backend.models import User, Product, Customer, Sale, SaleItem, InventoryLog, CreditLedger
from backend.database import Base

# ── Import routers ─────────────────────────────────────────────────────────────
from backend.routers.auth import router as auth_router
from backend.routers.products import router as products_router
from backend.routers.sales import router as sales_router
from backend.routers.inventory import router as inventory_router
from backend.routers.dashboard import router as dashboard_router
from backend.routers.hardware import router as hardware_router
from backend.routers.customers import router as customers_router

# ── Create FastAPI app ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Supermarket POS + CRM API",
    description="API for the E26 Supermarket POS and CRM system",
    version="1.0.0",
)

# ── CORS — allow frontend ───────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include routers ────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(sales_router)
app.include_router(inventory_router)
app.include_router(dashboard_router)
app.include_router(hardware_router)
app.include_router(customers_router)


# ── Startup event ──────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    logger.info("Creating database tables…")
    Base.metadata.create_all(bind=engine)
    logger.info("Tables ready.")
    _run_migrations()        # ← NEW LINE ADDED
    _seed_default_admin()

# If we want add any extra column in database (migrations) we can add it here
def _run_migrations():
    """Run safe, idempotent schema migrations on every startup."""
    from sqlalchemy import text

    migrations = [
        #"ALTER TABLE products ADD COLUMN IF NOT EXISTS image_data TEXT;",
        # Add future migrations below this line ↓
        # "ALTER TABLE products ADD COLUMN IF NOT EXISTS category TEXT;",
        # "ALTER TABLE customers ADD COLUMN IF NOT EXISTS loyalty_points INT DEFAULT 0;",
    ]

    with engine.connect() as conn:
        for migration in migrations:
            try:
                conn.execute(text(migration))
                conn.commit()
                logger.info(f"✅ Migration applied: {migration[:60]}…")
            except Exception as e:
                logger.warning(f"⚠️  Migration warning: {e}")
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _seed_default_admin():
    """Create a default admin user on first run if the users table is empty."""
    from backend.services.auth_service import AuthService

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            admin = User(
                username="admin",
                full_name="System Admin",
                hashed_password=AuthService.hash_password("admin123"),
                role="admin",
            )
            db.add(admin)
            db.commit()
            logger.info("✅ Default admin created — username: admin  password: admin123")
            logger.warning("⚠️  Change the default password immediately!")
    finally:
        db.close()


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": "Supermarket POS + CRM", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}