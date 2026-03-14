"""
frontend/inventory.py — Admin inventory management page.
"""
import streamlit as st
import requests
import os
import pandas as pd
import base64

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


def show_inventory():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }
    .page-header { font-size: 1.5rem; font-weight: 700;
                    background: linear-gradient(90deg,#0f3460,#1a1a2e); color:#fff;
                    padding:14px 20px; border-radius:12px; margin-bottom:16px; }
    .low-stock { color: #e94560; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="page-header">📦 Inventory Management</div>', unsafe_allow_html=True)

    tab_list, tab_add, tab_restock = st.tabs(["📋 Product List", "➕ Add Product", "🔄 Restock"])

    # ── PRODUCT LIST ──────────────────────────────────────────────────────────
    with tab_list:
        resp = _api("get", "/products/")
        if resp and resp.status_code == 200:
            products = resp.json()
            if products:
                df = pd.DataFrame(products)[
                    ["id", "barcode", "name", "category", "unit", "price", "tax_rate", "stock_qty", "min_stock_alert"]
                ]
                df.columns = ["ID", "Barcode", "Name", "Category", "Unit", "Price (₹)", "Tax %", "Stock", "Min Alert"]

                # Clean currencies to int
                df["Price (₹)"] = df["Price (₹)"].fillna(0).astype(int)
                df["Tax %"] = df["Tax %"].fillna(0).astype(int)
                
                # Conditionally format quantities based on unit
                def format_qty(row, col):
                    val = row[col]
                    if pd.isna(val): return 0
                    if str(row["Unit"]).lower() in ["kg", "litre", "ltr"]:
                        return round(float(val), 2)
                    return int(val)
                    
                df["Stock"] = df.apply(lambda r: format_qty(r, "Stock"), axis=1)
                df["Min Alert"] = df.apply(lambda r: format_qty(r, "Min Alert"), axis=1)

                # Highlight low stock
                def highlight_low(row):
                    color = "background-color: #000000" if row["Stock"] <= row["Min Alert"] else ""
                    return [color] * len(row)

                st.dataframe(
                    df.style.apply(highlight_low, axis=1),
                    use_container_width=True,
                    height=400,
                )

                # ── Edit / Delete section ─────────────────────────────────────
                st.divider()
                st.subheader("✏️ Edit or Delete Product")
                product_options = {f"{p['id']} — {p['name']}": p for p in products}
                selected_label = st.selectbox("Select product:", list(product_options.keys()))
                selected = product_options[selected_label]

                with st.form("edit_form"):
                    c1, c2 = st.columns(2)
                    new_name = c1.text_input("Name", value=selected["name"])
                    new_barcode = c2.text_input("Barcode", value=selected.get("barcode") or "")
                    new_category = c1.text_input("Category", value=selected.get("category") or "")
                    new_unit = c2.text_input("Unit", value=selected.get("unit", "pcs"))
                    
                    is_float_unit = new_unit.lower() in ["kg", "litre"]
                    
                    new_price = c1.number_input("Price (₹)", value=int(selected["price"]), min_value=0, step=1)
                    new_tax = c2.number_input("Tax Rate %", value=int(selected.get("tax_rate", 0)), min_value=0, step=1)
                    new_min = c1.number_input(
                        "Min Stock Alert", 
                        value=float(selected.get("min_stock_alert", 5)) if is_float_unit else int(selected.get("min_stock_alert", 5)), 
                        min_value=0.0 if is_float_unit else 0, 
                        step=0.5 if is_float_unit else 1
                    )
                    new_desc = st.text_area("Description", value=selected.get("description") or "")
                    
                    if selected.get("image_data"):
                        st.image(f"data:image/jpeg;base64,{selected['image_data']}", caption="Current Image", width=150)
                    new_image = st.file_uploader("Upload New Image (optional, jpg/png/webp)", type=["jpg", "jpeg", "png","webp"], key=f"edit_img_{selected['id']}")

                    c_save, c_delete = st.columns(2)
                    save = c_save.form_submit_button("💾 Save Changes", use_container_width=True)
                    delete = c_delete.form_submit_button("🗑️ Delete Product", use_container_width=True)

                if save:
                    image_b64 = selected.get("image_data")
                    if new_image is not None:
                        image_b64 = base64.b64encode(new_image.read()).decode("utf-8")
                    
                    payload = {
                        "name": new_name, "barcode": new_barcode or None,
                        "category": new_category, "unit": new_unit,
                        "price": new_price, "tax_rate": new_tax,
                        "min_stock_alert": new_min, "description": new_desc,
                        "image_data": image_b64,
                    }
                    r = _api("put", f"/products/{selected['id']}", json=payload)
                    if r and r.status_code == 200:
                        st.success("Product updated!")
                        st.rerun()
                    else:
                        st.error(f"Update failed: {r.text if r else 'No response'}")

                if delete:
                    r = _api("delete", f"/products/{selected['id']}")
                    if r and r.status_code == 200:
                        st.success("Product deleted!")
                        st.rerun()
                    else:
                        st.error(f"Delete failed: {r.text if r else 'No response'}")

            else:
                st.info("No products found. Add your first product.")

    # ── ADD PRODUCT ───────────────────────────────────────────────────────────
    with tab_add:
        st.subheader("➕ Add New Product")
        
        if "add_reset" not in st.session_state:
            st.session_state.add_reset = 0
            
        if "add_success" in st.session_state:
            st.success(st.session_state.add_success)
            del st.session_state.add_success

        c1, c2 = st.columns(2)
        name = c1.text_input("Product Name *", key=f"new_name_{st.session_state.add_reset}")
        barcode = c2.text_input("Barcode (optional)", key=f"new_barcode_{st.session_state.add_reset}")
        category = c1.text_input("Category", key=f"new_category_{st.session_state.add_reset}")
        unit = c2.selectbox("Unit", ["pcs", "kg", "litre", "pack", "dozen", "box"], key=f"new_unit_{st.session_state.add_reset}")
        
        is_float_unit = unit in ["kg", "litre", "ltr"]
        
        price = c1.number_input("Price (₹) *", min_value=0, step=1, key=f"new_price_{st.session_state.add_reset}")
        tax_rate = c2.number_input("Tax Rate %", 0, 100, 0, 1, key=f"new_tax_{st.session_state.add_reset}")
        stock_qty = c1.number_input(
            "Opening Stock", 
            min_value=0.0 if is_float_unit else 0, 
            step=0.5 if is_float_unit else 1, 
            key=f"new_stock_{st.session_state.add_reset}"
        )
        min_stock = c2.number_input(
            "Min Stock Alert", 
            min_value=0.0 if is_float_unit else 0, 
            value=5.0 if is_float_unit else 5, 
            step=0.5 if is_float_unit else 1, 
            key=f"new_min_{st.session_state.add_reset}"
        )
        description = st.text_area("Description (optional)", key=f"new_desc_{st.session_state.add_reset}")
        product_image = st.file_uploader("Product Image (optional, jpg/png/webp)", type=["jpg", "jpeg", "png", "webp"], key=f"add_img_{st.session_state.add_reset}")
        
        submitted = st.button("✅ Add Product", use_container_width=True)

        if submitted:
            if not name or price == 0:
                st.warning("Name and price are required.")
            else:
                image_b64 = None
                if product_image is not None:
                    image_b64 = base64.b64encode(product_image.read()).decode("utf-8")
                
                payload = {
                    "name": name, "barcode": barcode or None,
                    "category": category, "unit": unit,
                    "price": price, "tax_rate": tax_rate,
                    "stock_qty": stock_qty, "min_stock_alert": min_stock,
                    "description": description or None,
                    "image_data": image_b64,
                }
                r = _api("post", "/products/", json=payload)
                if r and r.status_code == 201:
                    st.session_state.add_success = f"✅ Product '{name}' added successfully!"
                    # Streamlit forbids directly changing session_state keys associated with un-rendered widgets
                    # if the widget hasn't rendered yet or is bound.
                    # Best way is to increment the reset counter to spawn fresh widgets with new keys.
                    st.session_state.add_reset += 1
                    st.rerun()
                else:
                    try:
                        detail = r.json().get("detail", r.text) if r else "No response"
                    except Exception:
                        detail = r.text if r else "No response"
                    st.error(f"Failed: {detail}")

    # ── RESTOCK ───────────────────────────────────────────────────────────────
    with tab_restock:
        st.subheader("🔄 Restock Product")
        resp = _api("get", "/products/")
        if resp and resp.status_code == 200:
            products = resp.json()
            product_map = {f"{p['id']} — {p['name']} (Stock: {p['stock_qty']})": p for p in products}
            with st.form("restock_form"):
                selected_label = st.selectbox("Select product:", list(product_map.keys()))
                qty = st.number_input("Quantity to add *", min_value=0.1, step=1.0)
                reason = st.text_input("Reason", value="Restock from supplier")
                submitted = st.form_submit_button("📥 Restock", use_container_width=True)

            if submitted:
                product = product_map[selected_label]
                payload = {"product_id": product["id"], "qty": qty, "reason": reason}
                r = _api("post", "/inventory/restock", json=payload)
                if r and r.status_code == 200:
                    st.success(f"✅ Restocked {qty} units of '{product['name']}'.")
                else:
                    st.error(f"Restock failed: {r.text if r else 'No response'}")
