"""
frontend/pos.py — POS billing interface.

Features:
  - Barcode scan / product search
  - Cart management (add, remove, qty, discount)
  - Weight reading from digital scale
  - Payment: Cash, UPI, Card (Pine Labs), Credit
  - POST /sales → triggers receipt print
"""
import streamlit as st
import requests
import os
from datetime import datetime

from config import API_BASE


def _headers():
    return {"Authorization": f"Bearer {st.session_state.get('token', '')}"}


def _api(method, path, **kwargs):
    try:
        resp = getattr(requests, method)(f"{API_BASE}{path}", headers=_headers(), timeout=8, **kwargs)
        return resp
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot reach backend API.")
        return None


def show_pos():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .pos-header { font-size: 1.5rem; font-weight: 700; color: #fff;
                   background: linear-gradient(90deg,#e94560,#0f3460); padding:14px 20px;
                   border-radius:12px; margin-bottom:16px; }
    .cart-total { font-size: 1.8rem; font-weight: 700; color: #e94560; }
    .product-card { background: rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1);
                     border-radius:12px; padding:12px; margin:6px 0; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="pos-header">🛒 POS — Billing Counter</div>', unsafe_allow_html=True)

    # Init cart in session state
    if "cart" not in st.session_state:
        st.session_state.cart = []

    col_left, col_right = st.columns([3, 2], gap="large")

    # ── LEFT: Product search & cart ───────────────────────────────────────────
    with col_left:
        st.subheader("🔍 Add Product")

        tab_barcode, tab_search = st.tabs(["📷 Barcode Scan", "🔎 Search"])

        with tab_barcode:
            def on_barcode_scan():
                barcode = st.session_state.get("barcode_field", "").strip()
                if barcode:
                    _add_by_barcode(barcode)
                    st.session_state["barcode_field"] = ""

            st.text_input(
                "Scan barcode (focus here & scan):",
                key="barcode_field",
                placeholder="Scan or type barcode…",
                on_change=on_barcode_scan
            )
            # if st.button("➕ Add by Barcode", key="add_barcode"):
            #     on_barcode_scan()

        with tab_search:
            search_q = st.text_input("Search by name/category:", key="search_q")
            if search_q and len(search_q) >= 2:
                resp = _api("get", f"/products/search?q={search_q}")
                if resp and resp.status_code == 200:
                    products = resp.json()
                    if products:
                        for p in products[:8]:
                            c1, c2, c3 = st.columns([4, 2, 1])
                            c1.write(f"**{p['name']}** — ₹{p['price']}")
                            c2.write(f"Stock: {p['stock_qty']} {p['unit']}")
                            if c3.button("＋", key=f"add_{p['id']}"):
                                _add_to_cart(p)
                    else:
                        st.info("No products found.")

        # ── Cart ─────────────────────────────────────────────────────────────
        st.divider()
        st.subheader("🧾 Cart")

        if not st.session_state.cart:
            st.info("Cart is empty. Scan a product to begin.")
        else:
            for idx, item in enumerate(st.session_state.cart):
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([4, 1.5, 1.5, 1.5, 1])
                    c1.write(f"**{item['name']}**")
                    new_qty = c2.number_input(
                        "Qty", min_value=0.0, value=float(item["qty"]),
                        step=0.5, key=f"qty_{idx}", label_visibility="collapsed"
                    )
                    new_disc = c3.number_input(
                        "Disc%", min_value=0.0, max_value=100.0, value=float(item["discount"]),
                        step=1.0, key=f"disc_{idx}", label_visibility="collapsed"
                    )
                    if new_qty == 0:
                        del st.session_state.cart[idx]
                        st.rerun()
                    else:
                        item["qty"] = new_qty
                        item["discount"] = new_disc
                        subtotal = item["unit_price"] * new_qty * (1 - new_disc / 100)
                        c4.write(f"₹{subtotal:.2f}")
                    if c5.button("🗑️", key=f"del_{idx}"):
                        del st.session_state.cart[idx]
                        st.rerun()

    # ── RIGHT: Totals & Payment ───────────────────────────────────────────────
    with col_right:
        st.subheader("💰 Payment")

        # Weight button for weighted items
        with st.expander("⚖️ Read Scale Weight"):
            if st.button("📡 Read Weight Now"):
                resp = _api("get", "/hardware/scale")
                if resp and resp.status_code == 200:
                    data = resp.json()
                    if data.get("weight"):
                        st.success(f"Weight: **{data['weight']} {data.get('unit','kg')}**")
                        st.session_state["last_weight"] = data["weight"]
                    else:
                        st.warning(data.get("error", "Scale not responding"))

        # Cart discount
        cart_discount = st.number_input("Overall Discount %", 0.0, 100.0, 0.0, 1.0)

        # Payment mode
        payment_mode = st.selectbox(
            "Payment Mode",
            ["cash", "upi", "card", "credit"],
            format_func=lambda x: {"cash": "💵 Cash", "upi": "📱 UPI", "card": "💳 Card (Pine Labs)", "credit": "🤝 Credit"}[x],
        )

        # Customer (required for credit)
        customer_id = None
        if payment_mode == "credit":
            cust_phone = st.text_input("Customer Phone (for credit):")
            if cust_phone:
                resp = _api("get", f"/products/search?q={cust_phone}")  # use customer search if added
                st.caption("Enter phone to look up customer.")

        # ── Totals ────────────────────────────────────────────────────────────
        st.divider()
        subtotal = sum(
            item["unit_price"] * item["qty"] * (1 - item["discount"] / 100)
            for item in st.session_state.cart
        )
        disc_amount = subtotal * (cart_discount / 100)
        total = subtotal - disc_amount

        col_a, col_b = st.columns(2)
        col_a.metric("Subtotal", f"₹{subtotal:.2f}")
        col_a.metric("Discount", f"-₹{disc_amount:.2f}")
        col_b.metric("🧾 TOTAL", f"₹{total:.2f}")

        st.divider()

        # ── Confirm Sale ──────────────────────────────────────────────────────
        if st.button("✅ Confirm Sale", use_container_width=True, type="primary"):
            if not st.session_state.cart:
                st.warning("Cart is empty!")
            else:
                _confirm_sale(cart_discount, payment_mode, customer_id, total)

        if st.button("🗑️ Clear Cart", use_container_width=True):
            st.session_state.cart = []
            st.rerun()


def _add_by_barcode(barcode: str):
    resp = _api("get", f"/products/barcode/{barcode}")
    if resp and resp.status_code == 200:
        _add_to_cart(resp.json())
    elif resp:
        st.warning(f"Product with barcode '{barcode}' not found.")


def _add_to_cart(product: dict):
    for item in st.session_state.cart:
        if item["product_id"] == product["id"]:
            item["qty"] += 1
            st.toast(f"Updated qty: {item['name']}")
            return
    st.session_state.cart.append({
        "product_id": product["id"],
        "name": product["name"],
        "unit_price": product["price"],
        "qty": 1,
        "discount": 0.0,
    })
    st.toast(f"Added: {product['name']}")


def _confirm_sale(cart_discount: float, payment_mode: str, customer_id, total: float):
    payload = {
        "items": [
            {
                "product_id": item["product_id"],
                "qty": item["qty"],
                "unit_price": item["unit_price"],
                "discount": item["discount"],
            }
            for item in st.session_state.cart
        ],
        "discount": cart_discount,
        "payment_mode": payment_mode,
        "customer_id": customer_id,
    }

    # For card payments: initiate Pine Labs first
    if payment_mode == "card":
        with st.spinner("Initiating card payment…"):
            pay_resp = _api("post", "/hardware/payment/initiate",
                            json={"amount": total, "payment_mode": "card"})
            if pay_resp and pay_resp.status_code == 200:
                pay_data = pay_resp.json()
                if not pay_data.get("success"):
                    st.error(f"POS: {pay_data.get('message')}")
                    return
                st.info(f"✅ Payment initiated on terminal. Transaction ID: {pay_data.get('transaction_id')}")
            else:
                st.warning("POS terminal not reachable. Proceeding with manual verification.")

    with st.spinner("Processing sale…"):
        resp = _api("post", "/sales", json=payload)
        if resp is None:
            return
        if resp.status_code == 201:
            sale = resp.json()
            st.success(f"✅ Sale #{sale['id']} completed! Total: ₹{sale['total']:.2f}")

            # Print receipt
            receipt_payload = {
                "sale_id": sale["id"],
                "cashier": st.session_state.get("username", "Staff"),
                "created_at": sale["created_at"][:16].replace("T", " "),
                "payment_mode": sale["payment_mode"],
                "transaction_ref": sale.get("transaction_ref"),
                "items": [
                    {
                        "name": i["product_name"],
                        "qty": i["qty"],
                        "unit_price": i["unit_price"],
                        "subtotal": i["subtotal"],
                    }
                    for i in sale.get("items", [])
                ],
                "subtotal": sale["subtotal"],
                "discount": sale["discount"],
                "tax": sale["tax"],
                "total": sale["total"],
            }
            print_resp = _api("post", "/hardware/print", json=receipt_payload)
            if print_resp and print_resp.status_code == 200:
                st.info("🖨️ Receipt printed.")
            else:
                st.warning("🖨️ Receipt print failed (is printer connected?)")

            st.session_state.cart = []
            st.rerun()
        else:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            st.error(f"Sale failed: {detail}")
