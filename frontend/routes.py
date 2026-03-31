"""
frontend/routes.py — FastAPI app serving the HTMX-powered HTML frontend.

Architecture:
  - Jinja2Templates for HTML rendering
  - Session-keyed in-memory cart (per-tab via cookie session ID)
  - Proxies API calls to the existing backend at BACKEND_URL
  - Serves static files from frontend/static/
  - All HTMX fragment endpoints return partial HTML

Run:
    uvicorn frontend.routes:app --host 0.0.0.0 --port 8001 --reload
"""
import os
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv
import base64
from fastapi import FastAPI, Request, Response, Form, Query, Cookie, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

logger = logging.getLogger("frontend")
logging.basicConfig(level=logging.INFO)

# ── Config ──────────────────────────────────────────────────────────────────
BACKEND_URL: str = os.getenv("BACKEND_URL", os.getenv("API_BASE", "http://127.0.0.1:8000"))
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR    = Path(__file__).parent / "static"

# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="Supermarket POS — Frontend", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ── In-memory cart store (session_id → cart_state) ──────────────────────────
# cart_state = {
#   "items": [{"product_id", "name", "unit", "unit_price", "qty",
#              "discount", "subtotal", "image_data"}],
#   "cart_discount": 0.0,
#   "cust_name": "", "cust_phone": ""
# }
CARTS: Dict[str, dict] = {}

def _get_cart(session_id: str) -> dict:
    if session_id not in CARTS:
        CARTS[session_id] = {"items": [], "cart_discount": 0.0, "cust_name": "", "cust_phone": ""}
    return CARTS[session_id]

def _recalc(cart: dict):
    """Recalculate subtotals and taxes on every item."""
    for item in cart["items"]:
        item["subtotal"] = item["unit_price"] * item["qty"] * (1 - item["discount"] / 100)
        item["tax"] = item["subtotal"] * (item.get("tax_rate", 0) / 100)

def _session_id(request: Request) -> str:
    """Identify the cart session. Prioritizes the JWT token if present."""
    token = _token(request)
    if token:
        # Use token itself as a stable key. In-memory CARTS handles long keys fine.
        return f"auth_{token}"
    # Fallback to cookie for non-HTMX or guest access
    return request.cookies.get("session_id", "guest_default")

def _ensure_session(response: Response, session_id: str) -> str:
    response.set_cookie("session_id", session_id, httponly=True, samesite="lax")
    return session_id

# ── Backend API proxy helper ─────────────────────────────────────────────────
async def _api(
    method: str,
    path: str,
    token: Optional[str] = None,
    **kwargs
) -> dict:
    """Returns {'data': ..., 'status': ..., 'error': ...}"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=8.0) as client:
            resp = await getattr(client, method)(path, headers=headers, **kwargs)
            if resp.status_code in (200, 201):
                return {"data": resp.json(), "status": resp.status_code, "error": None}
            
            err_msg = resp.text[:200]
            try:
                detail = resp.json().get("detail", err_msg)
                if isinstance(detail, list): # handle pydantic validation errors
                    detail = str(detail[0].get("msg")) if detail else err_msg
                err_msg = detail
            except:
                pass
            
            logger.warning(f"Backend {method.upper()} {path} → {resp.status_code}: {err_msg}")
            return {"data": None, "status": resp.status_code, "error": err_msg}
    except Exception as e:
        logger.error(f"Backend call failed: {e}")
        return {"data": None, "status": 500, "error": str(e)}

def _token(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header (set by HTMX via app.js)."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None

# ── Template context helper ──────────────────────────────────────────────────
def _ctx(request: Request, **extra) -> dict:
    base = {"request": request, "api_base": BACKEND_URL}
    base.update(extra)
    return base

async def _to_base64(file: UploadFile) -> Optional[str]:
    """Convert UploadFile to base64 string."""
    if not file or not file.filename:
        return None
    try:
        content = await file.read()
        if not content:
            return None
        return base64.b64encode(content).decode("utf-8")
    except Exception as e:
        logger.error(f"Image encoding failed: {e}")
        return None

# ════════════════════════════════════════════════════════════════════════════
#  PAGE ROUTES (full HTML pages)
# ════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context=_ctx(request))


@app.get("/app/pos", response_class=HTMLResponse)
async def pos_page(request: Request):
    return templates.TemplateResponse(request=request, name="pos.html", context=_ctx(request))


@app.get("/app/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return templates.TemplateResponse(request=request, name="analytics.html", context=_ctx(request))


@app.get("/app/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request):
    return templates.TemplateResponse(request=request, name="inventory.html", context=_ctx(request))


@app.get("/app/customers", response_class=HTMLResponse)
async def customers_page(request: Request):
    return templates.TemplateResponse(request=request, name="customers.html", context=_ctx(request))


@app.get("/app/help", response_class=HTMLResponse)
async def help_page(request: Request):
    return templates.TemplateResponse(request=request, name="help.html", context=_ctx(request))


@app.get("/app/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse(request=request, name="settings.html", context=_ctx(request))


# ════════════════════════════════════════════════════════════════════════════
#  CATEGORY MANAGEMENT — /inventory/categories
# ════════════════════════════════════════════════════════════════════════════

@app.get("/inventory/categories", response_class=HTMLResponse)
async def inv_categories_tab(request: Request):
    token = _token(request)
    cat_resp = await _api("get", "/categories/", token=token)
    categories = cat_resp["data"] or []
    
    return HTMLResponse(f"""
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
        <!-- Left Panel: Categories -->
        <div class="card">
            <div class="card-title">📂 Categories</div>
            <form hx-post="/inventory/categories/add" hx-target="#category-list-container" hx-swap="innerHTML" style="margin-bottom:15px;">
                <div class="form-group">
                    <label class="form-label">New Category Name</label>
                    <div style="display:flex; gap:8px;">
                        <input class="form-control" name="name" required placeholder="e.g. frozen foods" style="margin-bottom:0;">
                        <button type="submit" class="btn btn-primary">Add</button>
                    </div>
                </div>
            </form>
            <div id="category-list-container" hx-get="/inventory/categories/list" hx-trigger="load">
                <span class="spinner"></span> Loading...
            </div>
        </div>

        <!-- Right Panel: Subcategories -->
        <div class="card">
            <div class="card-title">🌿 Subcategories</div>
            <div class="form-group" style="margin-bottom:15px;">
                <label class="form-label">Select Category</label>
                <select class="form-control" id="mgmt-category-select" name="category" 
                        hx-get="/inventory/subcategories/list" hx-target="#subcategory-list-container" hx-trigger="change, load">
                    {"".join(f'<option value="{c["name"]}">{c["name"]}</option>' for c in categories)}
                </select>
            </div>
            <form hx-post="/inventory/subcategories/add" hx-target="#subcategory-list-container" hx-swap="innerHTML" style="margin-bottom:15px;">
                <input type="hidden" name="category" id="hidden-category-input">
                <script>
                    document.body.addEventListener('htmx:configRequest', (event) => {{
                        if (event.detail.path === '/inventory/subcategories/add') {{
                            event.detail.parameters['category'] = document.getElementById('mgmt-category-select').value;
                        }}
                    }});
                </script>
                <div class="form-group">
                    <label class="form-label">New Subcategory Name</label>
                    <div style="display:flex; gap:8px;">
                        <input class="form-control" name="name" required placeholder="e.g. ice cream" style="margin-bottom:0;">
                        <button type="submit" class="btn btn-primary">Add</button>
                    </div>
                </div>
            </form>
            <div id="subcategory-list-container">
                <div style="text-align:center; padding:20px; color:var(--text-muted);">Select a category to see subcategories</div>
            </div>
        </div>
    </div>
    """)

@app.get("/inventory/categories/list", response_class=HTMLResponse)
async def inv_categories_list(request: Request):
    token = _token(request)
    resp = await _api("get", "/categories/", token=token)
    categories = resp["data"] or []
    rows = "".join(f"""
    <div id="category-row-{c['id']}" style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
        <span>{c['name']}</span>
        <div style="display:flex; gap:5px;">
            <button class="btn btn-secondary btn-sm" hx-get="/inventory/categories/edit/{c['id']}" hx-target="#category-row-{c['id']}" hx-swap="outerHTML">✏️</button>
            <button class="btn btn-danger btn-sm" hx-delete="/inventory/categories/{c['id']}" hx-target="#category-list-container" hx-confirm="Delete category '{c['name']}'?">🗑️</button>
        </div>
    </div>""" for c in categories)
    return HTMLResponse(rows if rows else "No categories found.")

@app.post("/inventory/categories/add", response_class=HTMLResponse)
async def inv_categories_add(request: Request, name: str = Form(...)):
    token = _token(request)
    await _api("post", "/categories/", token=token, json={"name": name.strip().lower()})
    return await inv_categories_list(request)

@app.delete("/inventory/categories/{cat_id}", response_class=HTMLResponse)
async def inv_categories_delete(request: Request, cat_id: int):
    token = _token(request)
    await _api("delete", f"/categories/{cat_id}", token=token)
    return await inv_categories_list(request)

@app.get("/inventory/categories/edit/{cat_id}", response_class=HTMLResponse)
async def inv_categories_edit_row(request: Request, cat_id: int):
    token = _token(request)
    resp = await _api("get", "/categories/", token=token)
    categories = resp["data"] or []
    cat = next((c for c in categories if c["id"] == cat_id), None)
    if not cat: return HTMLResponse("Not found")
    
    return HTMLResponse(f"""
    <div id="category-row-{cat_id}" style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
        <form hx-post="/inventory/categories/edit/{cat_id}" hx-target="#category-list-container" style="display:flex; gap:8px; width:100%;">
            <input class="form-control" name="name" value="{cat['name']}" style="margin-bottom:0; flex:1;">
            <button type="submit" class="btn btn-primary btn-sm">💾</button>
            <button type="button" class="btn btn-secondary btn-sm" hx-get="/inventory/categories/list" hx-target="#category-list-container">❌</button>
        </form>
    </div>
    """)

@app.post("/inventory/categories/edit/{cat_id}", response_class=HTMLResponse)
async def inv_categories_update(request: Request, cat_id: int, name: str = Form(...)):
    token = _token(request)
    await _api("put", f"/categories/{cat_id}", token=token, json={"name": name.strip().lower()})
    return await inv_categories_list(request)

@app.get("/inventory/subcategories/list", response_class=HTMLResponse)
async def inv_subcategories_list(request: Request, category: str = Query("")):
    token = _token(request)
    if not category: return HTMLResponse("")
    resp = await _api("get", f"/subcategories/?category={category}", token=token)
    subs = resp["data"] or []
    rows = "".join(f"""
    <div id="subcategory-row-{s['id']}" style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
        <span>{s['name']}</span>
        <div style="display:flex; gap:5px;">
            <button class="btn btn-secondary btn-sm" hx-get="/inventory/subcategories/edit/{s['id']}" hx-target="#subcategory-row-{s['id']}" hx-swap="outerHTML">✏️</button>
            <button class="btn btn-danger btn-sm" hx-delete="/inventory/subcategories/{s['id']}" hx-target="#subcategory-list-container" hx-confirm="Delete subcategory '{s['name']}'?">🗑️</button>
        </div>
    </div>""" for s in subs)
    return HTMLResponse(rows if rows else "No subcategories found for this category.")

@app.post("/inventory/subcategories/add", response_class=HTMLResponse)
async def inv_subcategories_add(request: Request, name: str = Form(...), category: str = Form(...)):
    token = _token(request)
    await _api("post", "/subcategories/", token=token, json={"name": name.strip().lower(), "category": category})
    return await inv_subcategories_list(request, category=category)

@app.delete("/inventory/subcategories/{sub_id}", response_class=HTMLResponse)
async def inv_subcategories_delete(request: Request, sub_id: int):
    token = _token(request)
    # To refresh the list, we need the parent category. For simplicity, we'll try to get it.
    sub_resp = await _api("get", f"/subcategories/", token=token) # hack to find category
    subs = sub_resp["data"] or []
    parent_cat = next((s["category"] for s in subs if s["id"] == sub_id), "")
    
    await _api("delete", f"/subcategories/{sub_id}", token=token)
    return await inv_subcategories_list(request, category=parent_cat)

@app.get("/inventory/subcategories/edit/{sub_id}", response_class=HTMLResponse)
async def inv_subcategories_edit_row(request: Request, sub_id: int):
    token = _token(request)
    # We need to find the subcategory name and the parent category
    sub_resp = await _api("get", f"/subcategories/", token=token)
    subs = sub_resp["data"] or []
    sub = next((s for s in subs if s["id"] == sub_id), None)
    if not sub: return HTMLResponse("Not found")

    return HTMLResponse(f"""
    <div id="subcategory-row-{sub_id}" style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
        <form hx-post="/inventory/subcategories/edit/{sub_id}" hx-target="#subcategory-list-container" style="display:flex; gap:8px; width:100%;">
            <input type="hidden" name="category" value="{sub['category']}">
            <input class="form-control" name="name" value="{sub['name']}" style="margin-bottom:0; flex:1;">
            <button type="submit" class="btn btn-primary btn-sm">💾</button>
            <button type="button" class="btn btn-secondary btn-sm" 
                    hx-get="/inventory/subcategories/list?category={sub['category']}" hx-target="#subcategory-list-container">❌</button>
        </form>
    </div>
    """)

@app.post("/inventory/subcategories/edit/{sub_id}", response_class=HTMLResponse)
async def inv_subcategories_update(request: Request, sub_id: int, name: str = Form(...), category: str = Form(...)):
    token = _token(request)
    await _api("put", f"/subcategories/{sub_id}", token=token, json={"name": name.strip().lower(), "category": category})
    return await inv_subcategories_list(request, category=category)


# ════════════════════════════════════════════════════════════════════════════
#  POS PARTIAL ROUTES — /pos/*
# ════════════════════════════════════════════════════════════════════════════

@app.get("/pos/products", response_class=HTMLResponse)
async def pos_products(request: Request, status: str = "all"):
    token = _token(request)
    resp = await _api("get", "/products/", token=token)
    products = resp["data"] or []
    # Filter by status
    if status == "in_stock":
        products = [p for p in products if p.get("stock_qty", 0) > p.get("min_stock_alert", 0)]
    elif status == "low_stock":
        products = [p for p in products if 0 < p.get("stock_qty", 0) <= p.get("min_stock_alert", 0)]
    elif status == "out_of_stock":
        products = [p for p in products if p.get("stock_qty", 0) <= 0]
    return templates.TemplateResponse(request=request, name="partials/product_list.html", context=_ctx(request, products=products)
    )


@app.get("/pos/search", response_class=HTMLResponse)
async def pos_search(request: Request, q: str = ""):
    token = _token(request)
    if not q or len(q) < 2:
        resp = await _api("get", "/products/", token=token)
    else:
        resp = await _api("get", f"/products/search?q={q}", token=token)
    products = resp["data"] or []
    return templates.TemplateResponse(request=request, name="partials/product_list.html", context=_ctx(request, products=products)
    )


@app.get("/pos/recent-bills", response_class=HTMLResponse)
async def recent_bills(request: Request):
    token = _token(request)
    resp = await _api("get", "/sales/?limit=10", token=token)
    sales = resp["data"] or []
    bills = []
    for s in sales:
        bills.append({
            "id": s.get("id"),
            "customer_name": s.get("customer_name") or "Walk-in",
            "item_count": len(s.get("items", [])),
            "total": s.get("total", 0),
            "payment_mode": s.get("payment_mode", "cash"),
        })
    return templates.TemplateResponse(request=request, name="partials/recent_bills.html", context=_ctx(request, bills=bills)
    )


# ── Cart endpoints ────────────────────────────────────────────────────────
@app.get("/pos/cart", response_class=HTMLResponse)
async def get_cart(request: Request):
    sid = _session_id(request)
    cart = _get_cart(sid)
    _recalc(cart)
    return templates.TemplateResponse(request=request, name="partials/cart.html", context=_ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
    )


@app.post("/pos/cart/add/{product_id}", response_class=HTMLResponse)
async def add_to_cart(request: Request, product_id: int):
    sid = _session_id(request)
    cart = _get_cart(sid)
    token = _token(request)
    resp = await _api("get", f"/products/{product_id}", token=token)
    product = resp["data"]
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if already in cart
    for item in cart["items"]:
        if item["product_id"] == product_id:
            # Check stock before incrementing
            if item["qty"] < item.get("stock_qty", 999):
                item["qty"] += 1
            _recalc(cart)
            return templates.TemplateResponse(request=request, name="partials/cart.html", context=_ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"]))

    cart["items"].append({
        "product_id": product_id,
        "name": product["name"],
        "unit": product.get("unit", "pcs"),
        "unit_price": product["price"],
        "qty": 1,
        "stock_qty": product.get("stock_qty", 0),
        "discount": product.get("discount", 0.0),
        "tax_rate": product.get("tax_rate", 0.0),
        "image_data": product.get("image_data"),
        "subtotal": product["price"],
        "tax": product["price"] * (product.get("tax_rate", 0.0) / 100)
    })
    _recalc(cart)
    return templates.TemplateResponse(request=request, name="partials/cart.html", context=_ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
    )


@app.patch("/pos/cart/qty/{product_id}", response_class=HTMLResponse)
async def change_qty(request: Request, product_id: int,
                     delta: float = 1, float: bool = False):
    sid = _session_id(request)
    cart = _get_cart(sid)
    for item in cart["items"]:
        if item["product_id"] == product_id:
            step = 0.5 if float else 1
            if delta > 0:
                # Increment: check stock
                if item["qty"] < item.get("stock_qty", 999):
                    item["qty"] += step
            else:
                # Decrement: don't go below 1
                if item["qty"] > 1:
                    item["qty"] -= step
            break
    _recalc(cart)
    return templates.TemplateResponse(request=request, name="partials/cart.html", context=_ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
    )


@app.patch("/pos/cart/discount/{product_id}", response_class=HTMLResponse)
async def set_item_discount(request: Request,
                             product_id: int,
                             discount: float = Form(0)):
    sid = _session_id(request)
    cart = _get_cart(sid)
    for item in cart["items"]:
        if item["product_id"] == product_id:
            item["discount"] = max(0, min(100, discount))
            break
    _recalc(cart)
    return templates.TemplateResponse(request=request, name="partials/cart.html", context=_ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
    )


@app.patch("/pos/cart/cart-discount", response_class=HTMLResponse)
async def set_cart_discount(request: Request,
                             discount: float = Form(0)):
    sid = _session_id(request)
    cart = _get_cart(sid)
    cart["cart_discount"] = max(0, min(100, discount))
    _recalc(cart)
    return templates.TemplateResponse(request=request, name="partials/cart.html", context=_ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
    )


@app.delete("/pos/cart/item/{product_id}", response_class=HTMLResponse)
async def remove_cart_item(request: Request,
                            product_id: int):
    sid = _session_id(request)
    cart = _get_cart(sid)
    cart["items"] = [i for i in cart["items"] if i["product_id"] != product_id]
    _recalc(cart)
    return templates.TemplateResponse(request=request, name="partials/cart.html", context=_ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
    )


@app.delete("/pos/cart", response_class=HTMLResponse)
async def clear_cart(request: Request):
    sid = _session_id(request)
    CARTS.pop(sid, None)
    return templates.TemplateResponse(request=request, name="partials/cart.html", context=_ctx(request, cart=[], cart_discount=0.0)
    )


# ── Payment modal flow ────────────────────────────────────────────────────
@app.get("/pos/modal/customer", response_class=HTMLResponse)
async def modal_customer(request: Request):
    return templates.TemplateResponse(request=request, name="partials/bill_modal.html", context=_ctx(request))


@app.post("/pos/modal/payment", response_class=HTMLResponse)
async def modal_payment(request: Request,
                        cust_name: str = Form(""),
                        cust_phone: str = Form("")):
    sid = _session_id(request)
    cart = _get_cart(sid)
    cart["cust_name"] = cust_name
    cart["cust_phone"] = cust_phone
    _recalc(cart)
    subtotal = sum(i["subtotal"] for i in cart["items"])
    total_tax = sum(i.get("tax", 0) for i in cart["items"])
    disc = (subtotal + total_tax) * (cart.get("cart_discount", 0) / 100)
    grand_total = subtotal + total_tax - disc
    return templates.TemplateResponse(request=request, name="partials/payment.html", context=_ctx(request, cust_name=cust_name, cust_phone=cust_phone, grand_total=grand_total)
    )


@app.post("/pos/modal/verify", response_class=HTMLResponse)
async def modal_verify(request: Request,
                       payment_mode: str = Form("cash"),
                       cust_name: str = Form(""),
                       cust_phone: str = Form(""),
                       grand_total: float = Form(0)):
    sid = _session_id(request)
    cart = _get_cart(sid)
    token = _token(request)
    _recalc(cart)

    # Build sale payload for backend
    payload = {
        "items": [
            {
                "product_id": i["product_id"],
                "qty": i["qty"],
                "unit_price": i["unit_price"],
                "discount": i["discount"],
            }
            for i in cart["items"]
        ],
        "discount": cart.get("cart_discount", 0),
        "payment_mode": payment_mode,
        "customer_name": cust_name if cust_name else None,
        "customer_phone": cust_phone if cust_phone else None,
        "customer_id": None,
    }

    # For card payments, initiate Pine Labs first
    if payment_mode == "card":
        await _api("post", "/hardware/payment/initiate",
                   token=token,
                   json={"amount": grand_total, "payment_mode": "card"})

    sale_resp = await _api("post", "/sales/", token=token, json=payload)
    sale = sale_resp["data"]

    if not sale:
        err = sale_resp.get("error") or "Unknown error"
        return HTMLResponse(
            content=f"""<div class='modal-backdrop'><div class='modal'>
            <div style='color:var(--accent); text-align:center; padding:20px;'>
              ❌ TRANSACTION FAILED: {err}<br>
              <span style="color:var(--text-muted); font-size:0.75rem;">(Debug Info - Status: {sale_resp['status']}, Sid: {sid[:10]})</span>
            </div>
            <button class='btn btn-secondary btn-full' onclick='closeModal()'>Close</button>
            </div></div>""",
            status_code=200
        )

    # Print receipt via hardware endpoint
    receipt_payload = {
        "sale_id": sale["id"],
        "cashier": "",
        "created_at": sale.get("created_at", "")[:16].replace("T", " "),
        "payment_mode": sale["payment_mode"],
        "items": [
            {"name": i["product_name"], "qty": i["qty"],
             "unit_price": i["unit_price"], "subtotal": i["subtotal"]}
            for i in sale.get("items", [])
        ],
        "subtotal": sale["subtotal"],
        "discount": sale["discount"],
        "tax": sale["tax"],
        "total": sale["total"],
    }
    await _api("post", "/hardware/print", token=token, json=receipt_payload)

    # Clear cart after successful sale
    CARTS.pop(sid, None)

    created_at = sale.get("created_at", "")[:16].replace("T", " ")
    return templates.TemplateResponse(request=request, name="partials/receipt.html", context=_ctx(request,
             sale_id=sale["id"],
             customer_name=cust_name or None,
             payment_mode=payment_mode,
             created_at=created_at,
             items=[{
                 "name": i["product_name"],
                 "qty": i["qty"],
                 "unit_price": i["unit_price"],
                 "subtotal": i["subtotal"],
             } for i in sale.get("items", [])],
             subtotal=sale["subtotal"],
             discount=sale["discount"],
             discount_pct=sale.get("discount_pct", 0),
             tax=sale["tax"],
             total=sale["total"])
    )


# ════════════════════════════════════════════════════════════════════════════
#  ANALYTICS PARTIAL ROUTES — /analytics/*
# ════════════════════════════════════════════════════════════════════════════

@app.get("/analytics/summary", response_class=HTMLResponse)
async def analytics_summary(request: Request):
    from datetime import date
    token = _token(request)
    today = date.today().isoformat()
    resp = await _api("get", f"/dashboard/summary?target_date={today}", token=token)
    summary = resp["data"] or {}
    pb = summary.get("payment_breakdown", {})
    kpis = [
        {"label": "Today's Revenue", "value": f"₹{int(summary.get('total_revenue', 0)):,}", "sub": ""},
        {"label": "Transactions", "value": summary.get("total_transactions", 0), "sub": "today"},
        {"label": "Cash", "value": f"₹{int(pb.get('cash', 0)):,}", "sub": ""},
        {"label": "UPI / Card", "value": f"₹{int(pb.get('upi', 0) + pb.get('card', 0)):,}", "sub": ""},
    ]
    html_parts = []
    for k in kpis:
        html_parts.append(f"""
        <div class="kpi-card">
          <div class="kpi-label">{k['label']}</div>
          <div class="kpi-value">{k['value']}</div>
          <div class="kpi-sub">{k['sub']}</div>
        </div>""")
    return HTMLResponse("".join(html_parts))


@app.get("/analytics/sales", response_class=HTMLResponse)
async def analytics_sales(request: Request, range: str = "week"):
    token = _token(request)
    
    if range == "year":
        resp = await _api("get", "/dashboard/monthly-revenue", token=token)
        data = resp["data"] or []
        months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        
        if not data:
            return HTMLResponse("<div style='color:var(--text-muted);padding:20px;text-align:center;'>No sales data available yet for this year.</div>")

        max_rev = max((m.get("revenue", 0) for m in data), default=1) or 1
        bars = []
        # Sort by month and take up to 12
        for m in sorted(data, key=lambda x: x.get("month", 0)):
            mo = m.get("month", 1)
            rev = m.get("revenue", 0)
            pct = max(4, int((rev / max_rev) * 100))
            label = months[int(mo) - 1]
            val_str = f"₹{int(rev//1000)}k" if rev >= 1000 else f"₹{int(rev)}"
            bars.append(f"""
            <div style="display:flex;flex-direction:column;align-items:center;gap:4px;flex:1;min-width:32px;">
              <div style="font-size:0.65rem;color:var(--text-muted);">{val_str}</div>
              <div style="width:100%;background:var(--accent);border-radius:4px 4px 0 0;height:{pct}%;min-height:4px;
                          transition:height 0.4s cubic-bezier(0.19,1,0.22,1);"></div>
              <div style="font-size:0.7rem;color:var(--text-muted);">{label}</div>
            </div>""")
    else:
        # Week or Month -> daily data
        days = 7 if range == "week" else 30
        resp = await _api("get", f"/dashboard/daily-revenue?days={days}", token=token)
        data = resp["data"] or []
        
        if not data:
            return HTMLResponse(f"<div style='color:var(--text-muted);padding:20px;text-align:center;'>No sales data available for the last {days} days.</div>")

        max_rev = max((d.get("revenue", 0) for d in data), default=1) or 1
        bars = []
        for d in data:
            date_obj = datetime.strptime(d["date"], "%Y-%m-%d")
            # For week, use day name (Mon, Tue). For month, use date (Mar 25).
            if range == "week":
                label = date_obj.strftime("%a")
            else:
                label = date_obj.strftime("%b %d")
            
            rev = d.get("revenue", 0)
            pct = max(4, int((rev / max_rev) * 100))
            val_str = f"₹{int(rev//1000)}k" if rev >= 1000 else f"₹{int(rev)}"
            
            bars.append(f"""
            <div style="display:flex;flex-direction:column;align-items:center;gap:4px;flex:1;min-width:28px;">
              <div style="font-size:0.6rem;color:var(--text-muted);">{val_str}</div>
              <div style="width:100%;background:var(--accent);border-radius:4px 4px 0 0;height:{pct}%;min-height:4px;
                          transition:height 0.4s cubic-bezier(0.19,1,0.22,1);"></div>
              <div style="font-size:0.65rem;color:var(--text-muted);">{label}</div>
            </div>""")
    
    chart_html = f"""
    <div style="display:flex;align-items:flex-end;gap:6px;height:220px;padding:12px 8px;overflow-x:auto;">
      {''.join(bars)}
    </div>"""
    return HTMLResponse(chart_html)


@app.get("/analytics/top-products", response_class=HTMLResponse)
async def analytics_top_products(request: Request):
    token = _token(request)
    resp = await _api("get", "/dashboard/top-products?limit=10", token=token)
    products = resp["data"] or []
    if not products:
        return HTMLResponse("<div style='color:var(--text-muted);padding:12px;'>No data yet.</div>")
    rows = "".join(f"""
    <tr>
      <td>{i+1}</td>
      <td>{p.get('product_name','—')}</td>
      <td>{int(p.get('total_qty', 0))}</td>
      <td>₹{int(p.get('total_revenue', 0)):,}</td>
    </tr>""" for i, p in enumerate(products))
    return HTMLResponse(f"""
    <table class="data-table">
      <thead><tr><th>#</th><th>Product</th><th>Qty Sold</th><th>Revenue</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>""")


@app.get("/analytics/least-products", response_class=HTMLResponse)
async def analytics_least_products(request: Request):
    token = _token(request)
    resp = await _api("get", "/dashboard/top-products?limit=100", token=token)
    products = resp["data"] or []
    least = list(reversed(products))[:8]
    if not least:
        return HTMLResponse("<div style='color:var(--text-muted);padding:12px;'>No data yet.</div>")
    rows = "".join(f"""
    <tr>
      <td>{p.get('product_name','—')}</td>
      <td>{int(p.get('total_qty', 0))}</td>
      <td>₹{int(p.get('total_revenue', 0)):,}</td>
    </tr>""" for p in least)
    return HTMLResponse(f"""
    <table class="data-table">
      <thead><tr><th>Product</th><th>Qty Sold</th><th>Revenue</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>""")


@app.get("/analytics/avg-order", response_class=HTMLResponse)
async def analytics_avg_order(request: Request, range: str = Query("today")):
    from datetime import date
    token = _token(request)
    resp = await _api("get", f"/dashboard/summary?period={range}", token=token)
    summary = resp["data"] or {}
    txns = summary.get("total_transactions", 0)
    rev = summary.get("total_revenue", 0)
    avg = int(rev / txns) if txns else 0
    
    labels = {"today": "today", "week": "this week", "month": "this month", "year": "this year"}
    label_text = labels.get(range, "today")
    
    return HTMLResponse(f"""
    <div style="text-align:center; padding:20px;">
      <div class="kpi-value" style="font-size:2.5rem;">₹{avg:,}</div>
      <div class="kpi-label">per transaction {label_text}</div>
      <div style="margin-top:12px; font-size:0.78rem; color:var(--text-muted);">
        Based on {txns} transactions
      </div>
    </div>""")


@app.get("/analytics/peak-hours", response_class=HTMLResponse)
async def analytics_peak_hours(request: Request):
    # Placeholder — backend doesn't have a peak-hours endpoint yet
    hours = [(f"{h}:00", 0) for h in range(9, 22)]
    max_v = 1
    bars = []
    for label, val in hours:
        pct = max(4, int((val / max_v) * 100))
        bars.append(f"""
        <div style="display:flex;flex-direction:column;align-items:center;gap:2px;flex:1;">
          <div style="width:100%;background:var(--deep);border-radius:4px 4px 0 0;
                      height:{pct}%;min-height:4px;"></div>
          <div style="font-size:0.55rem;color:var(--text-muted);writing-mode:vertical-rl;
                      transform:rotate(180deg);">{label}</div>
        </div>""")
    return HTMLResponse(f"""
    <div style="display:flex;align-items:flex-end;gap:3px;height:120px;padding:8px 4px;">
      {''.join(bars)}
    </div>
    <div style="font-size:0.72rem;color:var(--text-muted);text-align:center;margin-top:4px;">
      Peak hours tracking coming soon
    </div>""")


# ════════════════════════════════════════════════════════════════════════════
#  SUBCATEGORY OPTIONS — /subcategories/options
# ════════════════════════════════════════════════════════════════════════════

@app.get("/subcategories/options", response_class=HTMLResponse)
async def subcategory_options(request: Request, category: str = Query("")):
    token = _token(request)
    if not category:
        return templates.TemplateResponse(request=request, name="partials/subcategory_options.html", context=_ctx(request, subcategories=[]))
    resp = await _api("get", f"/subcategories/?category={category}", token=token)
    subcategories = resp["data"] or []
    return templates.TemplateResponse(request=request, name="partials/subcategory_options.html", context=_ctx(request, subcategories=subcategories))

# ════════════════════════════════════════════════════════════════════════════
#  INVENTORY PARTIAL ROUTES — /inventory/*
# ════════════════════════════════════════════════════════════════════════════

@app.get("/inventory/products", response_class=HTMLResponse)
async def inv_products(request: Request, q: Optional[str] = None):
    token = _token(request)
    if q:
        resp = await _api("get", f"/products/search?q={q}", token=token)
    else:
        resp = await _api("get", "/products/", token=token)
    products = resp["data"] or []
    print(f"DEBUG: inv_products -> status: {resp['status']}, count: {len(products)}, error: {resp['error']}")
    rows = ""
    for p in products:
        unit = p.get("unit", "pcs")
        qty = p.get("stock_qty", 0)
        min_q = p.get("min_stock_alert", 0)
        qty_disp = int(qty)
        low = int(qty) <= int(min_q)
        status_badge = (
            '<span class="badge badge-danger">Out</span>' if qty <= 0
            else '<span class="badge badge-warning">Low</span>' if low
            else '<span class="badge badge-success">OK</span>'
        )
        img_url = f'data:image/jpeg;base64,{p.get("image_data")}' if p.get("image_data") else ""
        img_tag = f'<img src="{img_url}" style="width:40px;height:40px;object-fit:cover;border-radius:4px;">' if img_url else '<div style="width:40px;height:40px;background:rgba(255,255,255,0.05);border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:1.2rem;border:1px solid var(--border);">🛒</div>'
        
        rows += f"""
        <tr>
          <td>{p.get('id')}</td>
          <td>{img_tag}</td>
          <td><strong>{p.get('name')}</strong></td>
          <td>{p.get('barcode') or '—'}</td>
          <td>{p.get('category') or '—'}</td>
          <td>{p.get('unit_value', '')} {p.get('base_unit', '') or p.get('unit', '')}</td>
          <td>₹{int(p.get('price', 0))}</td>
          <td>{p.get('discount', 0)}%</td>
          <td class="{'low-stock' if low else ''}">{qty_disp} pcs</td>
          <td>{status_badge}</td>
          <td>
            <button class="btn btn-secondary btn-sm"
                    hx-get="/inventory/edit-form/{p['id']}"
                    hx-target="#inv-modal"
                    hx-swap="innerHTML"
                    onclick="document.getElementById('inv-modal').style.display='flex'">
              ✏️
            </button>
            <button class="btn btn-danger btn-sm"
                    hx-delete="/inventory/product/{p['id']}"
                    hx-target="#inv-content"
                    hx-swap="innerHTML"
                    hx-confirm="Delete '{p.get('name')}'?">
              🗑️
            </button>
          </td>
        </tr>"""
    
    search_bar = f"""
    <div style="margin-bottom:16px; display:flex; align-items:center; gap:12px; background:var(--surface); padding:12px; border:1px solid var(--border); border-radius:var(--radius-sm);">
      <div style="font-size:0.9rem; font-weight:700; color:var(--text);">🔍 Find Products:</div>
      <input type="search" name="q" class="form-control" style="width:300px; margin-bottom:0;"
             placeholder="Search by name, barcode or category..."
             value="{q or ''}"
             hx-get="/inventory/products"
             hx-trigger="keyup changed delay:350ms"
             hx-target="#inv-content"
             hx-indicator="#inv-search-spinner">
      <span class="htmx-indicator spinner" id="inv-search-spinner"></span>
    </div>
    """

    if resp["error"]:
        error_html = f'<div style="color:var(--accent);padding:12px;background:rgba(255,0,0,0.1);border-radius:8px;margin-bottom:16px;">❌ {resp["error"]}</div>'
    else:
        error_html = ""

    return HTMLResponse(f"""
    {error_html}
    {search_bar}
    <div style="overflow-x:auto;">
    <table class="data-table">
      <thead><tr>
        <th>ID</th><th>Image</th><th>Name</th><th>Barcode</th><th>Category</th>
        <th>Size</th><th>Price</th><th>Discount</th><th>Stock</th><th>Status</th><th>Actions</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
    <!-- inline modal for edit form -->
    <div id="inv-modal" class="modal-backdrop"
         style="display:none;"
         onclick="if(event.target===this){{this.style.display='none'}}">
    </div>""")


@app.get("/inventory/add-form", response_class=HTMLResponse)
async def inv_add_form(request: Request):
    token = _token(request)
    resp = await _api("get", "/categories/", token=token)
    categories = resp["data"] or []
    cat_options = "".join(f'<option value="{c["name"]}">{c["name"]}</option>' for c in categories)

    return HTMLResponse(f"""
    <div class="card">
      <div class="card-title" style="margin-bottom:16px;">➕ Add New Product</div>
      <form hx-post="/inventory/product"
            hx-target="#inv-content"
            hx-swap="innerHTML"
            hx-encoding="multipart/form-data">
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
          <div class="form-group">
            <label class="form-label">Product Name *</label>
            <input class="form-control" name="name" required placeholder="e.g. Basmati Rice">
          </div>
          <div class="form-group">
            <label class="form-label">Barcode</label>
            <input class="form-control" name="barcode" placeholder="Optional">
          </div>
          <div class="form-group">
            <label class="form-label">Category</label>
            <select class="form-control" name="category"
                    hx-get="/subcategories/options"
                    hx-target="#subcategory-select"
                    hx-trigger="change">
              <option value="">-- Select Category --</option>
              {cat_options}
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Subcategory</label>
            <select class="form-control" name="subcategory_id" id="subcategory-select">
              <option value="">-- Select Subcategory --</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Price (₹) *</label>
            <input class="form-control" name="price" type="number" min="0" step="1" required>
          </div>
          <div class="form-group">
            <label class="form-label">Tax Rate %</label>
            <input class="form-control" name="tax_rate" type="number" min="0" max="100" value="0" step="1">
          </div>
          <div class="form-group">
            <label class="form-label">Unit Value</label>
            <input class="form-control" name="unit_value" type="number" step="any" value="1" required>
          </div>
          <div class="form-group">
            <label class="form-label">Base Unit</label>
            <select class="form-control" name="base_unit">
              <option value="pcs">pcs</option>
              <option value="g">g</option>
              <option value="ml">ml</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Discount %</label>
            <input class="form-control" name="discount" type="number" min="0" max="100" value="0" step="1">
          </div>
          <div class="form-group">
            <label class="form-label">Opening Stock (pcs) *</label>
            <input class="form-control" name="stock_qty" type="number" min="0" step="1" value="0" required
                   onkeydown="if(event.key==='.' || event.key==='e' || event.key==='-'){{event.preventDefault();}}">
            <input type="hidden" name="stock_unit" value="pcs">
          </div>
          <div class="form-group">
            <label class="form-label">Min Stock Alert (pcs) *</label>
            <input class="form-control" name="min_stock_alert" type="number" min="0" step="1" value="5" required
                   onkeydown="if(event.key==='.' || event.key==='e' || event.key==='-'){{event.preventDefault();}}">
          </div>
          <div class="form-group">
            <label class="form-label">Product Image</label>
            <input class="form-control" type="file" name="image" accept="image/*">
          </div>
        </div>
        <div class="form-group" style="grid-column:1/-1;">
          <label class="form-label">Description</label>
          <textarea class="form-control" name="description" rows="2" placeholder="Optional"></textarea>
        </div>
        <div style="margin-top:16px;">
          <button type="submit" class="btn btn-primary">✅ Add Product</button>
        </div>
      </form>
    </div>""")


@app.post("/inventory/product", response_class=HTMLResponse)
async def inv_create_product(request: Request,
                              name: str = Form(...),
                              barcode: Optional[str] = Form(None),
                              category: Optional[str] = Form(None),
                              subcategory_id: Optional[int] = Form(None),
                              unit: str = Form("pcs"),
                              price: float = Form(...),
                              tax_rate: float = Form(0),
                               discount: float = Form(0),
                               base_unit: str = Form("pcs"),
                               unit_value: float = Form(1.0),
                               stock_unit: str = Form("pcs"),
                               stock_qty: int = Form(0),
                              min_stock_alert: int = Form(5),
                              description: Optional[str] = Form(None),
                              image: UploadFile = File(None)):
    token = _token(request)
    image_data = await _to_base64(image)
    payload = {
        "name": name, "barcode": barcode or None, "category": category,
        "subcategory_id": subcategory_id,
        "unit": base_unit, "price": price, "tax_rate": tax_rate, "discount": discount,
        "base_unit": base_unit, "unit_value": unit_value, "stock_unit": stock_unit,
        "stock_qty": stock_qty, "min_stock_alert": min_stock_alert,
        "description": description or None,
        "image_data": image_data,
    }
    resp = await _api("post", "/products/", token=token, json=payload)
    if resp["error"]:
        # Return the specific pydantic validation error message
        return HTMLResponse(f'<div style="color:var(--accent);padding:12px;background:rgba(255,0,0,0.1);border-radius:8px;">❌ {resp["error"]}</div>')
    if resp["data"]:
        return RedirectResponse(url="/inventory/products", status_code=303)
    return HTMLResponse("""<div style="color:var(--accent);padding:12px;">
        ❌ Failed to create product. Check all fields.</div>""")


@app.delete("/inventory/product/{product_id}", response_class=HTMLResponse)
async def inv_delete_product(request: Request, product_id: int):
    token = _token(request)
    await _api("delete", f"/products/{product_id}", token=token)
    # Re-render the product list segment (partial)
    return await inv_products(request)


@app.get("/inventory/edit-form/{product_id}", response_class=HTMLResponse)
async def inv_edit_form(request: Request, product_id: int):
    token = _token(request)
    resp = await _api("get", f"/products/{product_id}", token=token)
    p = resp["data"]
    if not p:
        return HTMLResponse('<div style="color:var(--accent);padding:12px;">❌ Product not found.</div>')
    
    # Generate category options
    cat_resp = await _api("get", "/categories/", token=token)
    categories = cat_resp["data"] or []
    cat_options = '<option value="">-- Select Category --</option>'
    for cat in categories:
        selected = 'selected' if p.get('category') == cat['name'] else ''
        cat_options += f'<option value="{cat["name"]}" {selected}>{cat["name"]}</option>'

    # Generate subcategory options if category exists
    sub_options = '<option value="">-- Select Subcategory --</option>'
    if p.get('category'):
        sub_resp = await _api("get", f"/subcategories/?category={p.get('category')}", token=token)
        subs = sub_resp["data"] or []
        for s in subs:
            selected = 'selected' if p.get('subcategory_id') == s['id'] else ''
            sub_options += f'<option value="{s["id"]}" {selected}>{s["name"]}</option>'

    return HTMLResponse(f"""
    <div class="modal" style="margin:20px auto;">
      <div class="card-title" style="margin-bottom:16px;">✏️ Edit Product: {p.get('name')}</div>
      <form hx-post="/inventory/product/{product_id}"
            hx-target="#inv-content"
            hx-swap="innerHTML"
            hx-encoding="multipart/form-data">
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
          <div class="form-group">
            <label class="form-label">Product Name *</label>
            <input class="form-control" name="name" value="{p.get('name','')}" required>
          </div>
          <div class="form-group">
            <label class="form-label">Barcode</label>
            <input class="form-control" name="barcode" value="{p.get('barcode','') or ''}">
          </div>
          <div class="form-group">
            <label class="form-label">Category</label>
            <select class="form-control" name="category"
                    hx-get="/subcategories/options"
                    hx-target="#subcategory-select-edit"
                    hx-trigger="change">
              {cat_options}
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Subcategory</label>
            <select class="form-control" name="subcategory_id" id="subcategory-select-edit">
              {sub_options}
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Price (₹) *</label>
            <input class="form-control" name="price" type="number" min="0" step="1" value="{int(p.get('price',0))}" required>
          </div>
          <div class="form-group">
            <label class="form-label">Tax Rate %</label>
            <input class="form-control" name="tax_rate" type="number" min="0" max="100" value="{int(p.get('tax_rate',0))}" step="1">
          </div>
          <div class="form-group">
            <label class="form-label">Unit Value (e.g. 1000 for 1kg=1000g)</label>
            <input class="form-control" name="unit_value" type="number" step="any" value="{p.get('unit_value', 1.0)}" required>
          </div>
          <div class="form-group">
            <label class="form-label">Base Unit (for inventory tracking)</label>
            <select class="form-control" name="base_unit">
              <option value="pcs" {"selected" if p.get("base_unit")=="pcs" else ""}>pcs</option>
              <option value="g" {"selected" if p.get("base_unit")=="g" else ""}>g</option>
              <option value="ml" {"selected" if p.get("base_unit")=="ml" else ""}>ml</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Discount %</label>
            <input class="form-control" name="discount" type="number" min="0" max="100" value="{int(p.get('discount',0))}" step="1">
          </div>
          <div class="form-group">
            <label class="form-label">Stock Unit (e.g. pcs, packets)</label>
            <input class="form-control" name="stock_unit" value="{p.get('stock_unit','pcs')}" required>
          </div>
          <div class="form-group">
            <label class="form-label">Min Stock Alert (pcs) *</label>
            <input class="form-control" name="min_stock_alert" type="number" min="0" step="1" value="{int(p.get('min_stock_alert',5))}" required
                   onkeydown="if(event.key==='.' || event.key==='e' || event.key==='-'){{event.preventDefault();}}">
          </div>
          <div class="form-group">
            <label class="form-label">Update Image</label>
            <input class="form-control" type="file" name="image" accept="image/*">
          </div>
        </div>
        <div class="form-group" style="grid-column:1/-1;">
          <label class="form-label">Description</label>
          <textarea class="form-control" name="description" rows="2">{p.get('description','') or ''}</textarea>
        </div>
        <div style="margin-top:16px; display:flex; gap:10px;">
          <button type="submit" class="btn btn-primary">💾 Save Changes</button>
          <button type="button" class="btn btn-secondary" onclick="document.getElementById('inv-modal').style.display='none'">Cancel</button>
        </div>
      </form>
    </div>""")


@app.post("/inventory/product/{product_id}", response_class=HTMLResponse)
async def inv_update_product(request: Request,
                              product_id: int,
                              name: str = Form(...),
                              barcode: Optional[str] = Form(None),
                              category: Optional[str] = Form(None),
                              subcategory_id: Optional[int] = Form(None),
                              unit: str = Form("pcs"),
                              price: float = Form(...),
                              tax_rate: float = Form(0),
                              discount: float = Form(0),
                              base_unit: Optional[str] = Form(None),
                              unit_value: Optional[float] = Form(None),
                              stock_unit: Optional[str] = Form("pcs"),
                              min_stock_alert: int = Form(5),
                              description: Optional[str] = Form(None),
                              image: UploadFile = File(None)):
    token = _token(request)
    image_data = await _to_base64(image)
    payload = {
        "name": name, "barcode": barcode or None, "category": category,
        "subcategory_id": subcategory_id,
        "unit": base_unit if base_unit else unit, 
        "price": price, "tax_rate": tax_rate, "discount": discount,
        "base_unit": base_unit, "unit_value": unit_value, "stock_unit": stock_unit,
        "min_stock_alert": min_stock_alert,
        "description": description or None,
    }
    if image_data:
        payload["image_data"] = image_data
        
    resp = await _api("put", f"/products/{product_id}", token=token, json=payload)
    if resp["error"]:
        return HTMLResponse(f'<div style="color:var(--accent);padding:12px;background:rgba(255,0,0,0.1);border-radius:8px;">❌ {resp["error"]}</div>')
    if resp["data"]:
        return RedirectResponse(url="/inventory/products", status_code=303)
    return HTMLResponse('<div style="color:var(--accent);padding:12px;">❌ Failed to update product.</div>')


@app.get("/inventory/restock-form", response_class=HTMLResponse)
async def inv_restock_form(request: Request):
    token = _token(request)
    resp = await _api("get", "/products/", token=token)
    products = resp["data"] or []
    options = "".join(f'<option value="{p["id"]}">{p["name"]} (Stock: {int(p["stock_qty"])})</option>'
                      for p in products)
    return HTMLResponse(f"""
    <div class="card" style="max-width: 600px; margin: 0 auto;">
      <div class="card-title" style="margin-bottom:20px; display:flex; align-items:center; gap:10px;">
        <span style="font-size:1.4rem;">🔄</span> Restock Product
      </div>
      
      <!-- Selected Product Info Area -->
      <div id="selected-product-info" style="display:none; margin-bottom:24px; padding:16px; background:rgba(14, 165, 233, 0.08); border:2px solid var(--accent); border-radius:var(--radius); animation: slideDown 0.3s ease-out;">
         <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:12px;">
               <div style="width:40px; height:40px; background:var(--accent); border-radius:8px; display:flex; align-items:center; justify-content:center; color:white; font-size:1.2rem;">📦</div>
               <div>
                  <div id="selected-product-name" style="font-size:1.1rem; font-weight:800; color:var(--text);">No product selected</div>
                  <div id="selected-product-stock" style="font-size:0.8rem; color:var(--text-muted); margin-top:2px;">Current Stock: --</div>
               </div>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" onclick="clearRestockSelection()" style="border-radius:20px; padding:4px 12px; font-size:0.75rem;">Change Product</button>
         </div>
      </div>

      <form hx-post="/inventory/restock" hx-target="#inv-content" hx-swap="innerHTML" id="restock-form">
        <input type="hidden" name="product_id" id="hidden-product-id" required>
        
        <!-- Step 1: Search and Select -->
        <div id="product-search-container" class="form-group" style="margin-bottom:24px;">
          <label class="form-label" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span>1. Search Product to Restock</span>
          </label>
          <div style="position:relative; border:1px solid var(--border); border-radius:var(--radius-sm); overflow:hidden; background:var(--surface2);">
            <div style="display:flex; align-items:center; padding:0 12px; border-bottom:1px solid var(--border);">
               <span style="opacity:0.5;">🔍</span>
               <input type="text" class="form-control" id="restock-search" 
                      placeholder="Type name or barcode..." 
                      onkeyup="filterRestockList()"
                      autocomplete="off"
                      style="border:none; background:transparent; padding:12px 8px; margin-bottom:0; width:100%; box-shadow:none;">
            </div>
            <select class="form-control" id="product-select" size="6" 
                    onchange="selectRestockProduct()"
                    style="border:none; background:transparent; height:auto; padding:0; outline:none;">
              {options}
            </select>
          </div>
          <p style="font-size:0.7rem; color:var(--text-muted); margin-top:8px;">Click on a product from the list above to proceed.</p>
        </div>

        <!-- Step 2: Restock Details -->
        <div id="restock-details" style="opacity:0.3; pointer-events:none; transition:all 0.4s ease;">
            <div style="background:rgba(255,255,255,0.02); padding:16px; border-radius:var(--radius); border:1px dashed var(--border);">
                <div class="form-group">
                  <label class="form-label">2. Quantity to Add (pcs) *</label>
                  <input class="form-control" id="restock-qty" name="qty" type="number" min="1" step="1" value="1" required 
                         style="font-size:1.1rem; font-weight:700; padding:12px;"
                         onkeydown="if(event.key==='.' || event.key==='e' || event.key==='-'){{event.preventDefault();}}">
                  <small style="color: var(--text-muted); font-size:0.7rem; margin-top:4px; display:block;">Enter the number of units received from supplier.</small>
                </div>
                <div class="form-group" style="margin-bottom:20px;">
                  <label class="form-label">3. Reason / Remarks</label>
                  <input class="form-control" name="reason" value="Restock from supplier" style="padding:10px;">
                </div>
                <button type="submit" class="btn btn-primary btn-full btn-xl">📥 Confirm & Add Stock</button>
            </div>
        </div>

        <script>
        function filterRestockList() {{
          const input = document.getElementById('restock-search');
          const filter = input.value.toLowerCase();
          const select = document.getElementById('product-select');
          const options = select.getElementsByTagName('option');
          for (let i = 0; i < options.length; i++) {{
            const txt = options[i].textContent || options[i].innerText;
            const match = txt.toLowerCase().indexOf(filter) > -1;
            options[i].style.display = match ? "" : "none";
          }}
        }}

        function selectRestockProduct() {{
          const select = document.getElementById('product-select');
          const selectedOption = select.options[select.selectedIndex];
          if(!selectedOption) return;

          const pId = selectedOption.value;
          const pNameStock = selectedOption.textContent;
          
          // Update hidden input
          document.getElementById('hidden-product-id').value = pId;
          
          // Update display
          document.getElementById('selected-product-name').textContent = pNameStock.split('(')[0].trim();
          document.getElementById('selected-product-stock').textContent = 'Currently in inventory: ' + pNameStock.split('(')[1].replace(')', '').trim();
          
          // Visual transitions
          document.getElementById('product-search-container').style.display = 'none';
          document.getElementById('selected-product-info').style.display = 'block';
          
          // Enable restock details
          const details = document.getElementById('restock-details');
          details.style.opacity = '1';
          details.style.pointerEvents = 'auto';
          
          // Focus quantity field
          setTimeout(() => document.getElementById('restock-qty').focus(), 300);
        }}

        function clearRestockSelection() {{
           document.getElementById('hidden-product-id').value = '';
           document.getElementById('product-search-container').style.display = 'block';
           document.getElementById('selected-product-info').style.display = 'none';
           
           const details = document.getElementById('restock-details');
           details.style.opacity = '0.3';
           details.style.pointerEvents = 'none';
           
           document.getElementById('restock-search').value = '';
           filterRestockList(); 
           setTimeout(() => document.getElementById('restock-search').focus(), 100);
        }}
        </script>
        <style>
        @keyframes slideDown {{
           from {{ opacity:0; transform:translateY(-15px); }}
           to {{ opacity:1; transform:translateY(0); }}
        }}
        #product-select option {{
           padding: 10px 12px;
           border-bottom: 1px solid var(--border);
           cursor: pointer;
           font-weight: 500;
        }}
        #product-select option:hover {{
           background: rgba(14, 165, 233, 0.1);
        }}
        #product-select::-webkit-scrollbar {{
           width: 6px;
        }}
        #product-select::-webkit-scrollbar-thumb {{
           background: rgba(255,255,255,0.1);
           border-radius: 10px;
        }}
        </style>
      </form>
    </div>""")


@app.post("/inventory/restock", response_class=HTMLResponse)
async def inv_restock(request: Request,
                      product_id: int = Form(...),
                      qty: int = Form(...),
                      reason: str = Form("Restock")):
    token = _token(request)
    res = await _api("post", "/inventory/restock", token=token,
               json={"product_id": product_id, "qty": qty, "reason": reason})
    if res["error"]:
        return HTMLResponse(f'<div style="color:var(--accent);padding:12px;background:rgba(255,0,0,0.1);border-radius:8px;">❌ {res["error"]}</div>')
    return RedirectResponse(url="/inventory/products", status_code=303)


@app.get("/inventory/stock-alerts", response_class=HTMLResponse)
async def inv_stock_alerts(request: Request):
    token = _token(request)
    resp = await _api("get", "/products/low-stock", token=token)
    low = resp["data"] or []
    return templates.TemplateResponse(request=request, name="partials/stock_alerts.html", context=_ctx(request, low_stock=low)
    )


# ════════════════════════════════════════════════════════════════════════════
#  CUSTOMERS PARTIAL ROUTES — /customers/*
# ════════════════════════════════════════════════════════════════════════════

@app.get("/customers/list", response_class=HTMLResponse)
async def customers_list(request: Request, q: Optional[str] = None):
    token = _token(request)
    # The backend's customer endpoint may not exist; handle gracefully
    try:
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=8.0) as client:
            params = {"q": q} if q else {}
            resp = await client.get("/customers/",
                                    params=params,
                                    headers={"Authorization": f"Bearer {token}"} if token else {})
            customers = resp.json() if resp.status_code == 200 else []
    except Exception:
        customers = []
    
    if not customers:
        return HTMLResponse("""<tr><td colspan="7" style="text-align:center;
            color:var(--text-muted);padding:32px;">No customers found.</td></tr>""")
    
    rows = ""
    for i, c in enumerate(customers):
        cust_id = c.get('id', 0)
        rows += f"""
        <tr hx-get="/customers/insights/{cust_id}"
            hx-target="#customer-insights-content"
            hx-swap="innerHTML"
            style="cursor:pointer;">
          <td>{i+1}</td>
          <td><strong>{c.get('name','—')}</strong></td>
          <td>{c.get('phone','—')}</td>
          <td>{c.get('total_orders', 0)}</td>
          <td>₹{int(c.get('total_spending', 0)):,}</td>
          <td>{c.get('last_purchase','—')}</td>
          <td><button class="btn btn-secondary btn-sm"
                      hx-get="/customers/insights/{cust_id}"
                      hx-target="#customer-insights-content">
            View
          </button></td>
        </tr>"""
    return HTMLResponse(rows)


@app.get("/customers/search", response_class=HTMLResponse)
async def customers_search(request: Request, q: str = ""):
    return await customers_list(request, q=q)


@app.get("/customers/insights/{customer_id}", response_class=HTMLResponse)
async def customer_insights(request: Request, customer_id: int):
    token = _token(request)
    resp = await _api("get", f"/customers/{customer_id}/insights", token=token)
    data = resp["data"]
    
    if resp["error"] or not data:
        err = resp["error"] or "Customer not found"
        logger.error(f"Customer insights error for {customer_id}: {err}")
        return HTMLResponse(f'<div style="color:var(--accent); padding:20px; text-align:center;">❌ {err}</div>')
    
    logger.info(f"Loaded insights for customer {customer_id}")

    # Build top products list if they exist
    top_products_html = ""
    if data.get("top_products"):
        items_html = "".join([f"""
            <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05); font-size:0.8rem;">
                <span style="color:var(--text); font-weight:500;">{p['name']}</span>
                <span style="color:var(--accent); font-weight:700;">{int(p['qty'])} sold</span>
            </div>
        """ for p in data["top_products"]])
        
        top_products_html = f"""
        <div style="margin-top:20px; text-align:left; width:100%;">
            <div style="font-size:0.75rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:10px; border-bottom:1px solid var(--border); padding-bottom:4px;">
                Highest Purchased Products
            </div>
            {items_html}
        </div>
        """
    else:
        top_products_html = '<div style="margin-top:20px; color:var(--text-muted); font-size:0.75rem;">No purchase history found</div>'

    return HTMLResponse(f"""
    <div style="text-align:center; padding:12px 0;">
      <div style="font-size:2rem; margin-bottom:8px;">👤</div>
      <div style="font-size:1rem; font-weight:700; color:#fff; margin-bottom:4px;">
        {data.get('name', 'Unknown')}
      </div>
      <div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:16px;">
        {data.get('phone', 'No Phone')}
      </div>
    </div>
    
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px;">
        <div class="kpi-card" style="padding:12px;">
          <div class="kpi-label" style="font-size:0.65rem;">Total Orders</div>
          <div class="kpi-value" style="font-size:1.4rem;">{data.get('total_orders', 0)}</div>
        </div>
        <div class="kpi-card" style="padding:12px;">
          <div class="kpi-label" style="font-size:0.65rem;">Total Spending</div>
          <div class="kpi-value" style="font-size:1.4rem;">₹{int(data.get('total_spending', 0)):,}</div>
        </div>
    </div>
    
    <div class="kpi-card" style="padding:12px; margin-bottom:20px;">
      <div class="kpi-label" style="font-size:0.65rem;">Last Purchase</div>
      <div class="kpi-value" style="font-size:1.1rem;">{data.get('last_purchase', 'Never')}</div>
    </div>
    
    {top_products_html}
    """)


# ════════════════════════════════════════════════════════════════════════════
#  SETTINGS PARTIAL ROUTES — /settings/*
# ════════════════════════════════════════════════════════════════════════════

@app.get("/settings/health", response_class=HTMLResponse)
async def settings_health(request: Request):
    try:
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=5.0) as client:
            resp = await client.get("/health")
            if resp.status_code == 200:
                return HTMLResponse(
                    '<span style="color:#2ecc71;">✅ Backend is healthy</span>')
    except Exception:
        pass
    return HTMLResponse('<span style="color:var(--accent);">❌ Backend unreachable</span>')


@app.post("/settings/test-print", response_class=HTMLResponse)
async def settings_test_print(request: Request):
    token = _token(request)
    result = await _api("post", "/hardware/print",
                        token=token,
                        json={"sale_id": 0, "cashier": "Test", "created_at": "Test",
                              "payment_mode": "test", "items": [],
                              "subtotal": 0, "discount": 0, "tax": 0, "total": 0})
    if result is not None:
        return HTMLResponse('<span style="color:#2ecc71;">✅ Print sent successfully</span>')
    return HTMLResponse('<span style="color:var(--accent);">❌ Printer not responding</span>')
