import streamlit as st
import requests
import pandas as pd
import json
import time
from datetime import datetime

# Backend API URL
BASE_URL = "http://localhost:5000"

# Initialize session state
if "token" not in st.session_state:
    st.session_state.token = None
if "role" not in st.session_state:
    st.session_state.role = None
if "username" not in st.session_state:
    st.session_state.username = None

def make_authenticated_request(method, endpoint, **kwargs):
    """Make an authenticated request to the backend."""
    headers = {"Authorization": st.session_state.token} if st.session_state.token else {}
    try:
        response = getattr(requests, method)(f"{BASE_URL}{endpoint}", headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error: {str(e)}")
        return None

def login():
    """Login form."""
    st.subheader("Login")
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")
    if st.button("Login"):
        response = requests.post(f"{BASE_URL}/login", json={"username": username, "password": password})
        if response.status_code == 200:
            data = response.json()
            st.session_state.token = data["token"]
            st.session_state.role = data["role"]
            st.session_state.username = username
            st.success("Logged in successfully!")
            st.rerun()
        else:
            st.error(response.json().get("error", "Login failed"))

def register():
    """Registration form."""
    st.subheader("Register")
    username = st.text_input("Username", key="register_username")
    password = st.text_input("Password", type="password", key="register_password")
    if st.button("Register"):
        response = requests.post(f"{BASE_URL}/register", json={"username": username, "password": password})
        if response.status_code == 201:
            st.success("Registered successfully! Please login.")
        else:
            st.error(response.json().get("error", "Registration failed"))

def logout():
    """Logout function."""
    st.session_state.token = None
    st.session_state.role = None
    st.session_state.username = None
    st.success("Logged out successfully!")
    st.rerun()

def show_products():
    """Display product catalog."""
    st.subheader("Product Catalog")
    products = make_authenticated_request("get", "/products")
    if products:
        df = pd.DataFrame(products)
        st.dataframe(df[["id", "name", "price", "stock"]])
        product_id = st.selectbox("Select Product to Add to Cart", df["id"], format_func=lambda x: f"{df[df['id'] == x]['name'].iloc[0]} (ID: {x})")
        quantity = st.number_input("Quantity", min_value=1, value=1)
        if st.button("Add to Cart"):
            if st.session_state.token:
                response = make_authenticated_request("post", "/cart/add", json={"product_id": product_id, "quantity": quantity})
                if response:
                    st.success(response.get("message", "Added to cart"))
            else:
                st.error("Please login to add items to cart")

def show_cart():
    """Display and manage cart."""
    st.subheader("Shopping Cart")
    if not st.session_state.token:
        st.error("Please login to view your cart")
        return
    cart = make_authenticated_request("get", "/cart")
    if cart and cart.get("cart"):
        df = pd.DataFrame([(k, v) for k, v in cart["cart"].items()], columns=["Product ID", "Quantity"])
        st.dataframe(df)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Clear Cart"):
                response = make_authenticated_request("delete", "/cart")
                if response:
                    st.success(response.get("message", "Cart cleared"))
                    st.rerun()
        with col2:
            if st.button("Create Order"):
                response = make_authenticated_request("post", "/order")
                if response:
                    st.success(f"Order created: {response.get('order_id')}")
                    st.rerun()
    else:
        st.info("Your cart is empty")

def show_notifications():
    """Display notifications."""
    st.subheader("Notifications")
    if not st.session_state.token:
        st.error("Please login to view notifications")
        return
    notifications = make_authenticated_request("get", "/notifications")
    if notifications and notifications.get("notifications"):
        df = pd.DataFrame(notifications["notifications"])
        df["timestamp"] = df["timestamp"].apply(lambda x: datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M:%S"))
        st.dataframe(df[["order_id", "status", "message", "timestamp"]])
    else:
        st.info("No notifications available")
    
    # Placeholder for real-time notifications (simplified polling)
    if st.checkbox("Enable Real-Time Notifications"):
        placeholder = st.empty()
        while True:
            notifications = make_authenticated_request("get", "/notifications")
            if notifications and notifications.get("notifications"):
                latest = notifications["notifications"][0]
                placeholder.write(f"Latest: {latest['message']} at {datetime.fromtimestamp(latest['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(5)

def show_admin_panel():
    """Admin panel for product and order management."""
    if st.session_state.role != "admin":
        st.error("Access denied: Admin only")
        return
    st.subheader("Admin Panel")
    
    # Create Product
    st.write("### Create Product")
    name = st.text_input("Product Name")
    price = st.number_input("Price", min_value=0.0, step=0.01)
    stock = st.number_input("Stock", min_value=0, step=1)
    if st.button("Create Product"):
        response = make_authenticated_request("post", "/products", json={"name": name, "price": price, "stock": stock})
        if response:
            st.success(response.get("message", "Product created"))
    
    # Update/Delete Product
    st.write("### Update/Delete Product")
    products = make_authenticated_request("get", "/products")
    if products:
        product_id = st.selectbox("Select Product", [p["id"] for p in products], format_func=lambda x: next(p["name"] for p in products if p["id"] == x))
        new_name = st.text_input("New Name")
        new_price = st.number_input("New Price", min_value=0.0, step=0.01)
        new_stock = st.number_input("New Stock", min_value=0, step=1)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Update Product"):
                response = make_authenticated_request("put", f"/products/{product_id}", json={"name": new_name, "price": new_price, "stock": new_stock})
                if response:
                    st.success(response.get("message", "Product updated"))
        with col2:
            if st.button("Delete Product"):
                response = make_authenticated_request("delete", f"/products/{product_id}")
                if response:
                    st.success(response.get("message", "Product deleted"))
                    st.rerun()
    
    # Update Order Status
    st.write("### Update Order Status")
    order_id = st.number_input("Order ID", min_value=1, step=1)
    new_status = st.selectbox("New Status", ["Pending", "Processing", "Shipped", "Delivered"])
    if st.button("Update Order Status"):
        response = make_authenticated_request("put", f"/order/{order_id}/status", json={"status": new_status})
        if response:
            st.success(response.get("message", "Status updated"))

def main():
    """Main Streamlit app."""
    st.title("Shop Application")
    
    # Sidebar
    with st.sidebar:
        if st.session_state.token:
            st.write(f"Logged in as: {st.session_state.username} ({st.session_state.role})")
            if st.button("Logout"):
                logout()
        else:
            login()
            st.write("---")
            register()
        
        st.write("### Navigation")
        page = st.radio("Go to", ["Home", "Cart", "Notifications", "Admin Panel"] if st.session_state.role == "admin" else ["Home", "Cart", "Notifications"])
    
    # Main content
    if page == "Home":
        show_products()
    elif page == "Cart":
        show_cart()
    elif page == "Notifications":
        show_notifications()
    elif page == "Admin Panel":
        show_admin_panel()

if __name__ == "__main__":
    main()