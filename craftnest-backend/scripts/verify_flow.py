import httpx
import uuid
import json

BASE_URL = "https://localhost:8443"

def run_verification():
    # Use httpx.Client with verification disabled for local self-signed certs
    client = httpx.Client(verify=False)
    
    unique_suffix = uuid.uuid4().hex[:6]
    seller_email = f"seller_{unique_suffix}@example.com"
    buyer_email = f"buyer_{unique_suffix}@example.com"
    password = "SecurePassword123!"

    print("=== Step 1: Sign up & Login Seller ===")
    signup_seller_resp = client.post(
        f"{BASE_URL}/api/v1/auth/signup",
        json={"email": seller_email, "password": password, "role": "seller"}
    )
    if signup_seller_resp.status_code != 201:
        print(f"Failed to sign up seller: {signup_seller_resp.text}")
        return False
    print("Seller signed up successfully.")

    login_seller_resp = client.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": seller_email, "password": password, "role": "seller"}
    )
    if login_seller_resp.status_code != 200:
        print(f"Failed to log in seller: {login_seller_resp.text}")
        return False
    seller_token = login_seller_resp.json()["access_token"]
    print("Seller logged in successfully.")

    print("\n=== Step 2: Sign up & Login Buyer ===")
    signup_buyer_resp = client.post(
        f"{BASE_URL}/api/v1/auth/signup",
        json={"email": buyer_email, "password": password, "role": "buyer"}
    )
    if signup_buyer_resp.status_code != 201:
        print(f"Failed to sign up buyer: {signup_buyer_resp.text}")
        return False
    print("Buyer signed up successfully.")

    login_buyer_resp = client.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": buyer_email, "password": password, "role": "buyer"}
    )
    if login_buyer_resp.status_code != 200:
        print(f"Failed to log in buyer: {login_buyer_resp.text}")
        return False
    buyer_token = login_buyer_resp.json()["access_token"]
    print("Buyer logged in successfully.")

    print("\n=== Step 3: Get Category ID ===")
    categories_resp = client.get(f"{BASE_URL}/api/v1/browse/categories")
    if categories_resp.status_code != 200:
        print(f"Failed to fetch categories: {categories_resp.text}")
        return False
    categories = categories_resp.json()
    if not categories:
        print("No categories found in database. Please run migrations/seeders first.")
        return False
    category_id = categories[0]["id"]
    print(f"Using category: {categories[0]['display_name']} ({category_id})")

    print("\n=== Step 4: Create 2 Products ===")
    headers_seller = {"Authorization": f"Bearer {seller_token}"}
    
    product1_payload = {
        "title": f"Artisanal Ceramic Mug {unique_suffix}",
        "description": "Hand-thrown speckled stoneware mug with satin white glaze.",
        "price_paise": 120000, # ₹1,200
        "stock": 15,
        "category_id": category_id,
        "image_urls": ["/media/products/placeholder.jpg"]
    }
    prod1_resp = client.post(f"{BASE_URL}/api/v1/products", json=product1_payload, headers=headers_seller)
    if prod1_resp.status_code != 201:
        print(f"Failed to create product 1: {prod1_resp.text}")
        return False
    prod1 = prod1_resp.json()
    print(f"Product 1 created: {prod1['title']} (ID: {prod1['id']})")

    product2_payload = {
        "title": f"Organic Linen Napkins {unique_suffix}",
        "description": "Set of 4 woven natural linen napkins with mitered corners.",
        "price_paise": 85000, # ₹850
        "stock": 8,
        "category_id": category_id,
        "image_urls": ["/media/products/placeholder.jpg"]
    }
    prod2_resp = client.post(f"{BASE_URL}/api/v1/products", json=product2_payload, headers=headers_seller)
    if prod2_resp.status_code != 201:
        print(f"Failed to create product 2: {prod2_resp.text}")
        return False
    prod2 = prod2_resp.json()
    print(f"Product 2 created: {prod2['title']} (ID: {prod2['id']})")

    print("\n=== Step 5: Buyer Places Order ===")
    headers_buyer = {"Authorization": f"Bearer {buyer_token}"}
    order_payload = {
        "shipping_address": "123 Creative Nest Lane,\nArtisan District, Pune - 411001",
        "items": [
            {"product_id": prod1["id"], "quantity": 2},
            {"product_id": prod2["id"], "quantity": 1}
        ]
    }
    order_resp = client.post(f"{BASE_URL}/api/v1/orders", json=order_payload, headers=headers_buyer)
    if order_resp.status_code != 201:
        print(f"Failed to create order: {order_resp.text}")
        return False
    order = order_resp.json()
    order_id = order["id"]
    print(f"Order created successfully. ID: {order_id}")
    print(f"Initial Status: {order['status']} (Expected: awaiting_payment)")
    assert order["status"] == "awaiting_payment"

    print("\n=== Step 6: Seller Updates Order to Processing ===")
    proc_payload = {"status": "processing", "seller_note": "Thank you for supporting hand-made art! Preparing shipment."}
    proc_resp = client.patch(f"{BASE_URL}/api/v1/seller/orders/{order_id}/status", json=proc_payload, headers=headers_seller)
    if proc_resp.status_code != 200:
        print(f"Failed to advance to processing: {proc_resp.text}")
        return False
    order_proc = proc_resp.json()
    print(f"Status updated: {order_proc['status']} (Expected: processing)")
    assert order_proc["status"] == "processing"

    print("\n=== Step 7: Seller Updates Order to Shipped (with Tracking) ===")
    tracking_code = f"TRK-{uuid.uuid4().hex[:12].upper()}"
    ship_payload = {
        "status": "shipped",
        "seller_note": "Your items have been shipped via India Post.",
        "tracking_code": tracking_code
    }
    ship_resp = client.patch(f"{BASE_URL}/api/v1/seller/orders/{order_id}/status", json=ship_payload, headers=headers_seller)
    if ship_resp.status_code != 200:
        print(f"Failed to advance to shipped: {ship_resp.text}")
        return False
    order_ship = ship_resp.json()
    print(f"Status updated: {order_ship['status']} (Expected: shipped)")
    print(f"Tracking Code recorded: {order_ship['tracking_code']}")
    assert order_ship["status"] == "shipped"
    assert order_ship["tracking_code"] == tracking_code

    print("\n=== Step 8: Buyer Verifies Tracking Code on Details ===")
    buyer_get_resp = client.get(f"{BASE_URL}/api/v1/orders/{order_id}", headers=headers_buyer)
    if buyer_get_resp.status_code != 200:
        print(f"Failed to fetch order as buyer: {buyer_get_resp.text}")
        return False
    buyer_order_view = buyer_get_resp.json()
    print(f"Buyer retrieved order status: {buyer_order_view['status']}")
    print(f"Buyer retrieved tracking: {buyer_order_view['tracking_code']}")
    assert buyer_order_view["status"] == "shipped"
    assert buyer_order_view["tracking_code"] == tracking_code

    print("\n=== Step 9: Seller Marks Order as Delivered ===")
    deliv_payload = {"status": "delivered"}
    deliv_resp = client.patch(f"{BASE_URL}/api/v1/seller/orders/{order_id}/status", json=deliv_payload, headers=headers_seller)
    if deliv_resp.status_code != 200:
        print(f"Failed to advance to delivered: {deliv_resp.text}")
        return False
    order_deliv = deliv_resp.json()
    print(f"Status updated: {order_deliv['status']} (Expected: delivered)")
    assert order_deliv["status"] == "delivered"

    print("\n=== Step 10: Buyer Verifies Final State ===")
    buyer_final_resp = client.get(f"{BASE_URL}/api/v1/orders/{order_id}", headers=headers_buyer)
    if buyer_final_resp.status_code != 200:
        print(f"Failed to fetch final order as buyer: {buyer_final_resp.text}")
        return False
    buyer_order_final = buyer_final_resp.json()
    print(f"Final Order Status: {buyer_order_final['status']} (Expected: delivered)")
    assert buyer_order_final["status"] == "delivered"

    print("\n==============================================")
    print(" SUCCESS: Full Order Lifecycle Flow Verified!")
    print("==============================================")
    return True

if __name__ == "__main__":
    run_verification()
