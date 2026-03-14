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
    /* Target Streamlit's image container */
    [data-testid="stImage"] img {
        height: 140px !important;
        width: 100% !important;
        object-fit: cover !important;
        border-radius: 8px !important;
    }
    .product-placeholder {
        height: 140px;
        background-color: rgba(255,255,255,0.05);
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 3rem;
        margin-bottom: 8px;
    }
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
                        # Display products in a grid
                        cols_per_row = 3
                        # Increase limit since it's a grid
                        products_to_show = products[:12]
                        for i in range(0, len(products_to_show), cols_per_row):
                            cols = st.columns(cols_per_row)
                            for col, p in zip(cols, products_to_show[i:i+cols_per_row]):
                                with col:
                                    with st.container(border=True):
                                        # Image
                                        if p.get("image_data"):
                                            st.image(f"data:image/jpeg;base64,{p['image_data']}", use_container_width=True)
                                        else:
                                            st.markdown('<div class="product-placeholder">🛒</div>', unsafe_allow_html=True)
                                        
                                        # Details
                                        st.markdown(f"**{p['name']}**")
                                        st.caption(f"₹{int(p['price'])} • Stock: {int(p['stock_qty'])} {p['unit']}")
                                        if st.button("➕ Add", key=f"add_{p['id']}", use_container_width=True):
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
                # Fetch the latest state directly bound to the widgets before rendering
                # to prevent a 1-click visual lag on the subtotals.
                current_qty = st.session_state.get(f"qty_{idx}", item["qty"])
                current_disc = st.session_state.get(f"disc_{idx}", item["discount"])
                
                item["qty"] = current_qty
                item["discount"] = current_disc
                
                subtotal = item["unit_price"] * item["qty"] * (1 - item["discount"] / 100)
                
                is_float_unit = item.get("unit", "pcs").lower() in ["kg", "litre", "ltr"]

                with st.container(border=True):

                    # ── Top row: serial + image + name + total + delete ──
                    top_left, top_right = st.columns([3, 1])

                    with top_left:
                        if item.get("image_data"):
                            img_html = (
                                f"<img src='data:image/jpeg;base64,{item['image_data']}' "
                                f"style='width:44px; height:44px; object-fit:cover; "
                                f"border-radius:6px; display:block; flex-shrink:0;'>"
                            )
                        else:
                            img_html = (
                                "<div style='width:44px; height:44px; border-radius:6px; "
                                "background:rgba(255,255,255,0.07); display:flex; flex-shrink:0; "
                                "align-items:center; justify-content:center; font-size:1.3rem;'>🛒</div>"
                            )

                        st.markdown(
                            f"<div style='display:flex; align-items:center; gap:10px;'>"
                            f"<span style='font-size:0.85rem; font-weight:600; color:#888; "
                            f"min-width:16px; text-align:center;'>#{idx+1}</span>"
                            f"{img_html}"
                            f"<div style='line-height:1.4;'>"
                            f"<div style='font-weight:700; font-size:0.95rem;'>{item['name']}</div>"
                            f"<div style='color:#888; font-size:0.78rem;'>₹{int(item['unit_price'])} / unit</div>"
                            f"</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                    with top_right:
                        st.markdown(
                            f"<div style='text-align:right; padding-top:4px;'>"
                            f"<div style='font-size:0.72rem; color:#888; margin-bottom:2px;'>Total</div>"
                            f"<div style='font-size:1.1rem; font-weight:700; color:#e94560;'>₹{int(subtotal)}</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                    st.markdown("<div style='margin-top:8px;'>", unsafe_allow_html=True)

                    # ── Bottom row: qty + disc + delete ──────────────────
                    b1, b2, b3 = st.columns([2, 2, 1])

                    with b1:
                        new_qty = st.number_input(
                            "Qty", 
                            min_value=0.0 if is_float_unit else 0,
                            value=float(item["qty"]) if is_float_unit else int(item["qty"]),
                            step=0.5 if is_float_unit else 1, 
                            key=f"qty_{idx}",
                            label_visibility="visible"
                        )

                    with b2:
                        new_disc = st.number_input(
                            "Disc %", min_value=0, max_value=100,
                            value=int(item["discount"]),
                            step=1, key=f"disc_{idx}",
                            label_visibility="visible"
                        )

                    with b3:
                        st.markdown("<div style='padding-top:22px;'>", unsafe_allow_html=True)
                        if st.button("🗑️ Del", key=f"del_{idx}", use_container_width=True):
                            del st.session_state.cart[idx]
                            st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown("</div>", unsafe_allow_html=True)

                    # Handle qty = 0 removal
                    if new_qty == 0:
                        del st.session_state.cart[idx]
                        st.rerun()
                    else:
                        item["qty"] = new_qty
                        item["discount"] = new_disc

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
        col_a.metric("Subtotal", f"₹{int(subtotal)}")
        col_a.metric("Discount", f"-₹{int(disc_amount)}")
        col_b.metric("🧾 TOTAL", f"₹{int(total)}")

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
            is_float_unit = item.get("unit", "pcs").lower() in ["kg", "litre", "ltr"]
            item["qty"] += 1.0 if is_float_unit else 1
            st.toast(f"Updated qty: {item['name']}")
            return
    st.session_state.cart.append({
        "product_id": product["id"],
        "name": product["name"],
        "unit_price": product["price"],
        "image_data": product.get("image_data"),
        "unit": product.get("unit", "pcs"),
        "qty": 1.0 if product.get("unit", "pcs").lower() in ["kg", "litre", "ltr"] else 1,
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
