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
BACKEND_URL: str = os.getenv("BACKEND_URL", os.getenv("API_BASE", "http://localhost:8000"))
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
    """Recalculate subtotals on every item."""
    for item in cart["items"]:
        item["subtotal"] = item["unit_price"] * item["qty"] * (1 - item["discount"] / 100)

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
    return templates.TemplateResponse("login.html", _ctx(request))


@app.get("/app/pos", response_class=HTMLResponse)
async def pos_page(request: Request):
    return templates.TemplateResponse("pos.html", _ctx(request))


@app.get("/app/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return templates.TemplateResponse("analytics.html", _ctx(request))


@app.get("/app/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request):
    return templates.TemplateResponse("inventory.html", _ctx(request))


@app.get("/app/customers", response_class=HTMLResponse)
async def customers_page(request: Request):
    return templates.TemplateResponse("customers.html", _ctx(request))


@app.get("/app/help", response_class=HTMLResponse)
async def help_page(request: Request):
    return templates.TemplateResponse("help.html", _ctx(request))


@app.get("/app/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", _ctx(request))


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
    return templates.TemplateResponse(
        "partials/product_list.html",
        _ctx(request, products=products)
    )


@app.get("/pos/search", response_class=HTMLResponse)
async def pos_search(request: Request, q: str = ""):
    token = _token(request)
    if not q or len(q) < 2:
        resp = await _api("get", "/products/", token=token)
    else:
        resp = await _api("get", f"/products/search?q={q}", token=token)
    products = resp["data"] or []
    return templates.TemplateResponse(
        "partials/product_list.html",
        _ctx(request, products=products)
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
    return templates.TemplateResponse(
        "partials/recent_bills.html",
        _ctx(request, bills=bills)
    )


# ── Cart endpoints ────────────────────────────────────────────────────────
@app.get("/pos/cart", response_class=HTMLResponse)
async def get_cart(request: Request):
    sid = _session_id(request)
    cart = _get_cart(sid)
    _recalc(cart)
    return templates.TemplateResponse(
        "partials/cart.html",
        _ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
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

    unit = product.get("unit", "pcs")
    is_float = unit.lower() in ["kg", "litre", "ltr"]

    # Check if already in cart
    for item in cart["items"]:
        if item["product_id"] == product_id:
            item["qty"] += 0.5 if is_float else 1
            _recalc(cart)
            return templates.TemplateResponse(
                "partials/cart.html",
                _ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
            )

    cart["items"].append({
        "product_id": product_id,
        "name": product["name"],
        "unit": unit,
        "unit_price": product["price"],
        "qty": 0.5 if is_float else 1,
        "discount": 0.0,
        "image_data": product.get("image_data"),
        "subtotal": product["price"],
    })
    _recalc(cart)
    return templates.TemplateResponse(
        "partials/cart.html",
        _ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
    )


@app.patch("/pos/cart/qty/{product_id}", response_class=HTMLResponse)
async def change_qty(request: Request, product_id: int,
                     delta: float = 1, float: bool = False):
    sid = _session_id(request)
    cart = _get_cart(sid)
    for item in cart["items"]:
        if item["product_id"] == product_id:
            step = 0.5 if float else 1
            item["qty"] = max(0, item["qty"] + (step if delta > 0 else -step))
            if item["qty"] == 0:
                cart["items"].remove(item)
            break
    _recalc(cart)
    return templates.TemplateResponse(
        "partials/cart.html",
        _ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
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
    return templates.TemplateResponse(
        "partials/cart.html",
        _ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
    )


@app.patch("/pos/cart/cart-discount", response_class=HTMLResponse)
async def set_cart_discount(request: Request,
                             discount: float = Form(0)):
    sid = _session_id(request)
    cart = _get_cart(sid)
    cart["cart_discount"] = max(0, min(100, discount))
    _recalc(cart)
    return templates.TemplateResponse(
        "partials/cart.html",
        _ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
    )


@app.delete("/pos/cart/item/{product_id}", response_class=HTMLResponse)
async def remove_cart_item(request: Request,
                            product_id: int):
    sid = _session_id(request)
    cart = _get_cart(sid)
    cart["items"] = [i for i in cart["items"] if i["product_id"] != product_id]
    _recalc(cart)
    return templates.TemplateResponse(
        "partials/cart.html",
        _ctx(request, cart=cart["items"], cart_discount=cart["cart_discount"])
    )


@app.delete("/pos/cart", response_class=HTMLResponse)
async def clear_cart(request: Request):
    sid = _session_id(request)
    CARTS.pop(sid, None)
    return templates.TemplateResponse(
        "partials/cart.html",
        _ctx(request, cart=[], cart_discount=0.0)
    )


# ── Payment modal flow ────────────────────────────────────────────────────
@app.get("/pos/modal/customer", response_class=HTMLResponse)
async def modal_customer(request: Request):
    return templates.TemplateResponse("partials/bill_modal.html", _ctx(request))


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
    disc = subtotal * (cart.get("cart_discount", 0) / 100)
    grand_total = subtotal - disc
    return templates.TemplateResponse(
        "partials/payment.html",
        _ctx(request, cust_name=cust_name, cust_phone=cust_phone, grand_total=grand_total)
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
    return templates.TemplateResponse(
        "partials/receipt.html",
        _ctx(request,
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
    resp = await _api("get", "/dashboard/monthly-revenue", token=token)
    monthly = resp["data"] or []
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    
    if not monthly:
        return HTMLResponse("<div style='color:var(--text-muted);padding:20px;text-align:center;'>No sales data available yet.</div>")

    max_rev = max((m.get("revenue", 0) for m in monthly), default=1) or 1
    bars = []
    for m in monthly[::-1][:12 if range=="year" else (4 if range=="month" else 7)]:
        mo = m.get("month", 1)
        rev = m.get("revenue", 0)
        pct = max(4, int((rev / max_rev) * 100))
        label = months[int(mo) - 1]
        bars.append(f"""
        <div style="display:flex;flex-direction:column;align-items:center;gap:4px;flex:1;min-width:32px;">
          <div style="font-size:0.72rem;color:var(--text-muted);">₹{int(rev//1000)}k</div>
          <div style="width:100%;background:var(--accent);border-radius:4px 4px 0 0;height:{pct}%;min-height:4px;
                      transition:height 0.4s cubic-bezier(0.19,1,0.22,1);"></div>
          <div style="font-size:0.7rem;color:var(--text-muted);">{label}</div>
        </div>""")
    
    chart_html = f"""
    <div style="display:flex;align-items:flex-end;gap:6px;height:220px;padding:12px 8px;">
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
#  INVENTORY PARTIAL ROUTES — /inventory/*
# ════════════════════════════════════════════════════════════════════════════

@app.get("/inventory/products", response_class=HTMLResponse)
async def inv_products(request: Request):
    token = _token(request)
    resp = await _api("get", "/products/", token=token)
    products = resp["data"] or []
    rows = ""
    for p in products:
        unit = p.get("unit", "pcs")
        is_float = unit.lower() in ["kg", "litre", "ltr"]
        qty = p.get("stock_qty", 0)
        min_q = p.get("min_stock_alert", 0)
        qty_disp = round(float(qty), 2) if is_float else int(qty)
        low = qty <= min_q
        status_badge = (
            '<span class="badge badge-danger">Out</span>' if qty <= 0
            else '<span class="badge badge-warning">Low</span>' if low
            else '<span class="badge badge-success">OK</span>'
        )
        rows += f"""
        <tr>
          <td>{p.get('id')}</td>
          <td><strong>{p.get('name')}</strong></td>
          <td>{p.get('barcode') or '—'}</td>
          <td>{p.get('category') or '—'}</td>
          <td>{unit}</td>
          <td>₹{int(p.get('price', 0))}</td>
          <td class="{'low-stock' if low else ''}">{qty_disp}</td>
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
    return HTMLResponse(f"""
    <div style="overflow-x:auto;">
    <table class="data-table">
      <thead><tr>
        <th>ID</th><th>Name</th><th>Barcode</th><th>Category</th>
        <th>Unit</th><th>Price</th><th>Stock</th><th>Status</th><th>Actions</th>
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
            <input class="form-control" name="category" placeholder="e.g. Grains">
          </div>
          <div class="form-group">
            <label class="form-label">Unit</label>
            <select class="form-control" name="unit">
              <option value="pcs">pcs</option>
              <option value="kg">kg</option>
              <option value="litre">litre</option>
              <option value="pack">pack</option>
              <option value="dozen">dozen</option>
              <option value="box">box</option>
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
            <label class="form-label">Opening Stock</label>
            <input class="form-control" name="stock_qty" type="number" min="0" step="0.5" value="0">
          </div>
          <div class="form-group">
            <label class="form-label">Min Stock Alert</label>
            <input class="form-control" name="min_stock_alert" type="number" min="0" step="0.5" value="5">
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
                              unit: str = Form("pcs"),
                              price: float = Form(...),
                              tax_rate: float = Form(0),
                              stock_qty: float = Form(0),
                              min_stock_alert: float = Form(5),
                              description: Optional[str] = Form(None),
                              image: UploadFile = File(None)):
    token = _token(request)
    image_data = await _to_base64(image)
    payload = {
        "name": name, "barcode": barcode or None, "category": category,
        "unit": unit, "price": price, "tax_rate": tax_rate,
        "stock_qty": stock_qty, "min_stock_alert": min_stock_alert,
        "description": description or None,
        "image_data": image_data,
    }
    resp = await _api("post", "/products/", token=token, json=payload)
    if resp["data"]:
        return RedirectResponse(url="/inventory/products", status_code=303)
    return HTMLResponse("""<div style="color:var(--accent);padding:12px;">
        ❌ Failed to create product. Check all fields.</div>""")


@app.delete("/inventory/product/{product_id}", response_class=HTMLResponse)
async def inv_delete_product(request: Request, product_id: int):
    token = _token(request)
    await _api("delete", f"/products/{product_id}", token=token)
    # Re-render the product list
    return RedirectResponse(url="/inventory/products", status_code=303)


@app.get("/inventory/edit-form/{product_id}", response_class=HTMLResponse)
async def inv_edit_form(request: Request, product_id: int):
    token = _token(request)
    resp = await _api("get", f"/products/{product_id}", token=token)
    p = resp["data"]
    if not p:
        return HTMLResponse('<div style="color:var(--accent);padding:12px;">❌ Product not found.</div>')
    
    # Pre-select unit
    units = ["pcs", "kg", "litre", "pack", "dozen", "box"]
    unit_options = "".join(f'<option value="{u}" {"selected" if p.get("unit")==u else ""}>{u}</option>' for u in units)

    return HTMLResponse(f"""
    <div class="card" style="max-width:600px; margin:20px auto;">
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
            <input class="form-control" name="category" value="{p.get('category','') or ''}">
          </div>
          <div class="form-group">
            <label class="form-label">Unit</label>
            <select class="form-control" name="unit">
              {unit_options}
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
            <label class="form-label">Min Stock Alert</label>
            <input class="form-control" name="min_stock_alert" type="number" min="0" step="0.5" value="{p.get('min_stock_alert',5)}">
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
                              unit: str = Form("pcs"),
                              price: float = Form(...),
                              tax_rate: float = Form(0),
                              min_stock_alert: float = Form(5),
                              description: Optional[str] = Form(None),
                              image: UploadFile = File(None)):
    token = _token(request)
    image_data = await _to_base64(image)
    payload = {
        "name": name, "barcode": barcode or None, "category": category,
        "unit": unit, "price": price, "tax_rate": tax_rate,
        "min_stock_alert": min_stock_alert,
        "description": description or None,
    }
    if image_data:
        payload["image_data"] = image_data
        
    resp = await _api("put", f"/products/{product_id}", token=token, json=payload)
    if resp["data"]:
        return RedirectResponse(url="/inventory/products", status_code=303)
    return HTMLResponse('<div style="color:var(--accent);padding:12px;">❌ Failed to update product.</div>')


@app.get("/inventory/restock-form", response_class=HTMLResponse)
async def inv_restock_form(request: Request):
    token = _token(request)
    resp = await _api("get", "/products/", token=token)
    products = resp["data"] or []
    options = "".join(f'<option value="{p["id"]}">{p["name"]} (Stock: {int(p["stock_qty"])} {p["unit"]})</option>'
                      for p in products)
    return HTMLResponse(f"""
    <div class="card">
      <div class="card-title" style="margin-bottom:16px;">🔄 Restock Product</div>
      <form hx-post="/inventory/restock"
            hx-target="#inv-content"
            hx-swap="innerHTML">
        <div class="form-group">
          <label class="form-label">Select Product</label>
          <select class="form-control" name="product_id" required>
            {options}
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Quantity to Add</label>
          <input class="form-control" name="qty" type="number" min="0.1" step="0.5" value="1" required>
        </div>
        <div class="form-group">
          <label class="form-label">Reason</label>
          <input class="form-control" name="reason" value="Restock from supplier">
        </div>
        <button type="submit" class="btn btn-primary">📥 Restock</button>
      </form>
    </div>""")


@app.post("/inventory/restock", response_class=HTMLResponse)
async def inv_restock(request: Request,
                      product_id: int = Form(...),
                      qty: float = Form(...),
                      reason: str = Form("Restock")):
    token = _token(request)
    await _api("post", "/inventory/restock", token=token,
               json={"product_id": product_id, "qty": qty, "reason": reason})
    return RedirectResponse(url="/inventory/products", status_code=303)


@app.get("/inventory/stock-alerts", response_class=HTMLResponse)
async def inv_stock_alerts(request: Request):
    token = _token(request)
    resp = await _api("get", "/products/low-stock", token=token)
    low = resp["data"] or []
    return templates.TemplateResponse(
        "partials/stock_alerts.html",
        _ctx(request, low_stock=low)
    )


# ════════════════════════════════════════════════════════════════════════════
#  CUSTOMERS PARTIAL ROUTES — /customers/*
# ════════════════════════════════════════════════════════════════════════════

@app.get("/customers/list", response_class=HTMLResponse)
async def customers_list(request: Request):
    token = _token(request)
    # The backend's customer endpoint may not exist; handle gracefully
    try:
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=8.0) as client:
            resp = await client.get("/customers/",
                                    headers={"Authorization": f"Bearer {token}"} if token else {})
            customers = resp.json() if resp.status_code == 200 else []
    except Exception:
        customers = []
    
    if not customers:
        return HTMLResponse("""<tr><td colspan="7" style="text-align:center;
            color:var(--text-muted);padding:32px;">No customers found.</td></tr>""")
    
    rows = ""
    for i, c in enumerate(customers):
        rows += f"""
        <tr onclick="loadCustomerInsights({c.get('id', 0)})" style="cursor:pointer;">
          <td>{i+1}</td>
          <td><strong>{c.get('name','—')}</strong></td>
          <td>{c.get('phone','—')}</td>
          <td>{c.get('total_orders', 0)}</td>
          <td>₹{int(c.get('total_spending', 0)):,}</td>
          <td>{c.get('last_purchase','—')}</td>
          <td><button class="btn btn-secondary btn-sm"
                      onclick="loadCustomerInsights({c.get('id',0)});event.stopPropagation()">
            View
          </button></td>
        </tr>"""
    return HTMLResponse(rows)


@app.get("/customers/search", response_class=HTMLResponse)
async def customers_search(request: Request, q: str = ""):
    return await customers_list(request)


@app.get("/customers/insights/{customer_id}", response_class=HTMLResponse)
async def customer_insights(request: Request, customer_id: int):
    return HTMLResponse(f"""
    <div style="text-align:center; padding:12px 0;">
      <div style="font-size:2rem; margin-bottom:8px;">👤</div>
      <div style="font-size:0.85rem; font-weight:600; color:#fff; margin-bottom:16px;">
        Customer #{customer_id}
      </div>
    </div>
    <div class="kpi-card" style="margin-bottom:8px;">
      <div class="kpi-label">Total Orders</div>
      <div class="kpi-value" style="font-size:1.6rem;">—</div>
    </div>
    <div class="kpi-card" style="margin-bottom:8px;">
      <div class="kpi-label">Total Spent</div>
      <div class="kpi-value" style="font-size:1.6rem;">—</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Last Purchase</div>
      <div class="kpi-value" style="font-size:1.2rem;">—</div>
    </div>""")


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
