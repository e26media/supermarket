# 🛒 E26 Supermarket POS + CRM System

A modern, high-performance **Point-of-Sale and CRM system** built with **FastAPI**, **HTMX**, **Jinja2**, and **PostgreSQL**. Features a sleek, responsive UI with real-time hardware integrations.

---

## 📁 Project Structure

```
Supermarket/
├── .env                        ← Your environment variables
├── requirements.txt
├── run.py                      ← Unified runner for Backend & Frontend
│
├── backend/
│   ├── main.py                 ← FastAPI entry point & migrations
│   ├── database.py             ← SQLAlchemy engine & postgres session
│   ├── models/                 ← ORM models (Product, Sale, Customer, etc.)
│   ├── schemas/                ← Pydantic request/response models
│   ├── services/               ← Business logic (Inventory, Sales, Auth)
│   └── routers/                ← REST API endpoints
│
└── frontend/
    ├── routes.py               ← HTMX-based page routing (Main Controller)
    ├── static/
    │   ├── style.css           ← Modern UI theme & glassmorphism
    │   └── assets/             ← UI Icons and product images
    └── templates/
        ├── base.html           ← Main layout with Navbar
        ├── pages/              ← Full page templates (Inventory, POS, etc.)
        └── partials/           ← Dynamic HTMX components (Modals, Rows)
```

---

## 🚀 Key Concepts: The "Golden Rule"

Our inventory system follows a unique **Count-Based Inventory** rule to avoid precision errors:
-   **Stock (qty)**: Always tracked as a count of **Pieces/Packets/Pcs**.
-   **Unit Size (unit_value)**: The physical size of each piece (e.g., `500` for 500ml milk).
-   **Smart Display**: The POS automatically calculates and shows total volume/weight.
    -   *Example*: `50 pcs (25 L total)` for a crate of 50 half-litre milk packets.
-   **Strict Integers**: All stock quantities and restocks are enforced as integers to maintain a clean ledger.

---

## ⚡ Quick Start

### 1. Prerequisites
- Python 3.10+
- PostgreSQL running locally
- Create database: `CREATE DATABASE supermarket_crm;`

### 2. Install dependencies
```powershell
pip install -r requirements.txt
```

### 3. Configure environment
Create a `.env` file based on the local environment settings (PostgreSQL URL).

### 4. Run the application
The project uses a unified runner. Simply execute:
```powershell
python run.py
```
-   **Backend Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
-   **Web Interface**: [http://localhost:8000/](http://localhost:8000/) (FastAPI serves both)

---

## 🔐 Default Credentials

| Role  | Username | Password   |
|-------|----------|------------|
| Admin | `admin`  | `admin123` |

---

## 🔌 Hardware Integrations

| Device | Type | Logic |
|--------|------|-------|
| Barcode Scanner | HID Keyboard | Real-time POS lookup |
| Digital Scale | RS-232 | `SCALE_COM_PORT` config |
| Thermal Printer | ESC/POS | Automatic receipt generation |
| Payment POS | HTTP API | Pine Labs Plutus Smart Integration |

---

## 📊 API Summary

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/token` | Get JWT access token |
| GET  | `/products/` | List all products |
| POST | `/inventory/restock` | Update stock counts (Integer-only) |
| POST | `/sales/` | Process a new sale (Atomic) |
| GET  | `/dashboard/summary` | Real-time sales KPIs |
